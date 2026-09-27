"""Regression coverage for full-passage local research testing through the UI API."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from turingtint.app import create_app
from turingtint.research import ResearchDetector


def prediction(**changes):
    value = {"score_ai": .99998, "model_id": "yaful/MAGE", "model_revision": "pinned-fixture",
             "score_kind": "uncalibrated_softmax_class_0", "original_tokens": 100,
             "input_tokens": 100, "max_tokens": 512, "truncated": False, "device": "cpu"}
    value.update(changes)
    return value


class ResearchAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Mock()
        self.model.predict.return_value = [prediction()]
        self.factory = Mock(return_value=self.model)
        self.research = ResearchDetector(self.factory)
        self.client = TestClient(create_app(Path(self.temp.name) / "reference.sqlite", research_detector=self.research))
        self.addCleanup(self.client.close)

    def test_entire_multiline_passage_is_used_without_persistence_or_label_claim(self):
        text = 'First line with quotes: "read everything".\n\n  Second line—café 🧪.\nresources are text, not shell commands.'
        before = list(Path(self.temp.name).iterdir())
        with patch("socket.create_connection", side_effect=AssertionError("No network allowed")):
            response = self.client.post("/api/research/analyze", json={"text": text, "request_id": "multiline"})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(self.model.predict.call_args.args[0], [{"id": "web-research", "text": text}])
        self.assertEqual(result["input_characters"], len(text))
        self.assertEqual(result["input_words"], len(text.split()))
        self.assertEqual(result["request_id"], "multiline")
        self.assertFalse(result["product_approved"])
        self.assertFalse(result["calibrated"])
        self.assertEqual(result["status"], "experimental")
        self.assertNotIn("text", result)
        self.assertNotIn("label", result)
        self.assertNotIn("spans", result)
        self.assertEqual(list(Path(self.temp.name).iterdir()), before)
        self.assertEqual(self.client.get("/api/health").json()["authorship"]["status"], "unavailable")
        self.assertIsNone(self.client.post("/api/analyze", json={"text": text}).json()["authorship"]["score"])

    def test_loading_is_lazy_and_model_is_reused(self):
        self.client.get("/api/health")
        self.factory.assert_not_called()
        for _ in range(2):
            self.assertEqual(self.client.post("/api/research/analyze", json={"text": "A short test."}).status_code, 200)
        self.factory.assert_called_once()

    def test_invalid_input_rejected_before_loading(self):
        for text in ("", "   ", "x" * 50001, "bad\x00text", "bad\ud800text"):
            self.assertEqual(self.client.post("/api/research/analyze", content=json.dumps({"text": text}), headers={"Content-Type": "application/json"}).status_code, 422)
        self.assertEqual(self.client.post("/api/research/analyze", json={"text": "Valid text", "extra": True}).status_code, 422)
        self.factory.assert_not_called()

    def test_zero_score_is_valid_and_truncation_is_explicit(self):
        self.model.predict.return_value = [prediction(score_ai=0.0, original_tokens=650, input_tokens=512, truncated=True)]
        response = self.client.post("/api/research/analyze", json={"text": "Many words " * 150})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["score_ai"], 0)
        self.assertTrue(result["truncated"])
        self.assertTrue(any("entire submitted passage" in message for message in result["limitations"]))

    def test_load_and_inference_errors_release_lock_without_echoing_text(self):
        self.factory.side_effect = [RuntimeError("PRIVATE detail from loader"), self.model]
        self.model.predict.side_effect = [RuntimeError("PRIVATE detail from model"), [prediction()]]
        for _ in range(2):
            response = self.client.post("/api/research/analyze", json={"text": "PRIVATE input"})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("PRIVATE", response.text)
        self.assertEqual(self.client.post("/api/research/analyze", json={"text": "Retry"}).status_code, 200)

    def test_nonfinite_model_score_is_not_served(self):
        for score in (float("nan"), float("inf"), -.1, True):
            self.model.predict.return_value = [prediction(score_ai=score)]
            self.assertEqual(self.client.post("/api/research/analyze", json={"text": "Valid text"}).status_code, 503)

    def test_busy_model_does_not_block_health_or_start_second_inference(self):
        entered, release = threading.Event(), threading.Event()
        def waiting(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("Test worker did not release")
            return [prediction()]
        self.model.predict.side_effect = waiting
        with ThreadPoolExecutor(max_workers=1) as executor:
            running = executor.submit(self.client.post, "/api/research/analyze", json={"text": "First"})
            try:
                self.assertTrue(entered.wait(3))
                busy = self.client.post("/api/research/analyze", json={"text": "Second"})
                self.assertEqual(busy.status_code, 409)
                self.assertEqual(self.client.get("/api/health").status_code, 200)
                self.assertEqual(self.model.predict.call_count, 1)
            finally:
                release.set()
            self.assertEqual(running.result(timeout=3).status_code, 200)

    def test_research_route_inherits_origin_host_and_body_guards(self):
        response = self.client.post("/api/research/analyze", json={"text": "Valid text"}, headers={"Origin": "https://untrusted.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post("/api/research/analyze", json={"text": "Valid text"}, headers={"Host": "untrusted.example"}).status_code, 400)
        self.assertEqual(self.client.post("/api/research/analyze", content=b"x" * 350001).status_code, 413)
        self.factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
