"""Bounded context evidence tests; no model downloads, training, or GPU work."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from detector_eval.metrics import select_thresholds
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

    def test_agreement_produces_only_provisional_leaning_not_authorship_fact(self):
        result = self.detector().analyze(passage())
        self.assertEqual(result["assessment"]["label"], "ai_leaning")
        self.assertIn("does not prove", result["assessment"]["summary"])
        self.assertFalse(result["product_approved"])
        self.assertFalse(result["validated"])
        self.assertEqual(result["status"], "experimental")
        self.assertEqual(result["input"]["analyzed_characters"], len(passage()))
        self.assertTrue(result["input"]["coverage_complete"])
        self.assertTrue(all(item["label"] == "ai_leaning" for item in result["models"]))
        human = self.detector(FakeResearch((.05,)), FakeBaseline((.05,))).analyze(passage())
        self.assertEqual(human["assessment"]["label"], "human_leaning")

    def test_disagreement_keeps_individual_opinions_and_never_becomes_mixed(self):
        result = self.detector(FakeResearch((.95,)), FakeBaseline((.05,))).analyze(passage())
        self.assertEqual(result["assessment"]["label"], "inconclusive")
        self.assertEqual([item["label"] for item in result["models"]], ["ai_leaning", "human_leaning"])
        self.assertEqual(result["segments"][0]["label"], "inconclusive")
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
        self.assertTrue(all(item["score_ai"] == .95 for item in result["models"]))
        self.assertTrue(all(item["label"] == "inconclusive" for item in result["models"]))
        self.assertIn("short", result["segments"][0]["reason"])

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

    def test_missing_model_keeps_available_opinion_without_claiming_agreement(self):
        missing_baseline = WorkbenchDetector(FakeResearch(), threshold_loader=lambda: THRESHOLDS,
                                            baseline_loader=Mock(side_effect=ResearchUnavailable("PRIVATE baseline detail")))
        result = missing_baseline.analyze(passage())
        self.assertEqual(result["models"][0]["label"], "ai_leaning")
        self.assertEqual(result["models"][1]["status"], "unavailable")
        self.assertEqual(result["assessment"]["label"], "inconclusive")
        self.assertNotIn("PRIVATE", json.dumps(result))
        result = self.detector(FakeResearch(unavailable=True)).analyze(passage())
        self.assertEqual(result["models"][0]["status"], "unavailable")
        self.assertEqual(result["models"][1]["label"], "ai_leaning")
        self.assertEqual(result["input"]["analyzed_characters"], 0)

    def test_bad_or_missing_thresholds_do_not_hide_other_model_or_invent_labels(self):
        result = self.detector(thresholds={"mage": {"human_max": .8, "ai_min": .2}, "tfidf": THRESHOLDS["tfidf"]}).analyze(passage())
        self.assertEqual(result["models"][0]["label"], "inconclusive")
        self.assertEqual(result["models"][0]["score_ai"], .95)
        self.assertEqual(result["models"][1]["label"], "ai_leaning")
        self.assertEqual(result["assessment"]["label"], "inconclusive")

    def test_nonfinite_scores_or_wrong_token_metadata_are_unavailable(self):
        for changes in ({"score_ai": float("nan")}, {"score_ai": True}, {"score_ai": "0.95"}, {"input_tokens": 800}, {"max_tokens": 1024}):
            with self.subTest(changes=changes):
                result = self.detector(FakeResearch(**changes)).analyze(passage())
                self.assertEqual(result["models"][0]["status"], "unavailable")
                self.assertEqual(result["assessment"]["label"], "inconclusive")

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


if __name__ == "__main__":
    unittest.main()
