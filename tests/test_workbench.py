"""Bounded context evidence tests; no model downloads, training, or GPU work."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from detector_eval.metrics import select_thresholds
from detector_eval.candidate import SCORE_RECIPE, select_on_calibration
from turingtint.research import ResearchBusy, ResearchUnavailable
from turingtint.text import utf16_slice
from turingtint.workbench import WorkbenchDetector, load_verified_baseline, load_verified_thresholds


THRESHOLDS = {name: {"human_max": .2, "ai_min": .8} for name in ("mage", "tfidf")}


def passage(words=180):
    tokens = ["\U0001f9ea", "cafe\u0301"] + [f"word{index}" for index in range(words - 2)]
    return "  \n" + "\n\n ".join(" ".join(tokens[index:index + 17]) for index in range(0, len(tokens), 17)) + " \n "


class FakeResearch:
    def __init__(self, scores=(.95,), *, unavailable=False, **changes):
        self.scores = list(scores)
        self.inputs = []
        self.changes = changes
        self.unavailable = unavailable

    def analyze(self, text):
        self.inputs.append(text)
        if self.unavailable:
            raise ResearchUnavailable("PRIVATE loader detail")
        score = self.scores[min(len(self.inputs) - 1, len(self.scores) - 1)]
        return {"score_ai": score, "score_kind": "uncalibrated_softmax_class_0", "input_characters": len(text),
                "raw_logits": [math.log(score / (1 - score)), 0.] if 0 < score < 1 else [0., 0.],
                "original_tokens": len(text.split()) + 2, "input_tokens": len(text.split()) + 2,
                "max_tokens": 512, "truncated": False, **self.changes}


class FakeBaseline:
    classes_ = [0, 1]

    def __init__(self, scores=(.95,)):
        self.scores = list(scores)
        self.inputs = []

    def predict_proba(self, rows):
        self.inputs.extend(rows)
        score = self.scores[min(len(self.inputs) - 1, len(self.scores) - 1)]
        return [[1 - score, score]]


class WorkbenchTests(unittest.TestCase):
    def detector(self, research=None, baseline=None, thresholds=None, **options):
        research = research if research is not None else FakeResearch()
        baseline = baseline if baseline is not None else FakeBaseline()
        return WorkbenchDetector(research, baseline_loader=lambda: baseline,
                                 threshold_loader=lambda: THRESHOLDS if thresholds is None else thresholds, **options)

    def test_primary_signal_produces_only_provisional_leaning_not_authorship_fact(self):
        result = self.detector().analyze(passage())
        self.assertEqual(result["assessment"]["label"], "ai_leaning")
        self.assertIn("does not prove", result["assessment"]["summary"])
        self.assertFalse(result["product_approved"])
        self.assertFalse(result["validated"])
        self.assertEqual(result["status"], "experimental")
        self.assertEqual(result["decision_policy"], "mage_margin_primary_v1")
        self.assertEqual([item["role"] for item in result["models"]], ["primary", "secondary_diagnostic"])
        self.assertEqual(result["input"]["analyzed_characters"], len(passage()))
        self.assertTrue(result["input"]["coverage_complete"])
        self.assertTrue(result["input"]["context_lengths_supported"])
        self.assertTrue(all(item["leaning_supported"] for item in result["models"]))
        self.assertTrue(all(item["label"] == "ai_leaning" for item in result["models"]))
        human = self.detector(FakeResearch((.05,)), FakeBaseline((.05,))).analyze(passage())
        self.assertEqual(human["assessment"]["label"], "human_leaning")

    def test_secondary_disagreement_does_not_veto_primary_or_become_mixed(self):
        result = self.detector(FakeResearch((.95,)), FakeBaseline((.05,))).analyze(passage())
        self.assertEqual(result["assessment"]["label"], "ai_leaning")
        self.assertEqual([item["label"] for item in result["models"]], ["ai_leaning", "human_leaning"])
        self.assertEqual(result["segments"][0]["label"], "ai_leaning")
        self.assertIn("disagree", result["segments"][0]["reason"])

    def test_utf16_segments_preserve_every_character_and_nonoverlap(self):
        text = passage(610)
        research, baseline = FakeResearch(), FakeBaseline()
        result = self.detector(research, baseline).analyze(text)
        self.assertEqual(result["offset_encoding"], "utf-16")
        self.assertGreater(len(result["segments"]), 1)
        self.assertEqual("".join(item["text"] for item in result["segments"]), text)
        previous = 0
        for item in result["segments"]:
            self.assertEqual(item["start"], previous)
            self.assertEqual(utf16_slice(text, item["start"], item["end"]), item["text"])
            self.assertEqual(item["evidence_scope"], "context_block_not_sentence_authorship")
            self.assertGreaterEqual(item["words"], 80)
            self.assertLessEqual(item["words"], 200)
            previous = item["end"]
        self.assertEqual(previous, len(text.encode("utf-16-le")) // 2)
        self.assertEqual(research.inputs, baseline.inputs)
        self.assertEqual("".join(research.inputs), text)

    def test_different_context_opinions_cannot_be_averaged_into_global_label(self):
        result = self.detector(FakeResearch((.95, .05)), FakeBaseline((.95, .05))).analyze(passage(360))
        self.assertEqual([item["label"] for item in result["segments"]], ["ai_leaning", "human_leaning"])
        self.assertEqual(result["assessment"]["label"], "inconclusive")
        self.assertTrue(all(item["label"] == "inconclusive" for item in result["models"]))
        self.assertEqual(result["models"][0]["score_kind"], "word_weighted_mean_uncalibrated_context_scores")
        self.assertAlmostEqual(result["models"][0]["score_ai"], .5)

    def test_short_context_keeps_raw_predictions_without_leaning_label(self):
        result = self.detector().analyze("This short passage cannot support authorship localization.")
        self.assertEqual(result["assessment"]["label"], "inconclusive")
        for item in result["models"]:
            self.assertAlmostEqual(item["score_ai"], .95)
        self.assertTrue(all(item["label"] == "inconclusive" for item in result["models"]))
        self.assertIn("short", result["segments"][0]["reason"])
        self.assertIn("80 words", result["assessment"]["summary"])
        self.assertFalse(result["input"]["context_lengths_supported"])
        self.assertTrue(all(not item["leaning_supported"] for item in result["models"]))

    def test_edit_across_minimum_length_changes_eligibility_without_changing_raw_score(self):
        original = self.detector().analyze(passage(80))
        revised = self.detector().analyze(passage(79))
        self.assertEqual(revised["input"]["minimum_context_words"], 80)
        self.assertTrue(original["input"]["context_lengths_supported"])
        self.assertFalse(revised["input"]["context_lengths_supported"])
        for before, after in zip(original["models"], revised["models"]):
            self.assertAlmostEqual(before["score_ai"], after["score_ai"])
            self.assertTrue(before["leaning_supported"])
            self.assertFalse(after["leaning_supported"])
            self.assertEqual(after["label"], "inconclusive")

    def test_twelve_window_limit_leaves_explicit_unscored_remainder(self):
        text = passage(2500)
        research, baseline = FakeResearch(), FakeBaseline()
        result = self.detector(research, baseline).analyze(text)
        self.assertEqual(len(research.inputs), 12)
        self.assertEqual(len(baseline.inputs), 12)
        self.assertEqual(len(result["segments"]), 13)
        remainder = result["segments"][-1]
        self.assertEqual(remainder["label"], "inconclusive")
        self.assertTrue(all(item["status"] == "not_scored" for item in remainder["models"]))
        self.assertTrue(result["input"]["truncated"])
        self.assertFalse(result["input"]["coverage_complete"])
        self.assertEqual(result["input"]["analyzed_characters"], len(text) - len(remainder["text"]))
        self.assertEqual(result["assessment"]["label"], "inconclusive")
        self.assertEqual("".join(item["text"] for item in result["segments"]), text)

    def test_truncated_model_cannot_assign_whole_context_leaning(self):
        for declared_truncated in (True, False):
            with self.subTest(declared_truncated=declared_truncated):
                research = FakeResearch(original_tokens=700, input_tokens=512, truncated=declared_truncated)
                result = self.detector(research).analyze(passage())
                self.assertEqual(result["segments"][0]["models"][0]["status"], "truncated")
                self.assertEqual(result["segments"][0]["models"][0]["label"], "inconclusive")
                self.assertEqual(result["segments"][0]["models"][1]["label"], "ai_leaning")
                self.assertTrue(result["input"]["truncated"])
                self.assertEqual(result["input"]["analyzed_characters"], 0)
                self.assertEqual(result["assessment"]["label"], "inconclusive")

    def test_missing_secondary_does_not_block_primary_but_missing_primary_has_no_fallback(self):
        missing_baseline = WorkbenchDetector(FakeResearch(), threshold_loader=lambda: THRESHOLDS,
                                            baseline_loader=Mock(side_effect=ResearchUnavailable("PRIVATE baseline detail")))
        result = missing_baseline.analyze(passage())
        self.assertEqual(result["models"][0]["label"], "ai_leaning")
        self.assertEqual(result["models"][1]["status"], "unavailable")
        self.assertEqual(result["assessment"]["label"], "ai_leaning")
        self.assertEqual(result["input"]["analyzed_characters"], len(passage()))
        self.assertNotIn("PRIVATE", json.dumps(result))
        result = self.detector(FakeResearch(unavailable=True)).analyze(passage())
        self.assertEqual(result["models"][0]["status"], "unavailable")
        self.assertEqual(result["models"][1]["label"], "ai_leaning")
        self.assertEqual(result["input"]["analyzed_characters"], 0)

    def test_bad_or_missing_thresholds_do_not_hide_other_model_or_invent_labels(self):
        result = self.detector(thresholds={"mage": {"human_max": .8, "ai_min": .2}, "tfidf": THRESHOLDS["tfidf"]}).analyze(passage())
        self.assertEqual(result["models"][0]["label"], "inconclusive")
        self.assertAlmostEqual(result["models"][0]["score_ai"], .95)
        self.assertEqual(result["models"][1]["label"], "ai_leaning")
        self.assertEqual(result["assessment"]["label"], "inconclusive")

    def test_nonfinite_scores_or_wrong_token_metadata_are_unavailable(self):
        for changes in ({"score_ai": float("nan")}, {"score_ai": True}, {"score_ai": "0.95"},
                        {"input_tokens": 800}, {"max_tokens": 1024}, {"raw_logits": None},
                        {"raw_logits": [float("nan"), 0.]}, {"raw_logits": [True, 0.]},
                        {"raw_logits": [0., 0.]}, {"raw_logits": [1.]}, {"raw_logits": [1e308, -1e308]}):
            with self.subTest(changes=changes):
                result = self.detector(FakeResearch(**changes)).analyze(passage())
                self.assertEqual(result["models"][0]["status"], "unavailable")
                self.assertEqual(result["assessment"]["label"], "inconclusive")

    def test_uncertain_primary_cannot_be_overridden_by_secondary_ai(self):
        result = self.detector(FakeResearch((.5,)), FakeBaseline((.95,))).analyze(passage())
        self.assertEqual(result["assessment"]["label"], "inconclusive")
        self.assertEqual(result["models"][1]["label"], "ai_leaning")

    def test_margin_decision_uses_finite_logits_instead_of_rounded_softmax(self):
        raw = [5.66015625, -5.62890625]
        margin = raw[0] - raw[1]
        exact = 1 / (1 + math.exp(-margin))
        # Legacy rounded output is intentionally just below the frozen margin
        # cutoff. The real margin is at it; changing decimal formatting alone
        # could not recover this decision.
        legacy = .9999874830245972
        research = FakeResearch((legacy,), raw_logits=raw)
        thresholds = {"mage": {"human_max": .9998988918541782, "ai_min": .9999874911605668}, "tfidf": THRESHOLDS["tfidf"]}
        result = self.detector(research, FakeBaseline((.5,)), thresholds=thresholds).analyze(passage())
        self.assertLess(legacy, thresholds["mage"]["ai_min"])
        self.assertEqual(result["assessment"]["label"], "ai_leaning")
        opinion = result["segments"][0]["models"][0]
        self.assertEqual(opinion["score_ai"], exact)
        self.assertEqual(opinion["legacy_softmax_score_ai"], legacy)
        self.assertEqual(opinion["logit_margin"], margin)
        self.assertEqual(opinion["score_kind"], "uncalibrated_float64_sigmoid_logit_margin")

    def test_busy_request_rejected_and_lock_released_after_busy_provider(self):
        research = Mock()
        research.analyze.side_effect = ResearchBusy("Already scoring")
        detector = self.detector(research)
        with self.assertRaises(ResearchBusy):
            detector.analyze(passage())
        research.analyze.side_effect = FakeResearch().analyze
        self.assertEqual(detector.analyze(passage())["assessment"]["label"], "ai_leaning")
        entered, release = threading.Event(), threading.Event()
        def wait_for_release(text):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test fixture timed out")
            return FakeResearch().analyze(text)
        research.analyze.side_effect = wait_for_release
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(detector.analyze, passage())
            try:
                self.assertTrue(entered.wait(3))
                with self.assertRaises(ResearchBusy):
                    detector.analyze(passage())
            finally:
                release.set()
            self.assertEqual(future.result(timeout=3)["assessment"]["label"], "ai_leaning")

    def test_model_loading_is_lazy_reused_and_invalid_input_does_not_load(self):
        baseline_loader = Mock(return_value=FakeBaseline())
        threshold_loader = Mock(return_value=THRESHOLDS)
        detector = WorkbenchDetector(FakeResearch(), baseline_loader=baseline_loader, threshold_loader=threshold_loader)
        baseline_loader.assert_not_called()
        for invalid in ("", " \n", "x" * 50001, "bad\ud800text", "null\x00byte", 3):
            with self.subTest(invalid_type=type(invalid).__name__), self.assertRaises(ValueError):
                detector.analyze(invalid)
        baseline_loader.assert_not_called()
        for _ in range(2):
            detector.analyze(passage())
        baseline_loader.assert_called_once()
        threshold_loader.assert_called_once()


class WorkbenchArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "outputs/experiments/tfidf-v1"
        self.folder.mkdir(parents=True)
        self.content = b"local model fixture bytes"
        (self.folder / "baseline.joblib").write_bytes(self.content)
        self.sha = lambda value: hashlib.sha256(value).hexdigest()
        (self.folder / "report.json").write_text(json.dumps({"experiment": {"model_sha256": self.sha(self.content)}}))

    def test_baseline_hash_rejection_occurs_before_deserialization(self):
        (self.folder / "baseline.joblib").write_bytes(b"changed model")
        loader = Mock()
        with patch.dict(sys.modules, {"joblib": SimpleNamespace(load=loader)}):
            with self.assertRaises(ResearchUnavailable):
                load_verified_baseline(self.root)
        loader.assert_not_called()

    def test_baseline_deserializes_the_exact_bytes_it_verified(self):
        loader = Mock(side_effect=lambda stream: stream.read())
        with patch.dict(sys.modules, {"joblib": SimpleNamespace(load=loader)}):
            self.assertEqual(load_verified_baseline(self.root), self.content)
        self.assertEqual(loader.call_count, 1)

    def calibration_artifacts(self):
        frozen = self.root / "data/authorship/experiments/hc3-v1"
        frozen.mkdir(parents=True)
        rows, predictions = [], []
        for index, (label, score) in enumerate(((0, .1), (0, .2), (1, .8), (1, .9))):
            text = f"calibration fixture {index}"
            text_hash = self.sha(text.encode())
            rows.append({"id": str(index), "text": text, "label": label, "source_group": f"family-{index}", "prompt": "calibration-prompt", "split": "calibration", "text_sha256": text_hash, "document_sha256": text_hash})
            predictions.append({"id": str(index), "score_ai": score, "text_sha256": text_hash})
        records_bytes = "".join(json.dumps(row) + "\n" for row in rows).encode()
        (frozen / "records.jsonl").write_bytes(records_bytes)
        manifest_bytes = json.dumps({"records_sha256": self.sha(records_bytes)}).encode()
        (frozen / "manifest.json").write_bytes(manifest_bytes)
        prediction_bytes = "".join(json.dumps(row) + "\n" for row in predictions).encode()
        (self.folder / "predictions.jsonl").write_bytes(prediction_bytes)
        receipt = {"model_sha256": self.sha(self.content), "predictions_sha256": self.sha(prediction_bytes), "frozen_manifest_sha256": self.sha(manifest_bytes)}
        (self.folder / "report.json").write_text(json.dumps({"experiment": receipt}))
        thresholds = select_thresholds([{**row, "score": prediction["score_ai"]} for row, prediction in zip(rows, predictions)]).to_dict()
        comparison = {"input_hashes": {"hc3": self.sha(records_bytes), "tfidf_predictions": self.sha(prediction_bytes)}, "models": {"tfidf_logistic": {"calibrated_test": {"thresholds": thresholds}}}}
        result_dir = self.root / "evaluation/results"
        result_dir.mkdir(parents=True)
        path = result_dir / "phase2-comparison.json"
        path.write_text(json.dumps(comparison))
        return path, comparison

    def test_verified_baseline_thresholds_survive_missing_mage_artifacts(self):
        self.calibration_artifacts()
        self.assertEqual(load_verified_thresholds(self.root), {"tfidf": {"human_max": .2, "ai_min": .8}})

    def test_modified_saved_thresholds_are_rejected_by_calibration_recomputation(self):
        path, comparison = self.calibration_artifacts()
        comparison["models"]["tfidf_logistic"]["calibrated_test"]["thresholds"]["ai_min"] = .3
        path.write_text(json.dumps(comparison))
        self.assertEqual(load_verified_thresholds(self.root), {})

    def mage_candidate_artifacts(self):
        from detector_models.mage import MODEL_ID, MODEL_REVISION
        comparison_path, comparison = self.calibration_artifacts()
        folder = self.root / ".cache/detector-models/mage"
        folder.mkdir(parents=True)
        model_manifest = b'{"inference_allowed": true}'
        (folder / "manifest.json").write_bytes(model_manifest)
        comparison["input_hashes"]["mage_manifest"] = self.sha(model_manifest)
        frozen = self.root / "data/authorship/experiments/hc3-v1/records.jsonl"
        rows = [json.loads(line) for line in frozen.read_text().splitlines()]
        predictions = []
        for row, value in zip(rows, (.1, .2, .8, .9)):
            predictions.append({"id": row["id"], "score_ai": value, "raw_logits": [math.log(value / (1 - value)), 0.],
                                "text_sha256": row["text_sha256"], "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                                "preprocessing": "raw_text_v1", "max_tokens": 512,
                                "score_kind": "uncalibrated_softmax_class_0"})
        path = self.root / "outputs/experiments/mage-hc3-v1/predictions.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in predictions))
        comparison["input_hashes"]["mage_hc3_predictions"] = self.sha(path.read_bytes())
        comparison["models"]["mage_raw_text_512"] = comparison["models"]["tfidf_logistic"]
        comparison_path.write_text(json.dumps(comparison))
        selection, _ = select_on_calibration(rows, {row["id"]: row for row in predictions})
        candidate = {"version": 1, "product_approved": False, "score_recipe": SCORE_RECIPE,
                     "input_hashes": comparison["input_hashes"], "selection": selection}
        candidate_path = self.root / "evaluation/results/candidate-diagnostic.json"
        candidate_path.write_text(json.dumps(candidate))
        return candidate_path, candidate, path, predictions, comparison_path, comparison, rows

    def test_candidate_thresholds_require_verified_recipe_and_calibration_selection(self):
        candidate_path, candidate, *_ = self.mage_candidate_artifacts()
        with patch("detector_models.mage.verify_manifest", return_value={"inference_allowed": True}):
            result = load_verified_thresholds(self.root)
            self.assertEqual(set(result), {"mage", "tfidf"})
            self.assertAlmostEqual(result["mage"]["human_max"], .2)
            self.assertAlmostEqual(result["mage"]["ai_min"], .8)
            candidate["selection"]["candidates"]["logit_margin"]["thresholds"]["ai_min"] = .3
            candidate_path.write_text(json.dumps(candidate))
            self.assertEqual(set(load_verified_thresholds(self.root)), {"tfidf"})

    def test_wrong_margin_recipe_disables_primary_thresholds(self):
        candidate_path, candidate, *_ = self.mage_candidate_artifacts()
        candidate["score_recipe"] = {**SCORE_RECIPE, "transform": "legacy_rounded_softmax"}
        candidate_path.write_text(json.dumps(candidate))
        with patch("detector_models.mage.verify_manifest", return_value={"inference_allowed": True}):
            self.assertEqual(set(load_verified_thresholds(self.root)), {"tfidf"})

    def test_changed_logits_cannot_reuse_old_selection_even_with_updated_file_hashes(self):
        candidate_path, candidate, path, predictions, comparison_path, comparison, _ = self.mage_candidate_artifacts()
        predictions[0]["raw_logits"] = [7., 0.]
        path.write_text("".join(json.dumps(row) + "\n" for row in predictions))
        comparison["input_hashes"]["mage_hc3_predictions"] = self.sha(path.read_bytes())
        comparison_path.write_text(json.dumps(comparison))
        candidate["input_hashes"] = comparison["input_hashes"]
        candidate_path.write_text(json.dumps(candidate))
        with patch("detector_models.mage.verify_manifest", return_value={"inference_allowed": True}):
            self.assertEqual(set(load_verified_thresholds(self.root)), {"tfidf"})

    def test_selection_rejects_test_rows(self):
        *_, predictions, _comparison_path, _comparison, rows = self.mage_candidate_artifacts()
        rows[0]["split"] = "test"
        with self.assertRaisesRegex(ValueError, "calibration rows only"):
            select_on_calibration(rows, {row["id"]: row for row in predictions})


if __name__ == "__main__":
    unittest.main()
