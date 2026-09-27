import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fastapi.testclient import TestClient

from turingtint.app import create_app
from turingtint.examples import demo_cases


class ExampleTests(unittest.TestCase):
    def test_cases_have_truthful_provenance_and_no_score_based_selection(self):
        result = demo_cases()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["examples"]), 6)
        self.assertIn("No score-based selection", result["selection_policy"])
        cases = {item["id"]: item for item in result["examples"]}
        self.assertEqual(cases["constructed-mixed"]["text"], cases["hc3-human"]["text"] + "\n\n" + cases["hc3-ai"]["text"])
        self.assertEqual(cases["constructed-mixed"]["provenance"]["kind"], "synthetic_mixed")
        for case in result["examples"]:
            self.assertEqual(hashlib.sha256(case["text"].encode()).hexdigest(), case["text_sha256"])
            self.assertNotIn("score_ai", case)
            self.assertTrue(case["expected_behavior"])
            if case["id"] in {"hc3-human", "hc3-ai", "student-human", "constructed-mixed"}:
                self.assertTrue(case["provenance"]["license"])
                self.assertTrue(case["provenance"]["attribution"])

    def test_missing_or_tampered_examples_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "examples.json"
            self.assertEqual(demo_cases(path)["status"], "unavailable")
            fixture = demo_cases()
            fixture["examples"][0]["text"] += "changed"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            self.assertEqual(demo_cases(path)["status"], "unavailable")

    def test_loading_examples_never_starts_model_inference(self):
        detector, coach = Mock(), Mock()
        with TestClient(create_app(workbench_detector=detector, writing_coach=coach)) as client:
            response = client.get("/api/examples")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["examples"]), 6)
            detector.analyze.assert_not_called()
            coach.review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
