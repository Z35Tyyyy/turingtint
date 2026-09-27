"""Research adapter contracts; no network/download or trained model is needed."""

from pathlib import Path
from types import SimpleNamespace
import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch

from detector_models.__main__ import read_records
from detector_models.mage import (AI_CLASS, HUMAN_CLASS, MODEL_ID, MODEL_REVISION, SOURCE_REVISION,
                                  PINNED_ARTIFACTS, MageDetector, _torch_version_tuple, validate_records, verify_manifest)


class ModelContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_record_selection_is_explicit_and_preserves_input_order(self):
        source = self.root / "records.jsonl"
        source.write_text('\n'.join(json.dumps(row) for row in [
            {"id": "c", "text": "Third essay", "label": "ai"},
            {"id": "a", "text": "First essay", "label": "human"},
            {"id": "b", "text": "Second essay", "label": "human"}]), encoding="utf-8")
        selected = self.root / "ids.json"
        selected.write_text('["b", "c"]', encoding="utf-8")
        self.assertEqual([row["id"] for row in read_records(source, selected)], ["c", "b"])
        self.assertEqual([row["id"] for row in read_records(source, limit=1)], ["c"])
        selected.write_text('["missing"]', encoding="utf-8")
        with self.assertRaises(ValueError):
            read_records(source, selected)

    def test_invalid_duplicate_or_blank_records_fail(self):
        for records in ([{"id": "a", "text": ""}], [{"id": "a", "text": 9}],
                        [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}],
                        [{"id": 12, "text": "content"}]):
            with self.assertRaises(ValueError):
                validate_records(records)

    def manifest(self):
        files = []
        pins = {}
        for name in PINNED_ARTIFACTS:
            artifact = self.root / name
            artifact.write_bytes(f"fixture {name}".encode())
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            pins[name] = digest
            files.append({"file": name, "bytes": artifact.stat().st_size, "sha256": digest})
        pin_patch = patch("detector_models.mage.PINNED_ARTIFACTS", pins)
        pin_patch.start()
        self.addCleanup(pin_patch.stop)
        data = {"model_id": MODEL_ID, "model_revision": MODEL_REVISION, "source_revision": SOURCE_REVISION,
                "label_mapping": {"0": "ai", "1": "human"}, "license": "Apache-2.0",
                "inference_allowed": False, "files": files}
        (self.root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
        return data

    def test_tampered_artifact_manifest_fails(self):
        manifest = self.manifest()
        verify_manifest(self.root)
        (self.root / "config.json").write_bytes(b"changed weight")
        with self.assertRaises(ValueError):
            verify_manifest(self.root)

    def test_reversed_label_manifest_fails(self):
        manifest = self.manifest()
        manifest["label_mapping"] = {"0": "human", "1": "ai"}
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_manifest(self.root)

    def test_manifest_cannot_omit_duplicate_or_substitute_artifacts(self):
        manifest = self.manifest()
        original = list(manifest["files"])
        for replacement in ([], original[:-1], original + [original[0]]):
            manifest["files"] = replacement
            (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_manifest(self.root)
        manifest["files"] = original
        manifest["inference_allowed"] = True
        (self.root / "model.safetensors").write_bytes(b"unlisted model")
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_manifest(self.root)

    def test_changing_manifest_hash_cannot_relabel_a_different_artifact(self):
        manifest = self.manifest()
        artifact = self.root / "config.json"
        artifact.write_bytes(b"malicious substituted configuration")
        entry = next(item for item in manifest["files"] if item["file"] == "config.json")
        entry.update(bytes=artifact.stat().st_size, sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_manifest(self.root)

    def test_manifest_cannot_read_outside_model_directory(self):
        manifest = self.manifest()
        manifest["files"][0]["file"] = "../outside.txt"
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_manifest(self.root)

    def test_version_and_label_constants_are_explicit(self):
        self.assertEqual(_torch_version_tuple("2.6.0+cu124"), (2, 6, 0))
        self.assertLess(_torch_version_tuple("2.5.1"), (2, 6, 0))
        self.assertEqual((AI_CLASS, HUMAN_CLASS), (0, 1))


@unittest.skipUnless(importlib.util.find_spec("torch"), "PyTorch is optional outside the research environment")
class PredictionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        cls.torch = torch

    def predictor(self, logits):
        torch = self.torch

        class Tokenizer:
            def __call__(self, value, **kwargs):
                if isinstance(value, str):
                    return {"input_ids": list(range(len(value.split()) + 2))}
                lengths = [min(len(text.split()) + 2, kwargs["max_length"]) for text in value]
                width = max(lengths)
                mask = [[1] * count + [0] * (width - count) for count in lengths]
                return {"input_ids": torch.zeros((len(value), width), dtype=torch.long),
                        "attention_mask": torch.tensor(mask)}

        class Model:
            def __call__(self, **kwargs):
                self.global_attention = kwargs["global_attention_mask"]
                return SimpleNamespace(logits=torch.tensor(logits[:len(kwargs["input_ids"])], dtype=torch.float32))

        predictor = MageDetector.__new__(MageDetector)
        predictor.torch = torch
        predictor.tokenizer = Tokenizer()
        predictor.model = Model()
        predictor.device = "cpu"
        predictor.dtype = torch.float32
        predictor.max_tokens = 16
        return predictor

    def test_class_zero_score_and_truncation_are_not_inverted_or_hidden(self):
        predictor = self.predictor([[3, -3], [-3, 3]])
        rows = predictor.predict([{"id": "a", "text": "word " * 30, "label": "human"},
                                  {"id": "b", "text": "A brief paragraph", "label": "ai"}], batch_size=2)
        self.assertGreater(rows[0]["score_ai"], 0.99)
        self.assertLess(rows[1]["score_ai"], 0.01)
        self.assertEqual(rows[0]["original_tokens"], 32)
        self.assertEqual(rows[0]["input_tokens"], 16)
        self.assertTrue(rows[0]["truncated"])
        self.assertFalse(rows[1]["truncated"])
        self.assertNotIn("text", rows[0])
        self.assertNotIn("label", rows[0])
        self.assertEqual(rows[0]["text_sha256"], hashlib.sha256(("word " * 30).encode()).hexdigest())
        self.assertFalse(rows[0]["calibrated"])
        self.assertFalse(rows[0]["product_approved"])
        self.assertTrue((predictor.model.global_attention[:, 0] == 1).all())
        self.assertTrue((predictor.model.global_attention[:, 1:] == 0).all())

    def test_nonfinite_scores_are_not_reported(self):
        predictor = self.predictor([[float("nan"), 0]])
        with self.assertRaises(RuntimeError):
            predictor.predict([{"id": "a", "text": "A sample paragraph"}])


if __name__ == "__main__":
    unittest.main()
