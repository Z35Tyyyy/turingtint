"""Exercise the real pinned dependency's logging failure path without a model."""
import importlib.util
import json
import logging
import subprocess
import sys
import unittest
from unittest.mock import patch

from turingtint.guidance import build_prefix_constraint


class GuidanceImportTests(unittest.TestCase):
    def test_base_import_does_not_import_optional_ml_packages(self):
        code = (
            "import sys,json; import turingtint.guidance; "
            "print(json.dumps([name for name in "
            "('torch','transformers','lmformatenforcer') if name in sys.modules]))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            timeout=10, check=True,
        )
        self.assertEqual(json.loads(result.stdout), [])


@unittest.skipUnless(
    importlib.util.find_spec("lmformatenforcer")
    and importlib.util.find_spec("torch")
    and importlib.util.find_spec("transformers"),
    "Optional guided decoding dependencies are not installed",
)
class GuidancePrivacyTests(unittest.TestCase):
    def tokenizer_data(self, marker):
        from lmformatenforcer.tokenenforcer import TokenEnforcerTokenizerData
        return TokenEnforcerTokenizerData(
            [(0, "{", False), (1, "}", False)],
            lambda _tokens: marker, 2, False, 3,
        )

    def test_forced_internal_error_logs_no_prompt_and_invalid_eos_fails_closed(self):
        import torch
        from turingtint.coaching import WritingCoach

        marker = "SYNTHETIC_PRIVATE_PASSAGE"
        constraint = build_prefix_constraint(
            self.tokenizer_data(marker), {"type": "object"}
        )
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        capture = Capture()
        root = logging.getLogger()
        old_level = root.level
        root.addHandler(capture)
        root.setLevel(logging.DEBUG)
        allowed_results = []
        try:
            def generate(_text):
                with patch.object(
                    constraint.token_enforcer, "_collect_allowed_tokens",
                    side_effect=RuntimeError(marker + " parser failure"),
                ):
                    allowed = constraint(0, torch.tensor([100, 101]))
                allowed_results.append(allowed)
                return '{"assessment":'  # interrupted generation is incomplete

            result = WritingCoach(local_factory=lambda: generate).review(marker)
            # Assert outside the injected generator: WritingCoach intentionally
            # catches every generator failure, including an assertion error.
            self.assertEqual(allowed_results, [[2]])  # dependency fallback is EOS
            self.assertEqual(result["status"], "unavailable")
            self.assertNotIn("assessment", result)
            self.assertNotIn(marker, json.dumps(result))
            logging.getLogger("guidance-test-control").warning("Control logger works")
            self.assertEqual([record.getMessage() for record in records], ["Control logger works"])
            self.assertTrue(all(record.exc_info is None for record in records))
        finally:
            root.removeHandler(capture)
            root.setLevel(old_level)

    def test_constraints_do_not_share_parser_or_generation_state(self):
        import torch

        data = self.tokenizer_data("synthetic decoder")
        first = build_prefix_constraint(data, {"type": "object"})
        second = build_prefix_constraint(data, {"type": "object"})
        self.assertIsNot(first.token_enforcer.root_parser, second.token_enforcer.root_parser)
        self.assertIn(0, first(0, torch.tensor([100])))
        self.assertEqual(second.token_enforcer.prefix_states, {})
        self.assertIn(0, second(0, torch.tensor([200])))
        self.assertNotIn((100,), second.token_enforcer.prefix_states)


if __name__ == "__main__":
    unittest.main()
