"""Regression tests for abstention denominators and independent release evidence."""

import hashlib
import math
import unittest
from dataclasses import FrozenInstanceError

from detector_eval import FrozenThresholds, auroc, evaluate, select_thresholds, wilson_one_sided_bounds


def record(record_id, label, score, *, source_group=None, **metadata):
    return {"id": record_id, "label": label, "score": score, "source_group": source_group, **metadata}


class DetectorMetricTests(unittest.TestCase):
    def setUp(self):
        self.thresholds = FrozenThresholds(.2, .8)

    def calibrated(self):
        return select_thresholds([
            record("cal-human", 0, .1, source_group="cal-human-family", prompt="cal-prompt"),
            record("cal-ai", 1, .9, source_group="cal-ai-family", prompt="cal-prompt", generator="cal-model"),
        ])

    def release_records(self):
        return [record(f"human-{index}", 0, .1, source_group=f"human-family-{index}", prompt="test-prompt", length_bucket="long") for index in range(300)] + [record(f"ai-{index}", 1, .9, source_group=f"ai-family-{index}", prompt="test-prompt", generator="unseen-model", length_bucket="long") for index in range(100)]

    def assert_blocked(self, result, gate):
        self.assertFalse(result["product_approved"])
        self.assertEqual(next(item["status"] for item in result["gates"] if item["id"] == gate), "blocked")

    def test_abstention_denominators_and_precision(self):
        rows = [record(f"{label}-{index}", label, score, source_group=f"family-{label}-{index}") for label in (0, 1) for index, score in enumerate((.9, .5, .1))]
        metrics = evaluate(rows, self.thresholds)["metrics"]
        self.assertEqual(metrics["confusion"], {"tp": 1, "fp": 1, "tn": 1, "fn": 1, "abstain_human": 1, "abstain_ai": 1})
        self.assertAlmostEqual(metrics["human_fpr"], 1 / 3)
        self.assertEqual(metrics["answered_human_fpr"], .5)
        self.assertAlmostEqual(metrics["ai_recall"], 1 / 3)
        self.assertEqual(metrics["ai_precision"], .5)
        self.assertAlmostEqual(metrics["coverage"], 2 / 3)
        self.assertAlmostEqual(metrics["human_coverage"], 2 / 3)
        self.assertAlmostEqual(metrics["ai_coverage"], 2 / 3)
        self.assertAlmostEqual(metrics["brier"], 2.14 / 6)

    def test_uncertain_is_separate_and_boundaries_are_inclusive(self):
        self.assertEqual(self.thresholds.predict(.2), "human")
        self.assertEqual(self.thresholds.predict(.8), "ai")
        self.assertEqual(self.thresholds.predict(.5), "uncertain")
        all_uncertain = evaluate([record("human", 0, .5), record("ai", 1, .5)], FrozenThresholds(None, None))["metrics"]
        self.assertEqual(all_uncertain["human_fpr"], 0)
        self.assertEqual(all_uncertain["ai_recall"], 0)
        self.assertEqual(all_uncertain["coverage"], 0)
        self.assertIsNone(all_uncertain["answered_human_fpr"])
        self.assertIsNone(all_uncertain["ai_precision"])

    def test_empty_and_one_class_inputs_keep_undefined_metrics_null(self):
        metrics = evaluate([], self.thresholds)["metrics"]
        for name in ("human_fpr", "answered_human_fpr", "ai_recall", "ai_precision", "coverage", "brier", "auroc"):
            self.assertIsNone(metrics[name])
        only_human = evaluate([record("human", 0, .1)], self.thresholds)["metrics"]
        self.assertIsNone(only_human["ai_recall"])
        self.assertIsNone(only_human["auroc"])
        self.assertEqual(only_human["human_fpr"], 0)
        only_ai = evaluate([record("ai", 1, .9)], self.thresholds)["metrics"]
        self.assertIsNone(only_ai["human_fpr"])
        self.assertEqual(only_ai["ai_recall"], 1)

    def test_auroc_ties_and_rank_order(self):
        self.assertEqual(auroc([0, 1], [.5, .5]), .5)
        self.assertEqual(auroc([0, 0, 1, 1], [.1, .4, .35, .8]), .75)
        self.assertEqual(auroc([0, 1, 0, 1], [.9, .1, .9, .1]), 0)
        self.assertEqual(auroc([0, 1, 0, 1], [.1, .9, .1, .9]), 1)
        self.assertIsNone(auroc([], []))
        self.assertIsNone(auroc([1, 1], [.2, .8]))

    def test_wilson_is_one_sided_and_zero_trials_are_null(self):
        bound = wilson_one_sided_bounds(0, 300)
        self.assertEqual(bound["method"], "wilson_one_sided")
        self.assertAlmostEqual(bound["upper"], .008937872175, places=10)
        self.assertEqual(bound["lower"], 0)
        self.assertLess(bound["upper"], .01)
        inverse = wilson_one_sided_bounds(300, 300)
        self.assertAlmostEqual(inverse["lower"], 1 - bound["upper"])
        self.assertIsNone(wilson_one_sided_bounds(0, 0)["upper"])
        with self.assertRaises(ValueError):
            wilson_one_sided_bounds(2, 1)

    def test_invalid_nonfinite_scores_labels_and_thresholds_fail(self):
        for score in (math.nan, math.inf, -math.inf, -.01, 1.01, "0.5", True, None):
            with self.subTest(score=score), self.assertRaises(ValueError):
                evaluate([record("invalid", 0, score)], self.thresholds)
        for label in (True, "human", 2, 0.0, None):
            with self.subTest(label=label), self.assertRaises(ValueError):
                evaluate([record("invalid", label, .5)], self.thresholds)
        for human_max, ai_min in ((.8, .2), (.5, .5), (math.nan, .8), (.2, 1.1)):
            with self.subTest(boundaries=(human_max, ai_min)), self.assertRaises(ValueError):
                FrozenThresholds(human_max, ai_min)

    def test_calibration_selects_nonoverlapping_boundaries_with_false_human_cap(self):
        rows = [record("h1", 0, .1, source_group="h1"), record("h2", 0, .4, source_group="h2"), record("a1", 1, .2, source_group="a1"), record("a2", 1, .9, source_group="a2")]
        thresholds = select_thresholds(rows, ai_false_positive_cap=0, human_false_positive_cap=0)
        self.assertEqual(thresholds.ai_min, .9)
        self.assertEqual(thresholds.human_max, .1)
        self.assertEqual(thresholds.selected_on, "calibration")
        with self.assertRaises(FrozenInstanceError):
            thresholds.ai_min = .1
        self.assertEqual(FrozenThresholds.from_dict(thresholds.to_dict()), thresholds)

    def test_no_safe_useful_boundary_abstains_everywhere(self):
        thresholds = select_thresholds([record("h", 0, .5), record("a", 1, .5)])
        self.assertIsNone(thresholds.ai_min)
        self.assertIsNone(thresholds.human_max)

    def test_duplicate_families_do_not_dilute_calibration_false_flags(self):
        rows = [record(f"duplicate-{index}", 0, .1, source_group="one-human-family") for index in range(1000)]
        rows += [record("other-human", 0, .9, source_group="other-human-family"), record("ai", 1, .9, source_group="ai-family")]
        thresholds = select_thresholds(rows)
        self.assertIsNone(thresholds.ai_min)
        self.assertEqual(thresholds.human_max, .1)

    def test_shared_human_and_ai_source_family_is_valid(self):
        thresholds = select_thresholds([record("original", 0, .1, source_group="family"), record("generated", 1, .9, source_group="family")])
        self.assertEqual(thresholds.human_max, .1)
        self.assertEqual(thresholds.ai_min, .9)

    def test_test_selection_and_declared_test_rows_are_rejected(self):
        rows = [record("h", 0, .1), record("a", 1, .9)]
        with self.assertRaises(ValueError):
            select_thresholds(rows, split="test")
        rows[0]["split"] = "test"
        with self.assertRaises(ValueError):
            select_thresholds(rows)

    def test_calibration_test_record_family_and_hash_overlap_are_rejected(self):
        text_hash = hashlib.sha256(b"calibration text").hexdigest()
        thresholds = select_thresholds([record("h", 0, .1, source_group="human-family", text_sha256=text_hash), record("a", 1, .9, source_group="ai-family")])
        for row in (record("h", 0, .2, source_group="new"), record("new", 1, .9, source_group="human-family"), record("new", 0, .2, source_group="new", text_sha256=text_hash)):
            with self.subTest(row=row), self.assertRaises(ValueError):
                evaluate([row], thresholds)

    def test_prompt_disjoint_requirement_is_checked(self):
        thresholds = self.calibrated()
        for prompt in ("cal-prompt", None):
            with self.subTest(prompt=prompt), self.assertRaises(ValueError):
                evaluate([record("test", 0, .1, prompt=prompt)], thresholds, require_prompt_disjoint=True)
        result = evaluate([record("test", 0, .1, prompt="unseen-prompt")], thresholds, require_prompt_disjoint=True)
        self.assertEqual(result["metrics"]["counts"]["records"], 1)

    def test_conflicting_identical_text_and_duplicate_ids_fail(self):
        text_hash = hashlib.sha256(b"identical").hexdigest()
        with self.assertRaises(ValueError):
            evaluate([record("same-id", 0, .1), record("same-id", 0, .1)], self.thresholds)
        with self.assertRaises(ValueError):
            evaluate([record("h", 0, .1, text_sha256=text_hash), record("a", 1, .9, text_sha256=text_hash)], self.thresholds)

    def test_repeated_families_and_exact_duplicates_cannot_inflate_release_size(self):
        rows = self.release_records()
        for row in rows[:300]:
            row["source_group"] = "one-family"
        result = evaluate(rows, self.calibrated(), independent_source_groups_verified=True, unseen_generator_evidence=True)
        self.assertEqual(result["metrics"]["counts"]["human_source_groups"], 1)
        self.assert_blocked(result, "minimum_human_groups")
        rows = self.release_records()
        for row in rows[:300]:
            row["text_sha256"] = hashlib.sha256(b"one repeated human text").hexdigest()
        result = evaluate(rows, self.calibrated(), independent_source_groups_verified=True, unseen_generator_evidence=True)
        self.assertEqual(result["metrics"]["counts"]["human_source_groups"], 1)
        self.assert_blocked(result, "minimum_human_groups")

    def test_release_requires_sample_sizes_and_one_sided_false_positive_bound(self):
        thresholds = self.calibrated()
        rows = self.release_records()
        kwargs = {"independent_source_groups_verified": True, "unseen_generator_evidence": True, "require_prompt_disjoint": True}
        result = evaluate(rows, thresholds, **kwargs)
        self.assertTrue(result["product_approved"])
        self.assert_blocked(evaluate(rows[1:], thresholds, **kwargs), "minimum_human_groups")
        self.assert_blocked(evaluate(rows[:-1], thresholds, **kwargs), "minimum_ai_groups")
        rows[0]["score"] = .95
        result = evaluate(rows, thresholds, **kwargs)
        self.assertLess(result["metrics"]["human_fpr"], .01)
        self.assert_blocked(result, "human_fpr_upper_95")

    def test_missing_independence_and_unseen_generator_evidence_block_good_metrics(self):
        rows = self.release_records()
        thresholds = self.calibrated()
        result = evaluate(rows, thresholds)
        self.assert_blocked(result, "independent_source_groups")
        self.assert_blocked(result, "unseen_generator_evidence")
        rows[0]["source_group"] = None
        result = evaluate(rows, thresholds, independent_source_groups_verified=True, unseen_generator_evidence=True)
        self.assertTrue(result["insufficient_independence"])
        self.assertIsNone(result["metrics"]["human_group_fpr"]["bounds"])
        self.assert_blocked(result, "independent_source_groups")

    def test_predefined_thresholds_and_calibration_metrics_do_not_approve_product(self):
        rows = self.release_records()
        kwargs = {"independent_source_groups_verified": True, "unseen_generator_evidence": True}
        self.assert_blocked(evaluate(rows, self.thresholds, **kwargs), "calibration_provenance")
        self.assert_blocked(evaluate(rows, self.calibrated(), split="calibration", **kwargs), "test_split")

    def test_seen_generator_success_cannot_hide_total_unseen_generator_failure(self):
        rows = self.release_records()
        for row in rows[300:]:
            row["score"] = .1
        rows += [record(f"seen-ai-{index}", 1, .9, source_group=f"seen-ai-family-{index}", generator="cal-model") for index in range(900)]
        result = evaluate(rows, self.calibrated(), independent_source_groups_verified=True, unseen_generator_evidence=True)
        self.assertEqual(result["metrics"]["ai_recall"], .9)
        self.assertEqual(result["metrics"]["ai_group_recall"], .9)
        self.assertEqual(result["unseen_generator_validation"]["unseen-model"]["metrics"]["ai_recall"], 0)
        self.assert_blocked(result, "unseen_generator_evidence")

    def test_every_unseen_generator_needs_its_own_support_and_complete_metadata(self):
        rows = self.release_records()
        rows += [record(f"second-ai-{index}", 1, .9, source_group=f"second-ai-family-{index}", generator="second-unseen-model") for index in range(99)]
        kwargs = {"independent_source_groups_verified": True, "unseen_generator_evidence": True}
        self.assert_blocked(evaluate(rows, self.calibrated(), **kwargs), "unseen_generator_evidence")
        rows = self.release_records()
        rows[300].pop("generator")
        self.assert_blocked(evaluate(rows, self.calibrated(), **kwargs), "unseen_generator_evidence")

    def test_coverage_and_abstention_recall_gates_cannot_be_gamed(self):
        rows = self.release_records()
        for row in rows[300:]:
            row["score"] = .5
        result = evaluate(rows, self.calibrated(), independent_source_groups_verified=True, unseen_generator_evidence=True)
        self.assertEqual(result["metrics"]["ai_recall"], 0)
        self.assert_blocked(result, "ai_recall")
        for row in rows[:300]:
            row["score"] = .5
        result = evaluate(rows, self.calibrated(), independent_source_groups_verified=True, unseen_generator_evidence=True)
        self.assert_blocked(result, "coverage")

    def test_subgroups_are_reported_without_sentence_or_mixed_claims(self):
        rows = [record("h", 0, .1, length_bucket="short", prompt=1), record("a", 1, .9, length_bucket="long", prompt=2, generator="local-model")]
        result = evaluate(rows, self.thresholds)
        self.assertEqual(result["subgroups"]["length_bucket"]["short"]["counts"]["human"], 1)
        self.assertEqual(result["subgroups"]["prompt"]["2"]["ai_recall"], 1)
        self.assertIsNone(result["subgroups"]["generator"]["local-model"]["auroc"])
        self.assertIn("__missing__", result["subgroups"]["generator"])
        self.assertIn("uncertainty is not mixed", result["scope"])


if __name__ == "__main__":
    unittest.main()
