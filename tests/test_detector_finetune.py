import json
from pathlib import Path
import tempfile
import unittest

from detector_eval.experiment import file_sha, load_frozen
from detector_eval.finetune import compare_scores, fit_temperature, freeze_pilot, score_rows
from tests.test_detector_experiment import record


class FineTunePilotTests(unittest.TestCase):
    def test_linked_questions_stay_together_in_four_splits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            rows = [record(f"{i}-{label}", label, f"question-{i}")
                    for i in range(300) for label in ("human", "ai")]
            records = source / "records.jsonl"
            records.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            manifest = {"records_sha256": file_sha(records), "source_dataset": "fixture", "license_id": "fixture",
                        "attribution": "test fixture", "limitations": ["synthetic fixture"],
                        "related_source_groups": [{"source_groups": ["question-0", "removed", "question-299"]}]}
            (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            frozen = root / "frozen"
            freeze_pilot(source, frozen)
            result, receipt = load_frozen(frozen)
            self.assertEqual({r["split"] for r in result}, {"train", "validation", "calibration", "test"})
            related = [r for r in result if r["source_group"] in {"question-0", "question-299"}]
            self.assertEqual(len({r["split"] for r in related}), 1)
            self.assertEqual(len({r["split_unit"] for r in related}), 1)
            self.assertEqual(receipt["stats"]["counts"]["test:0"], receipt["stats"]["counts"]["test:1"])
            with self.assertRaisesRegex(ValueError, "already populated"):
                freeze_pilot(source, frozen)
            records = frozen / "records.jsonl"
            records.write_text(records.read_text() + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed"):
                load_frozen(frozen)

    def test_calibration_softens_overconfident_errors(self):
        logits = [[20., -20.], [-20., 20.], [20., -20.], [-20., 20.]]
        self.assertGreater(fit_temperature(logits, [0, 1, 1, 0]), 1.)
        with self.assertRaises(ValueError):
            fit_temperature([[1., float("nan")]], [0])

    def test_test_scores_do_not_change_fitted_temperature_or_thresholds(self):
        def rows(split):
            return [{"id": f"{split}-{i}", "label": i % 2, "split": split,
                     "source_group": f"{split}-question-{i // 2}", "split_unit": f"{split}-family-{i // 2}",
                     "prompt": f"{split}-question-{i // 2}"} for i in range(8)]
        calibration, test = rows("calibration"), rows("test")
        logits = [[3., -3.] if r["label"] == 0 else [-3., 3.] for r in calibration]
        first, _ = compare_scores(calibration, test, logits, logits)
        second, _ = compare_scores(calibration, test, logits, [r[::-1] for r in logits])
        self.assertEqual(first["temperature"], second["temperature"])
        self.assertEqual(first["calibrated_thresholds"]["thresholds"], second["calibrated_thresholds"]["thresholds"])
        self.assertEqual(first["binary_at_0_5"]["accuracy"], 1.)
        self.assertEqual(second["binary_at_0_5"]["accuracy"], 0.)
        self.assertFalse(first["calibrated_thresholds"]["product_approved"])
        self.assertEqual(score_rows(test, logits, 1.)[0]["source_group"], "test-family-0")


if __name__ == "__main__":
    unittest.main()
