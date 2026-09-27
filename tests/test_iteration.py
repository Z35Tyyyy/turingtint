"""Evidence-loop tests use temporary projects and no model downloads or network."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from iteration.runner import MAX_DIAGNOSTIC_BYTES, MAX_OUTPUT_BYTES, OUTPUT_READ_BYTES, ProtocolError, fingerprints, load_protocol, run, status


class IterationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.state = self.root / ".iteration"
        (self.root / "implementation.py").write_text("VERSION = 1\n", encoding="utf-8")
        (self.root / "inputs.txt").write_text("fixed independent input\n", encoding="utf-8")
        self.check = self.root / "check.py"
        self.write_check("passed")
        self.protocol = {
            "version": 1,
            "allowed_scripts": ["check.py"],
            "implementation_paths": ["implementation.py"],
            "input_paths": ["inputs.txt"],
            "checks": [{"id": "software", "script": "check.py", "args": [], "timeout_seconds": 5, "output": "json"}],
            "gates": [{"id": "software_gate", "description": "Functional behavior must pass.", "check_ids": ["software"]}],
            "review_slots": [],
        }
        self.protocol_path = self.root / "protocol.json"
        self.save_protocol()

    def write_check(self, state):
        self.check.write_text("import json\nprint(json.dumps(" + repr({"status": state, "summary": "Fixture verification", "evidence": [{"fixture": "local"}]}) + "))\n", encoding="utf-8")

    def save_protocol(self):
        self.protocol_path.write_text(json.dumps(self.protocol), encoding="utf-8")

    def execute(self, **kwargs):
        return run(self.root, self.protocol_path, self.state, **kwargs)

    def review(self, decision="approve", **extra):
        subject = fingerprints(self.root, load_protocol(self.root, self.protocol_path), self.state)["subject_sha256"]
        (self.root / "review.md").write_text("Reviewed the evidence and implementation independently.\n", encoding="utf-8")
        record = {"slot": "evaluation", "reviewer_id": "reviewer-one", "independent": True, "subject_sha256": subject, "decision": decision, "summary": "Independent review fixture", "evidence_paths": ["review.md"], **extra}
        path = self.root / "reviews.json"
        path.write_text(json.dumps({"version": 1, "reviews": [record]}), encoding="utf-8")
        return path

    def require_review(self):
        self.protocol["review_slots"] = [{"id": "evaluation"}]
        self.save_protocol()

    def test_passing_checks_promote_with_fingerprinted_evidence(self):
        result = self.execute(max_iterations=5)
        self.assertEqual(result["decision"], "promote")
        self.assertEqual(result["iterations"], 1)
        report = status(self.state)["latest"]
        self.assertEqual(len(report["fingerprints"]["subject_sha256"]), 64)
        self.assertEqual(report["checks"][0]["evidence"], [{"fixture": "local"}])
        self.assertEqual(report["gates"][0]["status"], "passed")
        self.assertNotIn("accuracy", report)

    def test_failure_resolves_only_after_pass_and_reopens_on_regression(self):
        self.write_check("failed")
        self.assertEqual(self.execute()["decision"], "block")
        self.assertEqual(status(self.state)["issue_counts"]["open"], 2)
        self.write_check("passed")
        self.assertEqual(self.execute()["decision"], "promote")
        self.write_check("blocked")
        self.assertEqual(self.execute()["decision"], "block")
        issue = next(item for item in status(self.state)["open_issues"] if item["id"] == "check:software")
        self.assertEqual(issue["status"], "reopened")
        self.assertEqual([item["status"] for item in issue["history"]], ["open", "resolved", "reopened"])
        self.assertNotIn("resolution_evidence", issue)

    def test_timeout_fails_and_terminates_check(self):
        self.check.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        self.protocol["checks"][0]["timeout_seconds"] = 0.15
        self.save_protocol()
        started = time.monotonic()
        result = self.execute(max_seconds=10)
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual(result["decision"], "block")
        self.assertTrue(status(self.state)["latest"]["checks"][0]["timed_out"])

    def test_total_budget_blocks_checks_that_cannot_start(self):
        self.check.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        self.protocol["checks"].append({"id": "later", "script": "check.py"})
        self.save_protocol()
        result = self.execute(max_seconds=0.15)
        self.assertEqual(result["decision"], "block")
        report = status(self.state)["latest"]
        self.assertEqual(report["checks"][1]["status"], "blocked")
        self.assertNotIn("argv", report["checks"][1])

    def test_nonzero_exit_cannot_be_overridden_by_pass_json(self):
        self.check.write_text("import json\nprint(json.dumps({'status': 'passed', 'summary': 'false success'}))\nraise SystemExit(3)\n", encoding="utf-8")
        self.assertEqual(self.execute()["decision"], "block")
        self.assertEqual(status(self.state)["latest"]["checks"][0]["exit_code"], 3)

    def test_malformed_json_and_nonfinite_numbers_fail_closed(self):
        for output in ("not json", '{"status":"passed","summary":"invalid metric","score":NaN}'):
            with self.subTest(output=output):
                self.check.write_text("print(" + repr(output) + ")\n", encoding="utf-8")
                self.assertEqual(self.execute()["decision"], "block")

    def test_empty_release_gate_cannot_pass_on_software_success(self):
        self.protocol["gates"].append({"id": "heldout_accuracy", "description": "Independent empirical accuracy evidence is required.", "check_ids": []})
        self.save_protocol()
        result = self.execute(max_iterations=10)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["stop_reason"], "no_progress")
        self.assertEqual(result["iterations"], 2)
        self.assertIn("gate:heldout_accuracy", result["blocking_issues"])

    def test_removing_failed_gate_does_not_erase_unresolved_issue(self):
        self.protocol["gates"].append({"id": "heldout_accuracy", "description": "Need independent evidence.", "check_ids": []})
        self.save_protocol()
        self.execute()
        self.protocol["gates"].pop()
        self.save_protocol()
        self.assertIn("gate:heldout_accuracy", self.execute()["blocking_issues"])

    def test_review_is_required_and_stale_review_is_rejected(self):
        self.require_review()
        self.assertEqual(self.execute()["decision"], "block")
        reviews = self.review()
        self.assertEqual(self.execute(reviews_path=reviews)["decision"], "promote")
        (self.root / "inputs.txt").write_text("new test corpus\n", encoding="utf-8")
        self.assertEqual(self.execute(reviews_path=reviews)["decision"], "block")
        review = status(self.state)["latest"]["reviews"][0]
        self.assertIn("different", review["summary"])

    def test_review_needs_real_evidence_and_independence_attestation(self):
        self.require_review()
        reviews = self.review(evidence_paths=["missing.md"])
        self.assertEqual(self.execute(reviews_path=reviews)["decision"], "block")
        reviews = self.review(independent=False)
        self.assertEqual(self.execute(reviews_path=reviews)["decision"], "block")

    def test_review_findings_require_explicit_resolution(self):
        self.require_review()
        reviews = self.review("request_changes", findings=[{"id": "leakage", "summary": "Split leakage remains."}])
        self.assertIn("review:evaluation:leakage", self.execute(reviews_path=reviews)["blocking_issues"])
        reviews = self.review()
        self.assertIn("review:evaluation:leakage", self.execute(reviews_path=reviews)["blocking_issues"])
        reviews = self.review(resolved_findings=["leakage"])
        self.assertEqual(self.execute(reviews_path=reviews)["decision"], "promote")

    def test_same_reviewer_cannot_fill_two_required_independent_slots(self):
        self.require_review()
        self.protocol["review_slots"].append({"id": "privacy"})
        self.save_protocol()
        reviews = self.review()
        bundle = json.loads(reviews.read_text(encoding="utf-8"))
        bundle["reviews"].append({**bundle["reviews"][0], "slot": "privacy"})
        reviews.write_text(json.dumps(bundle), encoding="utf-8")
        self.assertEqual(self.execute(reviews_path=reviews)["decision"], "block")
        self.assertTrue(all(item["status"] == "blocked" for item in status(self.state)["latest"]["reviews"]))

    def test_subject_mutation_during_checks_invalidates_success(self):
        self.check.write_text("from pathlib import Path\nimport json\nPath('inputs.txt').write_text('mutated')\nprint(json.dumps({'status':'passed','summary':'check passed'}))\n", encoding="utf-8")
        result = self.execute()
        self.assertEqual(result["decision"], "block")
        self.assertIn("integrity:subject_changed", result["blocking_issues"])

    def test_protocol_rejects_unallowlisted_scripts_and_root_escape(self):
        self.protocol["allowed_scripts"] = []
        self.save_protocol()
        with self.assertRaises(ProtocolError):
            self.execute()
        self.protocol["allowed_scripts"] = ["../outside.py"]
        self.save_protocol()
        with self.assertRaises(ProtocolError):
            self.execute()

    def test_optional_failure_does_not_block_configured_release(self):
        (self.root / "optional.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
        self.protocol["allowed_scripts"].append("optional.py")
        self.protocol["checks"].append({"id": "optional", "script": "optional.py", "required": False, "output": "exit_code"})
        self.save_protocol()
        self.assertEqual(self.execute()["decision"], "promote")
        self.assertFalse(status(self.state)["open_issues"][0]["blocking"])

    def test_check_in_excluded_state_cannot_bypass_fingerprinting(self):
        self.state.mkdir()
        (self.state / "check.py").write_text(self.check.read_text(encoding="utf-8"), encoding="utf-8")
        self.protocol["allowed_scripts"] = [".iteration/check.py"]
        self.protocol["checks"][0]["script"] = ".iteration/check.py"
        self.save_protocol()
        with self.assertRaises(ProtocolError):
            self.execute()

    def test_excessive_output_fails_closed(self):
        self.check.write_text("print('x' * (1024 * 1024 + 1))\n", encoding="utf-8")
        self.assertEqual(self.execute()["decision"], "block")
        self.assertIn("1 MiB", status(self.state)["latest"]["checks"][0]["summary"])

    def test_runaway_stdout_and_stderr_are_killed_before_timeout_without_temp_files(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                self.check.write_text("import os, sys\nchunk = b'x' * 65536\nwhile True:\n    os.write(sys." + stream + ".fileno(), chunk)\n", encoding="utf-8")
                self.protocol["checks"][0]["timeout_seconds"] = 20
                self.save_protocol()
                started = time.monotonic()
                with mock.patch("tempfile.TemporaryFile", side_effect=AssertionError("Check output must not write temporary files")):
                    self.assertEqual(self.execute(max_seconds=25)["decision"], "block")
                self.assertLess(time.monotonic() - started, 8)
                result = status(self.state)["latest"]["checks"][0]
                self.assertEqual(result["output_limit_exceeded"], stream)
                self.assertNotIn("timed_out", result)
                self.assertGreater(result["output_bytes_read"][stream], MAX_OUTPUT_BYTES)
                self.assertLessEqual(result["output_bytes_read"][stream], MAX_OUTPUT_BYTES + OUTPUT_READ_BYTES)
                self.assertLessEqual(result["output_bytes_retained"]["stdout"], MAX_OUTPUT_BYTES)
                self.assertLessEqual(result["output_bytes_retained"]["stderr"], MAX_DIAGNOSTIC_BYTES)

    def test_both_streams_drain_without_a_pipe_capacity_deadlock(self):
        self.check.write_text("import os\nfor _ in range(64):\n    os.write(1, b'o' * 4096)\n    os.write(2, b'e' * 4096)\n", encoding="utf-8")
        self.protocol["checks"][0]["output"] = "exit_code"
        self.save_protocol()
        self.assertEqual(self.execute()["decision"], "promote")
        result = status(self.state)["latest"]["checks"][0]
        self.assertEqual(result["output_bytes_read"], {"stdout": 262144, "stderr": 262144})
        self.assertEqual(len(result["diagnostic"]), MAX_DIAGNOSTIC_BYTES)

    def test_inherited_pipe_handles_do_not_extend_the_check_deadline(self):
        child_pid_path = self.root / "descendant.pid"
        self.check.write_text("import subprocess, sys\nfrom pathlib import Path\nchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\nPath('descendant.pid').write_text(str(child.pid))\n", encoding="utf-8")
        self.protocol["checks"][0]["timeout_seconds"] = 0.2
        self.save_protocol()
        started = time.monotonic()
        try:
            self.assertEqual(self.execute()["decision"], "block")
            self.assertLess(time.monotonic() - started, 8)
            self.assertTrue(status(self.state)["latest"]["checks"][0]["timed_out"])
        finally:
            # A direct parent that has already exited cannot be found by Windows
            # taskkill /T. Explicitly clean this deliberate orphan test fixture.
            if child_pid_path.exists():
                pid = int(child_pid_path.read_text(encoding="utf-8"))
                if os.name == "nt":
                    taskkill = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "taskkill.exe"
                    subprocess.run([str(taskkill), "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=5, check=False)
                else:
                    try:
                        os.kill(pid, 9)
                    except ProcessLookupError:
                        pass

    def test_exclusive_lock_prevents_concurrent_ledger_writers(self):
        self.state.mkdir()
        (self.state / "run.lock").write_text("active", encoding="utf-8")
        with self.assertRaises(ProtocolError):
            self.execute()
        self.assertEqual((self.state / "run.lock").read_text(encoding="utf-8"), "active")


if __name__ == "__main__":
    unittest.main()
