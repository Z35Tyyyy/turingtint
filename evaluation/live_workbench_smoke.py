"""Opt-in real browser smoke against an already running local workbench.

This is deliberately outside the routine evaluation protocol: it uses the GPU.
Run only after its exclusive inference slot has been allocated. No responses are
mocked and no examples or revisions are selected using detector outcomes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CASE_IDS = (
    "hc3-human", "hc3-ai", "student-human", "constructed-mixed",
    "assistant-challenge", "revision-practice",
)
LABELS = {
    "ai_leaning": "AI-leaning model signal",
    "human_leaning": "Human-leaning model signal",
    "inconclusive": "Inconclusive",
}
POST_PATHS = {"/api/workbench/analyze", "/api/analyze", "/api/coach/review"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def anchored(edit, text):
    start, end = edit.get("start"), edit.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        return False
    try:
        raw = text.encode("utf-16-le")
        return end * 2 <= len(raw) and raw[start * 2:end * 2].decode("utf-16-le") == edit.get("quote")
    except UnicodeError:
        return False


def run(base_url, output, deadline_seconds=1200):
    from playwright.sync_api import sync_playwright

    origin = urlsplit(base_url)
    if (origin.scheme != "http" or origin.hostname not in {"127.0.0.1", "localhost", "::1"}
            or origin.username or origin.password or origin.query or origin.fragment
            or origin.path not in {"", "/"}):
        raise ValueError("The smoke test requires an HTTP loopback origin without credentials or a path.")
    base_url = base_url.rstrip("/")
    output = output.resolve()
    output.relative_to((ROOT / "outputs/reviews").resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    screenshot_dir = output.with_suffix("")
    started = time.monotonic()
    receipt = {
        "schema_version": 1, "status": "running", "started_at": utc_now(),
        "base_url": base_url, "script_sha256": sha256(Path(__file__).read_bytes()),
        "fixture_file_sha256": sha256((ROOT / "evaluation/fixtures/demo-cases.json").read_bytes()),
        "python": sys.version, "playwright": version("playwright"),
        "case_order": list(CASE_IDS), "maximum_workbench_requests": 8,
        "maximum_coach_requests": 1, "deadline_seconds": deadline_seconds,
        "scope": "Real local UI smoke using synthetic and licensed public reference cases; not independent accuracy validation.",
        "selection_policy": "All six fixed IDs in order, then revision-practice with the first anchored, nonempty, non-withheld rewrite in returned order. Never select by detector outcomes.",
        "steps": [], "checks": [], "failures": [], "external_requests": [],
        "page_errors": [], "network": [], "served_assets": {},
    }
    # Exclusive creation preserves earlier successes and failures. Use a new
    # output name for an explicitly authorized later iteration.
    with output.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    requests = {}
    stage = {"name": "startup"}
    examples = {}

    def save():
        receipt["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        pending = output.with_suffix(".pending.json")
        pending.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        pending.replace(output)

    def timeout_ms(maximum):
        remaining = deadline_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("The overall live-smoke deadline was reached; no further inference was scheduled.")
        return max(1, int(min(maximum, remaining * 1000)))

    def check(name, passed, detail=None):
        result = {"stage": stage["name"], "name": name, "passed": bool(passed)}
        if detail is not None:
            result["detail"] = detail
        receipt["checks"].append(result)
        if not passed:
            receipt["failures"].append(result)

    def observe_request(request):
        path = urlsplit(request.url).path
        if request.method != "POST" or path not in POST_PATHS:
            return
        payload = request.post_data_json
        key = (path, payload.get("request_id"))
        record = {"stage": stage["name"], "path": path, "request_id": payload.get("request_id"),
                  "requested_at": utc_now(), "payload_fields": sorted(payload),
                  "text_sha256": sha256(payload.get("text", "")),
                  "input_characters": len(payload.get("text", "")),
                  "provider": payload.get("provider")}
        requests[key] = (record, time.monotonic())
        receipt["network"].append(record)

    def observe_response(response):
        path = urlsplit(response.url).path
        try:
            if response.request.method == "POST" and path in POST_PATHS:
                payload = response.request.post_data_json
                record, sent = requests[(path, payload.get("request_id"))]
                record.update(http_status=response.status, response=response.json(),
                              elapsed_ms=round((time.monotonic() - sent) * 1000))
            elif path in {"/", "/static/app.js", "/static/styles.css", "/api/examples", "/api/workbench/status"}:
                receipt["served_assets"][path] = {"http_status": response.status, "body_sha256": sha256(response.body())}
                if path == "/api/examples":
                    result = response.json()
                    receipt["examples_selection_policy"] = result.get("selection_policy")
                    examples.update({item["id"]: item for item in result.get("examples", [])})
                elif path == "/api/workbench/status":
                    receipt["capabilities"] = response.json()
        except Exception as exc:
            receipt["failures"].append({"stage": stage["name"], "name": "response_capture", "path": path, "error": str(exc)})

    def capture_ui(page):
        return page.evaluate("""() => {
          const text = id => document.getElementById(id)?.textContent || '';
          return {assessment: text('assessment-label'), summary: text('assessment-summary'),
            model_signals: text('model-signals'), input_details: text('input-details'),
            case_kind: text('case-kind'), coverage: text('coverage-note'), length_note: text('length-note'),
            detector_error: text('detector-error'), coach_error: text('coach-error'),
            source_error: text('source-error'), coach_status: text('coach-status'),
            coach_summary: text('coach-summary'), revision_cards: text('revision-cards'),
            comparison_visible: !document.getElementById('comparison').hidden,
            comparison: text('comparison'), annotated_text: text('annotated-text')};
        }""")

    def select_case(page, case_id):
        fixture = examples[case_id]
        if sha256(fixture["text"]) != fixture["text_sha256"]:
            raise ValueError(f"Live example {case_id} failed its declared text hash.")
        page.locator("#example-case").select_option(case_id)
        page.locator("#example").click()
        if page.locator("#passage").input_value() != fixture["text"]:
            raise ValueError(f"The UI did not load the exact text of {case_id}.")
        return fixture

    def analyze(page, case_id, name, feedback):
        timeout_ms(1)
        stage["name"] = name
        fixture = examples[case_id]
        page.locator("#include-feedback").set_checked(feedback)
        if feedback:
            page.locator("#coach-provider").select_option("local")
        submitted = page.locator("#passage").input_value()
        step = {"name": name, "case_id": case_id, "feedback": feedback, "started_at": utc_now(),
                "source_text_sha256": fixture["text_sha256"], "submitted_text_sha256": sha256(submitted),
                "submitted_characters": len(submitted), "submitted_words": len(submitted.split()),
                "modified_fixture": submitted != fixture["text"], "provenance": fixture["provenance"]}
        receipt["steps"].append(step)
        before_network = len(receipt["network"])
        save()
        print(json.dumps({"stage": name, "status": "starting", "feedback": feedback}), flush=True)
        step_started = time.monotonic()
        try:
            page.locator("#analyze").click(timeout=timeout_ms(10000))
            page.wait_for_function("""() => document.getElementById('workspace').getAttribute('aria-busy') === 'false'
              && !document.getElementById('analyze').disabled && !document.getElementById('results').hidden""",
                                   timeout=timeout_ms(330000 if feedback else 150000))
            step["wall_elapsed_ms"] = round((time.monotonic() - step_started) * 1000)
            with page.expect_download(timeout=timeout_ms(10000)) as event:
                page.locator("#export").click()
            report = json.loads(Path(event.value.path()).read_text(encoding="utf-8"))
            step.update(report=report, ui=capture_ui(page))
            network = receipt["network"][before_network:]
            expected_paths = {"/api/workbench/analyze": 1, "/api/analyze": 1, "/api/coach/review": int(feedback)}
            check("exact_request_counts", all(sum(item["path"] == path for item in network) == count for path, count in expected_paths.items()), expected_paths)
            check("exact_submitted_text", report.get("text") == submitted and all(item["text_sha256"] == sha256(submitted) for item in network))
            check("provenance_not_sent_to_models", all(set(item["payload_fields"]) == ({"text", "request_id", "provider"} if item["path"] == "/api/coach/review" else {"text", "request_id"}) for item in network))
            expected_status = {"workbench": "complete", "source": "complete", "coaching": "complete" if feedback else "skipped"}
            check("components_completed", report.get("component_status") == expected_status, report.get("component_status"))
            result = report.get("workbench") or {}
            check("experimental_only", result.get("status") == "experimental" and result.get("validated") is False and result.get("product_approved") is False)
            check("model_result_rendered", step["ui"]["assessment"] == LABELS.get(result.get("assessment", {}).get("label")))
            check("original_text_preserved_in_highlights", step["ui"]["annotated_text"] == submitted)
            check("input_character_count", result.get("input", {}).get("characters") == len(submitted))
            step["observed_label"] = result.get("assessment", {}).get("label")
            step["known_fixture_kind"] = fixture["provenance"]["kind"]
            # These observations are recorded without imposing a desired model
            # outcome or treating a constructed mixture as a sentence truth set.
            kind, prediction = step["known_fixture_kind"], step["observed_label"]
            step["origin_diagnostic"] = (
                "human_reference_flagged_ai" if kind == "documented_human" and prediction == "ai_leaning" else
                "ai_reference_flagged_human" if kind == "documented_ai" and prediction == "human_leaning" else
                "abstained" if prediction == "inconclusive" else "recorded_without_accuracy_claim")
            screenshot = screenshot_dir / f"{len(receipt['steps']):02d}-{name}.png"
            page.screenshot(path=str(screenshot), full_page=True, timeout=timeout_ms(10000))
            step["screenshot"] = str(screenshot.relative_to(ROOT))
            print(json.dumps({"stage": name, "status": report.get("component_status"), "label": step["observed_label"], "wall_elapsed_ms": step["wall_elapsed_ms"]}), flush=True)
            return step
        except Exception as exc:
            step["error"] = f"{type(exc).__name__}: {exc}"
            step["wall_elapsed_ms"] = round((time.monotonic() - step_started) * 1000)
            try:
                step["ui"] = capture_ui(page)
                screenshot = screenshot_dir / f"{len(receipt['steps']):02d}-{name}-failure.png"
                page.screenshot(path=str(screenshot), full_page=True, timeout=5000)
                step["screenshot"] = str(screenshot.relative_to(ROOT))
            except Exception:
                pass
            raise
        finally:
            save()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            receipt["browser"] = browser.version
            context = browser.new_context(viewport={"width": 1440, "height": 1100}, accept_downloads=True)

            def restrict(route):
                if not route.request.url.startswith(base_url + "/"):
                    receipt["external_requests"].append(route.request.url)
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", restrict)
            page = context.new_page()
            page.set_default_timeout(10000)
            page.on("request", observe_request)
            page.on("response", observe_response)
            page.on("pageerror", lambda error: receipt["page_errors"].append(str(error)))
            page.goto(base_url, wait_until="networkidle", timeout=timeout_ms(20000))
            check("all_fixed_examples_available", all(case_id in examples for case_id in CASE_IDS))
            if not all(case_id in examples for case_id in CASE_IDS):
                raise RuntimeError("Live server does not expose all six fixed cases; no inference was scheduled.")
            check("no_automatic_inference", not receipt["network"])
            check("local_coach_default", page.locator("#coach-provider").input_value() == "local")
            for case_id in CASE_IDS:
                select_case(page, case_id)
                analyze(page, case_id, f"fast-{case_id}", False)

            select_case(page, "revision-practice")
            original = analyze(page, "revision-practice", "revision-original-with-coach", True)
            original_text = original["report"]["text"]
            coaching = original["report"].get("coaching") or {}
            suggestions = coaching.get("suggestions", [])
            candidates = [(index, edit) for index, edit in enumerate(suggestions)
                          if anchored(edit, original_text) and isinstance(edit.get("rewrite"), str)
                          and edit["rewrite"].strip() and edit.get("rewrite_withheld") is not True]
            stage["name"] = "revision-preview-and-apply"
            check("concrete_anchored_revision_available", bool(candidates), {"suggestion_count": len(suggestions)})
            if candidates:
                index, edit = candidates[0]
                receipt["selected_revision"] = {"returned_index": index, "selection_rule": "first applicable suggestion in returned order", **edit}
                page.get_by_role("button", name="Review this change", exact=True).first.click()
                highlighted = "".join(page.locator("#annotated-text .revision-quote").all_text_contents())
                check("preview_exact_quote", page.locator("#preview-original").text_content() == edit["quote"] and highlighted == edit["quote"])
                check("preview_exact_rewrite", page.locator("#preview-proposed").text_content() == edit["rewrite"])
                check("preview_does_not_edit_input", page.locator("#passage").input_value() == original_text)
                page.screenshot(path=str(screenshot_dir / "revision-preview.png"), full_page=True, timeout=timeout_ms(10000))
                original_bytes = original_text.encode("utf-16-le")
                expected = (original_bytes[:edit["start"] * 2].decode("utf-16-le") + edit["rewrite"]
                            + original_bytes[edit["end"] * 2:].decode("utf-16-le"))
                page.locator("#apply-revision").click()
                check("apply_replaces_only_the_anchored_quote", page.locator("#passage").input_value() == expected)
                check("edited_fixture_labeled_modified", "Modified text" in page.locator("#case-kind").inner_text())
                revised = analyze(page, "revision-practice", "revision-after-edit-fast", False)
                comparison = revised["report"].get("comparison") or {}
                check("comparison_uses_exact_versions", comparison.get("original", {}).get("text") == original_text and comparison.get("revised", {}).get("text") == expected)
                check("comparison_is_visible", revised["ui"]["comparison_visible"])
                counts = {
                    "comparison-original-characters": len(original_text), "comparison-revised-characters": len(expected),
                    "comparison-original-words": len(original_text.split()), "comparison-revised-words": len(expected.split()),
                }
                check("comparison_counts_exact", all(page.locator(f"#{key}").inner_text().replace(",", "") == str(value) for key, value in counts.items()), counts)
                original_input = original["report"].get("workbench", {}).get("input", {})
                revised_input = revised["report"].get("workbench", {}).get("input", {})
                if original_input.get("context_lengths_supported") is False or revised_input.get("context_lengths_supported") is False:
                    rows = page.locator(".comparison-models tbody tr").all_text_contents()
                    check("unsupported_lengths_not_compared", bool(rows) and all("Not comparable" in row and "Signal changed" not in row for row in rows))
                    check("comparison_explains_length_eligibility", "not comparable" in page.locator("#comparison-status").inner_text().lower())
                if revised_input.get("context_lengths_supported") is False:
                    check("short_length_reason_prominent", page.locator("#length-note").is_visible() and str(revised_input.get("minimum_context_words")) in revised["ui"]["length_note"])
                receipt["revision_outcome"] = {"original_sha256": sha256(original_text), "revised_sha256": sha256(expected),
                                                "original_label": original["observed_label"], "revised_label": revised["observed_label"],
                                                "note": "No score improvement or authorship change is required or implied."}
            else:
                receipt["revision_outcome"] = {"status": "not_applied", "reason": "No grounded concrete rewrite was returned; the failure is preserved without substituting another example."}
            stage["name"] = "final_checks"
            check("no_external_page_requests", not receipt["external_requests"], receipt["external_requests"])
            check("no_page_errors", not receipt["page_errors"], receipt["page_errors"])
            check("no_browser_storage", page.evaluate("localStorage.length + sessionStorage.length") == 0)
            check("inference_budget_respected", sum(item["path"] == "/api/workbench/analyze" for item in receipt["network"]) <= 8 and sum(item["path"] == "/api/coach/review" for item in receipt["network"]) <= 1)
            browser.close()
        receipt["status"] = "completed_with_failures" if receipt["failures"] else "complete"
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["failures"].append({"stage": stage["name"], "error": f"{type(exc).__name__}: {exc}"})
    finally:
        receipt["finished_at"] = utc_now()
        save()
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Perform real local inference after an exclusive GPU slot has been allocated.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/reviews/live-workbench-v1.json")
    parser.add_argument("--deadline-seconds", type=int, default=1200)
    args = parser.parse_args()
    if not args.run:
        parser.error("Pass --run only after the GPU slot is available; this script performs real inference.")
    if not 60 <= args.deadline_seconds <= 1800:
        parser.error("Use a bounded deadline between 60 and 1800 seconds.")
    try:
        receipt = run(args.base_url, args.output, args.deadline_seconds)
    except Exception as exc:
        print(json.dumps({"status": "not_started", "error": f"{type(exc).__name__}: {exc}"}), flush=True)
        return 1
    print(json.dumps({"status": receipt["status"], "steps": len(receipt["steps"]),
                      "failures": len(receipt["failures"]), "output": str(args.output)}), flush=True)
    return 0 if receipt["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
