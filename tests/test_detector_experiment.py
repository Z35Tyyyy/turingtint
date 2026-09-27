import hashlib
import unittest

from detector_eval.experiment import attach_scores, excerpt, prepare


def record(name, label="human", group=None, text=None):
    text = text or " ".join([name] + ["academic"] * 100)
    return {"id": name, "label": label, "text": text, "source_group": group,
            "prompt_id": group, "generator": "fixture" if label == "ai" else None,
            "content_sha256": hashlib.sha256(text.encode()).hexdigest()}


class FrozenExperimentTests(unittest.TestCase):
    def test_one_excerpt_and_explicit_clipping(self):
        text = " ".join("w" + str(i) for i in range(400))
        result, kind = excerpt(text)
        self.assertEqual(len(result.split()), 250)
        self.assertIn("mid_sentence", kind)
        self.assertIsNone(excerpt("too short"))
        paragraph = " ".join(["word"] * 90)
        self.assertEqual(excerpt("title\n\n" + paragraph)[1], "natural_paragraph")

    def test_linked_removed_duplicate_siblings_cannot_leak(self):
        rows = [record("a", group="question-a"), record("b", "ai", "question-b"), record("c", "ai", "question-c")]
        relations = {"related_source_groups": [{"source_groups": ["question-a", "question-b"]},
                                                {"source_groups": ["question-b", "question-c"]}]}
        output, _ = prepare(rows, relations)
        self.assertEqual(len({r["split_unit"] for r in output}), 1)
        self.assertEqual(len({r["split"] for r in output}), 1)

    def test_stable_order_does_not_imply_known_author(self):
        rows = [record(str(i)) for i in range(60)]
        first, _ = prepare(rows, {})
        second, _ = prepare(list(reversed(rows)), {})
        self.assertEqual(first, second)
        self.assertTrue(all(r["source_group"] is None for r in first))
        self.assertEqual({r["split"] for r in first}, {"train", "calibration", "test"})

    def test_removed_bridge_still_joins_retained_families(self):
        rows = [record("left0", group="left"), record("right0", "ai", "right")]
        output, _ = prepare(rows, {"related_source_groups": [
            {"source_groups": ["removed", "left"]}, {"source_groups": ["removed", "right"]}]})
        self.assertEqual(output[0]["split_unit"], output[1]["split_unit"])

    def test_contradictory_labels_are_not_silently_admitted(self):
        rows = [record("a"), record("b", "ai", text=record("a")["text"])]
        with self.assertRaisesRegex(ValueError, "contradictory"):
            prepare(rows, {})

    def test_contradictory_clips_quarantined_before_split(self):
        prefix = " ".join(["same"] * 260)
        rows = [record("a", text=prefix + " human ending"), record("b", "ai", text=prefix + " ai ending"), record("c")]
        result, stats = prepare(rows, {})
        self.assertEqual([r["id"] for r in result], ["c"])
        self.assertEqual(stats["omitted"]["conflicting_excerpt"], 2)

    def test_content_hash_tampering_rejected(self):
        row = record("a")
        row["text"] += " tampered"
        with self.assertRaisesRegex(ValueError, "hash"):
            prepare([row], {})

    def test_prediction_coverage_and_duplicates(self):
        rows = [{"id": "a", "text": "first"}, {"id": "b", "text": "second"}]
        for predictions in ([{"id": "a", "score_ai": .2}], [{"id": "a", "score_ai": .2}] * 2):
            with self.assertRaises(ValueError):
                attach_scores(rows, predictions)
        predictions = [{"id": r["id"], "score_ai": .1, "text_sha256": hashlib.sha256(r["text"].encode()).hexdigest()} for r in rows]
        self.assertEqual(attach_scores(rows, predictions)[0]["score"], .1)
        predictions[0]["text_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "text hash"):
            attach_scores(rows, predictions)


if __name__ == "__main__":
    unittest.main()
