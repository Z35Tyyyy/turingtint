"""Bounded writing-quality checks through the already running local coach API.

No GPU model is loaded here. Fixtures are synthetic and frozen before inference.
These transparent checks are a development regression suite, not a quality score
for arbitrary writing. Semantic review of returned edits remains necessary.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evaluation/coach_quality_fixtures.json"


def judge(case, result):
    failures = []
    if result.get("status") != "complete":
        return ["review_not_complete"]
    if result.get("assessment") is not None or result.get("authorship_opinion") != "not_provided":
        failures.append("unexpected_authorship_opinion")
    suggestions = result.get("suggestions", [])
    text = case["text"]
    checks = case["checks"]
    if len(suggestions) < checks.get("minimum_edits", 0):
        failures.append("missing_useful_edit")
    if len(suggestions) > checks.get("maximum_edits", 2):
        failures.append("unnecessary_edits")
    rewrites = []
    for edit in suggestions:
        try:
            quote = text.encode("utf-16-le")[edit["start"] * 2:edit["end"] * 2].decode("utf-16-le")
            if quote != edit["quote"] or not quote:
                failures.append("invalid_exact_anchor")
        except (KeyError, UnicodeError, TypeError):
            failures.append("invalid_exact_anchor")
            continue
        rewrite = edit.get("rewrite", "")
        if rewrite:
            rewrites.append((quote, rewrite))
            if "[" in rewrite or "]" in rewrite:
                failures.append("placeholder_instead_of_edit")
            if not re.search(r"[.!?][\"'’”]?$", rewrite.strip()):
                failures.append("incomplete_rewrite")
            if checks.get("preserve_quoted_numbers") and set(re.findall(r"\d+(?:[.,:]\d+)*", quote)) != set(re.findall(r"\d+(?:[.,:]\d+)*", rewrite)):
                failures.append("changed_numeric_details")
    if checks.get("no_nonempty_rewrite") and rewrites:
        failures.append("invented_completion")
    if "shorter_ratio" in checks and not any(len(new.split()) <= len(old.split()) * checks["shorter_ratio"] for old, new in rewrites):
        failures.append("not_materially_more_concise")
    joined = " ".join(new for _, new in rewrites)
    for pattern in checks.get("forbidden_rewrite_patterns", []):
        if re.search(pattern, joined, re.I):
            failures.append("overclaim_retained")
    if "required_rewrite_pattern" in checks and not re.search(checks["required_rewrite_pattern"], joined, re.I):
        failures.append("missing_qualified_rewrite")
    generated = " ".join([result.get("summary", "")] + [e.get(k, "") for e in suggestions for k in ("issue", "why", "suggestion", "rewrite")])
    for pattern in checks.get("forbidden_generated_patterns", []):
        if re.search(pattern, generated, re.I):
            failures.append("followed_embedded_instruction")
    if "must_edit_sentence" in checks and not any(e.get("sentence_id") == checks["must_edit_sentence"] for e in suggestions):
        failures.append("missed_target_sentence")
    for field in [result.get("summary", "")] + [e.get(k, "") for e in suggestions for k in ("issue", "why", "suggestion")]:
        if not re.search(r"[.!?][\"'’”]?$", field.strip()):
            failures.append("incomplete_feedback_prose")
    return sorted(set(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="*")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.output.exists():
        parser.error("Use a local application port and a new output path.")
    raw = FIXTURES.read_bytes()
    cases = json.loads(raw)["cases"]
    if args.cases:
        unknown = set(args.cases) - {c["id"] for c in cases}
        if unknown:
            parser.error("Unknown fixture IDs")
        cases = [c for c in cases if c["id"] in args.cases]
    report = {"scope": "writing-quality development checks, not authorship validation", "created_at": datetime.now(timezone.utc).isoformat(),
              "fixtures_sha256": hashlib.sha256(raw).hexdigest(),
              "coach_code_sha256": hashlib.sha256((ROOT / "turingtint/coaching.py").read_bytes()).hexdigest(), "cases": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for case in cases:
        request = urllib.request.Request(f"http://127.0.0.1:{args.port}/api/coach/review",
            data=json.dumps({"text":case["text"], "provider":"local"}).encode(), headers={"Content-Type":"application/json"})
        started = time.perf_counter()
        try:
            with opener.open(request, timeout=150) as response:
                result = json.loads(response.read(128000))
        except Exception as error:
            result = {"status":"unavailable", "error_type":type(error).__name__}
        failures = judge(case, result)
        if result.get("coach_code_sha256") != report["coach_code_sha256"]:
            failures.append("server_code_snapshot_mismatch")
        report["cases"].append({"id":case["id"], "text":case["text"], "result":result, "failures":failures,
                                "elapsed_seconds":round(time.perf_counter()-started, 2)})
        report["passed"] = sum(not c["failures"] for c in report["cases"])
        report["evaluated"] = len(report["cases"])
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        print(json.dumps({"id":case["id"], "status":result.get("status"), "failures":failures}), flush=True)


if __name__ == "__main__":
    main()
