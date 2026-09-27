"""Request privacy, shared GPU contention and explicit provider selection."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fastapi.testclient import TestClient

from turingtint.app import create_app
from turingtint.coaching import GPU_LOCK
from turingtint.research import ResearchBusy, ResearchDetector


class WorkbenchAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.detector = Mock()
        self.detector.analyze.return_value = {"status": "experimental", "validated": False,
                                             "product_approved": False, "assessment": {"label": "inconclusive"}}
        self.coach = Mock()
        self.coach.review.return_value = {"status": "complete", "provider": "local", "suggestions": []}
        self.coach.status.return_value = {"local": {"available": True}, "openai": {"available": False}}
        self.research_factory = Mock()
        self.client = TestClient(create_app(Path(self.temp.name) / "reference.sqlite",
                                            workbench_detector=self.detector, writing_coach=self.coach,
                                            research_detector=ResearchDetector(self.research_factory)))
        self.addCleanup(self.client.close)

    def test_analysis_uses_full_multiline_text_without_calling_cloud_or_coach(self):
        text = "First paragraph.\n\nSecond line with emoji \U0001f9ea and punctuation."
        result = self.client.post("/api/workbench/analyze", json={"text": text, "request_id": "full-text"})
        self.assertEqual(result.status_code, 200)
        self.detector.analyze.assert_called_once_with(text)
        self.coach.review.assert_not_called()
        self.assertEqual(result.json()["request_id"], "full-text")
        self.assertFalse(result.json()["product_approved"])
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_coach_defaults_local_and_only_explicit_provider_changes_that(self):
        self.client.post("/api/coach/review", json={"text": "Review this."})
        self.coach.review.assert_called_once_with("Review this.", provider="local")
        self.coach.review.reset_mock()
        response = self.client.post("/api/coach/review", json={"text": "Review this.", "provider": "openai"})
        self.assertEqual(response.status_code, 200)
        self.coach.review.assert_called_once_with("Review this.", provider="openai")

    def test_rejects_custom_endpoint_and_invalid_text_without_model_calls(self):
        for route in ("/api/workbench/analyze", "/api/coach/review"):
            for text in ("", "  ", "private\x00", "private\ud800", "x" * 50001):
                result = self.client.post(route, content=json.dumps({"text": text}), headers={"Content-Type": "application/json"})
                self.assertEqual(result.status_code, 422)
                self.assertNotIn("private", result.text)
        for payload in ({"text": "Private", "provider": "arbitrary"},
                        {"text": "Private", "base_url": "https://example.com"},
                        {"text": "Private", "api_key": "private-value"}):
            self.assertEqual(self.client.post("/api/coach/review", json=payload).status_code, 422)
        self.detector.analyze.assert_not_called()
        self.coach.review.assert_not_called()

    def test_status_does_not_start_inference(self):
        result = self.client.get("/api/workbench/status")
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()["coaching"]["openai"]["available"])
        self.detector.analyze.assert_not_called()
        self.coach.review.assert_not_called()
        self.research_factory.assert_not_called()

    def test_component_failure_does_not_expose_exception_or_block_health(self):
        self.detector.analyze.side_effect = RuntimeError("PRIVATE passage or credentials")
        self.coach.review.side_effect = RuntimeError("PRIVATE passage or credentials")
        for route in ("/api/workbench/analyze", "/api/coach/review"):
            result = self.client.post(route, json={"text": "Test paragraph"})
            self.assertEqual(result.status_code, 503)
            self.assertNotIn("PRIVATE", result.text)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.detector.analyze.side_effect = ResearchBusy("The local model is busy.")
        self.assertEqual(self.client.post("/api/workbench/analyze", json={"text": "Test paragraph"}).status_code, 409)

    def test_coach_gpu_use_blocks_research_without_loading_another_model(self):
        self.assertTrue(GPU_LOCK.acquire(blocking=False))
        try:
            response = self.client.post("/api/research/analyze", json={"text": "Test paragraph"})
            self.assertEqual(response.status_code, 409)
            self.research_factory.assert_not_called()
            self.assertEqual(self.client.get("/api/health").status_code, 200)
        finally:
            GPU_LOCK.release()

    def test_both_routes_keep_local_origin_and_payload_guards(self):
        for route in ("/api/workbench/analyze", "/api/coach/review"):
            self.assertEqual(self.client.post(route, json={"text": "Private"}, headers={"Origin": "https://example.com"}).status_code, 403)
            self.assertEqual(self.client.post(route, json={"text": "Private"}, headers={"Host": "example.com"}).status_code, 400)
            self.assertEqual(self.client.post(route, content=b"x" * 350001).status_code, 413)
        self.detector.analyze.assert_not_called()
        self.coach.review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
