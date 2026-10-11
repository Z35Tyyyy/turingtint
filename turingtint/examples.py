"""Small, provenance-labeled public fixtures; labels are never model inputs."""
import hashlib
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "evaluation/fixtures/demo-cases.json"


def demo_cases(path=FIXTURES):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        examples = value["examples"]
        if not isinstance(examples, list) or not 1 <= len(examples) <= 12:
            raise ValueError("Invalid examples")
        ids = set()
        for item in examples:
            if item["id"] in ids or not isinstance(item["text"], str) or len(item["text"]) > 8000:
                raise ValueError("Invalid example")
            ids.add(item["id"])
            if hashlib.sha256(item["text"].encode()).hexdigest() != item["text_sha256"]:
                raise ValueError("Example checksum mismatch")
            if item["provenance"]["kind"] not in {"documented_human", "documented_ai", "synthetic_mixed", "writing_fixture"}:
                raise ValueError("Unknown provenance")
        return {"status": "ready", **value}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "unavailable", "examples": [], "reason": "The verified public examples are not installed."}
