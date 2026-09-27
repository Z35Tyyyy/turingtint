"""Run trusted local checks; keep unsupported release claims blocked.

The protocol is developer-controlled configuration, never model-generated task
text. This is an evidence recorder, not a code sandbox or a self-editing agent.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_OUTPUT_BYTES = 1024 * 1024
OUTPUT_READ_BYTES = 64 * 1024
MAX_DIAGNOSTIC_BYTES = 4000
ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
IGNORED_DIRECTORIES = {".git", "__pycache__", ".venv", "node_modules", ".iteration"}


class ProtocolError(ValueError):
    """The local protocol or evidence is not valid."""


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=_reject_constant)
    except (OSError, ValueError) as exc:
        raise ProtocolError(f"Cannot read JSON from {path}: {exc}") from exc


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _inside(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ProtocolError("Paths must be nonempty project-relative strings.")
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ProtocolError(f"Path escapes the project root: {relative}") from exc
    if must_exist and not path.exists():
        raise ProtocolError(f"Missing project path: {relative}")
    return path


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ProtocolError(f"{field} must be a simple identifier of at most 80 characters.")
    return value


def _number(value: Any, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ProtocolError(f"{field} must be between {minimum} and {maximum}.")
    return float(value)


def load_protocol(root: Path, protocol_path: Path) -> dict[str, Any]:
    protocol = _read_json(protocol_path)
    if not isinstance(protocol, dict) or protocol.get("version") != 1:
        raise ProtocolError("Protocol must be an object with version 1.")
    allowed_keys = {"version", "allowed_scripts", "implementation_paths", "input_paths", "checks", "gates", "review_slots"}
    if set(protocol) - allowed_keys:
        raise ProtocolError(f"Unknown protocol fields: {sorted(set(protocol) - allowed_keys)}")
    for name in ("allowed_scripts", "implementation_paths", "input_paths", "checks", "gates", "review_slots"):
        if not isinstance(protocol.get(name), list):
            raise ProtocolError(f"Protocol {name} must be a list.")
    scripts: set[Path] = set()
    for name in protocol["allowed_scripts"]:
        path = _inside(root, name)
        if not path.is_file() or path.suffix != ".py":
            raise ProtocolError(f"Allowlisted check must be a Python source file: {name}")
        scripts.add(path)
    for name in protocol["implementation_paths"] + protocol["input_paths"]:
        _inside(root, name)
    if not protocol["implementation_paths"]:
        raise ProtocolError("Declare implementation_paths so changes invalidate prior evidence.")
    if not protocol["checks"]:
        raise ProtocolError("At least one check is required; an empty protocol cannot promote.")
    known: dict[str, set[str]] = {}
    for collection in ("checks", "gates", "review_slots"):
        known[collection] = set()
        for item in protocol[collection]:
            if not isinstance(item, dict):
                raise ProtocolError(f"Every {collection} entry must be an object.")
            name = _identifier(item.get("id"), collection + ".id")
            if name in known[collection]:
                raise ProtocolError(f"Duplicate {collection} identifier: {name}")
            known[collection].add(name)
            if not isinstance(item.get("required", True), bool):
                raise ProtocolError(f"{name}.required must be a boolean.")
    for check in protocol["checks"]:
        if set(check) - {"id", "script", "args", "required", "timeout_seconds", "output"}:
            raise ProtocolError(f"Unknown fields in check {check['id']}.")
        if _inside(root, check.get("script")) not in scripts:
            raise ProtocolError(f"Check script is not allowlisted: {check['id']}")
        if not isinstance(check.get("args", []), list) or not all(isinstance(arg, str) and "\x00" not in arg for arg in check.get("args", [])):
            raise ProtocolError(f"{check['id']}.args must be a list of strings.")
        _number(check.get("timeout_seconds", 30), "timeout_seconds", 0.01, 3600)
        if check.get("output", "json") not in {"json", "exit_code"}:
            raise ProtocolError("Check output must be json or exit_code.")
    if not any(check.get("required", True) for check in protocol["checks"]):
        raise ProtocolError("At least one check must be required.")
    for gate in protocol["gates"]:
        if set(gate) - {"id", "description", "check_ids", "required"}:
            raise ProtocolError(f"Unknown fields in gate {gate['id']}.")
        if not isinstance(gate.get("description"), str) or not gate["description"].strip():
            raise ProtocolError("Each gate needs a nonempty description.")
        if not isinstance(gate.get("check_ids"), list) or not all(isinstance(name, str) for name in gate["check_ids"]):
            raise ProtocolError("gate.check_ids must be a list of check identifiers.")
        if set(gate["check_ids"]) - known["checks"]:
            raise ProtocolError(f"Gate {gate['id']} refers to an unknown check.")
    for slot in protocol["review_slots"]:
        if set(slot) - {"id", "required"}:
            raise ProtocolError(f"Unknown fields in review slot {slot['id']}.")
    return protocol


def _file_records(root: Path, paths: list[str], exclude: Path) -> list[dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for entry in paths:
        path = _inside(root, entry)
        candidates = [path] if path.is_file() else path.rglob("*")
        for candidate in candidates:
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root):
                raise ProtocolError(f"Fingerprint path escapes root: {candidate}")
            relative = candidate.relative_to(root)
            if resolved.is_relative_to(exclude) or any(part in IGNORED_DIRECTORIES for part in relative.parts) or candidate.suffix == ".pyc":
                continue
            hasher = hashlib.sha256()
            size = 0
            with candidate.open("rb") as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    hasher.update(chunk)
                    size += len(chunk)
            files[relative.as_posix()] = {"path": relative.as_posix(), "sha256": hasher.hexdigest(), "bytes": size}
    return [files[name] for name in sorted(files)]


def fingerprints(root: Path, protocol: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    for script in protocol["allowed_scripts"]:
        path = _inside(root, script)
        if path.is_relative_to(state_dir) or any(part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts):
            raise ProtocolError("Check scripts cannot be stored in generated or excluded directories.")
    implementation = _file_records(root, protocol["implementation_paths"] + protocol["allowed_scripts"], state_dir)
    inputs = _file_records(root, protocol["input_paths"], state_dir)
    result = {
        "config_sha256": digest(protocol),
        "implementation_sha256": digest(implementation),
        "inputs_sha256": digest(inputs),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python_version": platform.python_version(),
        "implementation_files": implementation,
        "input_files": inputs,
    }
    result["subject_sha256"] = digest({key: value for key, value in result.items() if key not in {"implementation_files", "input_files"}})
    return result


def _kill_process_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        taskkill = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "taskkill.exe"
        try:
            subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _check(root: Path, check: dict[str, Any], seconds_left: float) -> dict[str, Any]:
    result: dict[str, Any] = {"id": check["id"], "required": check.get("required", True), "status": "blocked", "summary": "Total time budget exhausted.", "evidence": []}
    if seconds_left <= 0:
        return result
    timeout = min(check.get("timeout_seconds", 30), seconds_left)
    argv = [sys.executable, str(_inside(root, check["script"])), *check.get("args", [])]
    result["argv"] = argv
    started = time.monotonic()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root)
    environment["PYTHONUTF8"] = "1"
    options: dict[str, Any] = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    process = None
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    bytes_read = {"stdout": 0, "stderr": 0}
    try:
        process = subprocess.Popen(argv, cwd=root, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0, shell=False, **options)
        streams = {"stdout": process.stdout, "stderr": process.stderr}
        # Python 3.12+ supports nonblocking Windows pipes. Fail closed if the
        # runtime cannot provide them; blocking reader threads can remain stuck
        # when a descendant inherits pipe handles after the direct child exits.
        for stream in streams.values():
            os.set_blocking(stream.fileno(), False)
        eof = set()
        deadline = started + timeout
        while True:
            progress = False
            for name, stream in streams.items():
                if name in eof:
                    continue
                chunk = stream.read(OUTPUT_READ_BYTES)
                if chunk is None:
                    continue
                if not chunk:
                    eof.add(name)
                    continue
                progress = True
                bytes_read[name] += len(chunk)
                retained_limit = MAX_OUTPUT_BYTES if name == "stdout" else MAX_DIAGNOSTIC_BYTES
                room = max(0, retained_limit - len(captured[name]))
                captured[name].extend(chunk[:room])
                if bytes_read[name] > MAX_OUTPUT_BYTES:
                    _kill_process_tree(process)
                    result.update(status="failed", summary=f"Check {name} exceeds the 1 MiB runtime output limit.", output_limit_exceeded=name, exit_code=process.returncode)
                    return result
            result["exit_code"] = process.poll()
            if result["exit_code"] is not None and len(eof) == len(streams):
                break
            seconds_remaining = deadline - time.monotonic()
            if seconds_remaining <= 0:
                _kill_process_tree(process)
                result.update(status="failed", summary="Check exceeded its time budget.", timed_out=True, exit_code=process.returncode)
                return result
            if not progress:
                time.sleep(min(0.005, seconds_remaining))
    except OSError as exc:
        result.update(status="failed", summary=f"Could not run check with bounded pipes: {type(exc).__name__}.")
        return result
    finally:
        if process is not None:
            if process.poll() is None:
                _kill_process_tree(process)
            # These are unbuffered, nonblocking pipe handles: closing does not
            # wait for EOF or for inherited handles in a descendant to close.
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        result["duration_seconds"] = round(time.monotonic() - started, 4)
        result["output_bytes_read"] = bytes_read
        result["output_bytes_retained"] = {name: len(data) for name, data in captured.items()}
    output = bytes(captured["stdout"])
    diagnostic = bytes(captured["stderr"])
    # Store small diagnostics, not an environment dump or unbounded child logs.
    if diagnostic:
        result["diagnostic"] = diagnostic.decode("utf-8", errors="replace")
    if result["exit_code"] != 0:
        result.update(status="failed", summary=f"Check exited with code {result['exit_code']}.")
        return result
    if check.get("output", "json") == "exit_code":
        result.update(status="passed", summary="Check completed with exit code zero.")
        return result
    try:
        payload = json.loads(output.decode("utf-8-sig"), parse_constant=_reject_constant)
        if not isinstance(payload, dict) or payload.get("status") not in {"passed", "failed", "blocked"}:
            raise ValueError("Invalid check status")
        if not isinstance(payload.get("summary"), str) or not payload["summary"].strip():
            raise ValueError("Missing check summary")
        if not isinstance(payload.get("evidence", []), list):
            raise ValueError("Evidence must be a list")
        canonical(payload)
    except (UnicodeError, ValueError, TypeError) as exc:
        result.update(status="failed", summary=f"Check did not emit a valid JSON result: {exc}.")
        return result
    result.update(status=payload["status"], summary=payload["summary"], evidence=payload.get("evidence", []), payload=payload)
    return result


def _review_results(root: Path, protocol: dict[str, Any], subject: str, reviews_path: Path | None, state_dir: Path) -> list[dict[str, Any]]:
    records: list[Any] = []
    bundle_error = ""
    if reviews_path is not None:
        try:
            bundle = _read_json(reviews_path)
            if not isinstance(bundle, dict) or bundle.get("version") != 1 or not isinstance(bundle.get("reviews"), list):
                raise ProtocolError("Review bundle must contain version 1 and a reviews list.")
            records = bundle["reviews"]
        except ProtocolError as exc:
            bundle_error = str(exc)
    results = []
    for slot in protocol["review_slots"]:
        result: dict[str, Any] = {"id": slot["id"], "required": slot.get("required", True), "status": "blocked", "summary": bundle_error or "No independent review evidence supplied.", "findings": [], "resolved_findings": []}
        candidates = [record for record in records if isinstance(record, dict) and record.get("slot") == slot["id"]]
        if candidates:
            try:
                if len(candidates) != 1:
                    raise ProtocolError("Supply exactly one review per slot.")
                record = candidates[0]
                if record.get("subject_sha256") != subject:
                    raise ProtocolError("Review covers a different implementation, input, or configuration fingerprint.")
                if record.get("independent") is not True:
                    raise ProtocolError("Reviewer must attest to independent review.")
                _identifier(record.get("reviewer_id"), "reviewer_id")
                if record.get("decision") not in {"approve", "request_changes"}:
                    raise ProtocolError("Review decision must be approve or request_changes.")
                if not isinstance(record.get("summary"), str) or not record["summary"].strip():
                    raise ProtocolError("Review needs a nonempty summary.")
                evidence_paths = record.get("evidence_paths")
                if not isinstance(evidence_paths, list) or not evidence_paths:
                    raise ProtocolError("Review must identify local evidence files.")
                evidence = []
                for name in evidence_paths:
                    path = _inside(root, name)
                    if not path.is_file() or path.stat().st_size == 0:
                        raise ProtocolError("Review evidence must be nonempty files.")
                    evidence.extend(_file_records(root, [name], state_dir))
                if not evidence:
                    raise ProtocolError("Review evidence cannot consist solely of generated state or excluded files.")
                findings = record.get("findings", [])
                resolved = record.get("resolved_findings", [])
                if not isinstance(findings, list) or not isinstance(resolved, list):
                    raise ProtocolError("Review findings and resolved_findings must be lists.")
                finding_ids = set()
                for finding in findings:
                    if not isinstance(finding, dict) or not isinstance(finding.get("summary"), str) or not finding["summary"].strip():
                        raise ProtocolError("Each review finding needs an id and summary.")
                    finding_id = _identifier(finding.get("id"), "finding.id")
                    if finding_id in finding_ids:
                        raise ProtocolError("Duplicate review finding id.")
                    finding_ids.add(finding_id)
                for name in resolved:
                    _identifier(name, "resolved_findings")
                    if name in finding_ids:
                        raise ProtocolError("A finding cannot be open and resolved in the same review.")
                if record["decision"] == "approve" and findings:
                    raise ProtocolError("An approval cannot include unresolved findings.")
                result.update(status="passed" if record["decision"] == "approve" else "failed", summary=record["summary"], reviewer_id=record["reviewer_id"], independent_attestation=True, evidence=evidence, findings=findings, resolved_findings=resolved)
            except (ProtocolError, OSError) as exc:
                result["summary"] = str(exc)
        results.append(result)
    # One reviewer cannot satisfy several required independent review slots.
    required_reviewers: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        if result["required"] and result["status"] == "passed":
            required_reviewers.setdefault(result["reviewer_id"], []).append(result)
    for assigned in required_reviewers.values():
        if len(assigned) > 1:
            for result in assigned:
                result.update(status="blocked", summary="Required independent review slots need distinct reviewer identities.", resolved_findings=[])
    return results


def _observe(ledger: dict[str, Any], issue_id: str, passed: bool, summary: str, blocking: bool, report: dict[str, Any], evidence: Any) -> None:
    issues = ledger["issues"]
    existing = issues.get(issue_id)
    if passed and existing is None:
        return
    previous = existing.get("status") if existing else None
    if passed:
        current = "resolved"
    elif previous in {"resolved", "reopened"}:
        current = "reopened"
    else:
        current = "open"
    issue = existing or {"id": issue_id, "first_seen": report["timestamp"], "history": []}
    # A required gate cannot be silently demoted by removing or weakening it.
    issue.update(status=current, summary=summary, blocking=blocking or issue.get("blocking", False), last_observed_run=report["run_id"], updated_at=report["timestamp"])
    if current != previous:
        issue["history"].append({"status": current, "run_id": report["run_id"], "timestamp": report["timestamp"], "subject_sha256": report["fingerprints"]["subject_sha256"], "evidence": evidence})
    if passed:
        issue["resolution_evidence"] = {"run_id": report["run_id"], "subject_sha256": report["fingerprints"]["subject_sha256"], "evidence": evidence}
    else:
        issue.pop("resolution_evidence", None)
    issues[issue_id] = issue


@contextmanager
def _lock(state_dir: Path):
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "run.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ProtocolError(f"An iteration run is already active, or a stale lock needs inspection: {path}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump({"pid": os.getpid(), "timestamp": timestamp()}, file)
        yield
    finally:
        path.unlink(missing_ok=True)


def run(root: Path, protocol_path: Path, state_dir: Path, *, max_iterations: int = 1, max_seconds: float = 120, reviews_path: Path | None = None) -> dict[str, Any]:
    """Execute at most max_iterations sweeps, preserving unresolved evidence gaps."""
    root = root.resolve()
    protocol_path = protocol_path.resolve()
    state_dir = state_dir.resolve()
    if not state_dir.is_relative_to(root) or state_dir == root:
        raise ProtocolError("State directory must be a subdirectory of the project.")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or not 1 <= max_iterations <= 100:
        raise ProtocolError("max_iterations must be an integer from 1 to 100.")
    _number(max_seconds, "max_seconds", 0.01, 86400)
    protocol = load_protocol(root, protocol_path)
    # Validate execution paths before creating state or taking the run lock.
    fingerprints(root, protocol, state_dir)
    started = time.monotonic()
    reports = []
    previous_signature = None
    stop_reason = "max_iterations"
    with _lock(state_dir):
        ledger_path = state_dir / "issues.json"
        ledger = _read_json(ledger_path) if ledger_path.exists() else {"version": 1, "issues": {}}
        if not isinstance(ledger, dict) or ledger.get("version") != 1 or not isinstance(ledger.get("issues"), dict):
            raise ProtocolError("Invalid issue ledger; do not discard it to force promotion.")
        for index in range(max_iterations):
            if time.monotonic() - started >= max_seconds:
                stop_reason = "time_budget"
                break
            protocol = load_protocol(root, protocol_path)
            before = fingerprints(root, protocol, state_dir)
            report: dict[str, Any] = {
                "version": 1,
                "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12],
                "timestamp": timestamp(),
                "iteration": index + 1,
                "fingerprints": before,
                "runtime": {"python_executable": sys.executable, "platform": platform.platform()},
                "budget": {"max_iterations": max_iterations, "max_seconds": max_seconds},
                "checks": [], "gates": [], "reviews": [],
            }
            for check in protocol["checks"]:
                result = _check(root, check, max_seconds - (time.monotonic() - started))
                report["checks"].append(result)
            checks = {result["id"]: result for result in report["checks"]}
            for gate in protocol["gates"]:
                dependencies = gate["check_ids"]
                passed = bool(dependencies) and all(checks[name]["status"] == "passed" for name in dependencies)
                report["gates"].append({"id": gate["id"], "required": gate.get("required", True), "status": "passed" if passed else "blocked", "summary": gate["description"], "check_ids": dependencies, "evidence": [{"check_id": name, "status": checks[name]["status"]} for name in dependencies]})
            report["reviews"] = _review_results(root, protocol, before["subject_sha256"], reviews_path, state_dir)
            try:
                after_protocol = load_protocol(root, protocol_path)
                unchanged = before["subject_sha256"] == fingerprints(root, after_protocol, state_dir)["subject_sha256"]
            except (ProtocolError, OSError):
                unchanged = False
            report["subject_unchanged_during_checks"] = unchanged
            _observe(ledger, "integrity:subject_changed", unchanged, "Implementation, inputs, and protocol must remain unchanged throughout verification.", True, report, {"unchanged": unchanged})
            for kind in ("checks", "gates", "reviews"):
                prefix = {"checks": "check", "gates": "gate", "reviews": "review"}[kind]
                for result in report[kind]:
                    _observe(ledger, f"{prefix}:{result['id']}", result["status"] == "passed" and unchanged, result["summary"], result["required"], report, {"status": result["status"], "evidence": result.get("evidence", []), "subject_unchanged": unchanged})
                    if kind == "reviews":
                        for finding in result["findings"]:
                            _observe(ledger, f"review:{result['id']}:{finding['id']}", False, finding["summary"], result["required"], report, {"reviewer_id": result.get("reviewer_id"), "evidence": result.get("evidence", [])})
                        if unchanged:
                            for finding_id in result["resolved_findings"]:
                                _observe(ledger, f"review:{result['id']}:{finding_id}", True, "Reviewer supplied explicit resolution evidence.", result["required"], report, {"reviewer_id": result.get("reviewer_id"), "evidence": result.get("evidence", [])})
            blockers = sorted(issue_id for issue_id, issue in ledger["issues"].items() if issue["status"] != "resolved" and issue["blocking"])
            report["blocking_issues"] = blockers
            report["decision"] = "promote" if not blockers else "block"
            report["decision_scope"] = "Only the configured protocol; passing software checks is not a measured detector accuracy claim."
            report["next_actions"] = [{"issue_id": name, "action": ledger["issues"][name]["summary"]} for name in blockers]
            report["elapsed_seconds"] = round(time.monotonic() - started, 4)
            _write_json(state_dir / "runs" / (report["run_id"] + ".json"), report)
            _write_json(ledger_path, ledger)
            _write_json(state_dir / "latest.json", report)
            reports.append(report)
            signature = digest({"subject": before["subject_sha256"], "checks": [(item["id"], item["status"], item["summary"]) for item in report["checks"]], "blockers": blockers})
            if report["decision"] == "promote":
                stop_reason = "promoted"
                break
            if previous_signature == signature:
                stop_reason = "no_progress"
                break
            previous_signature = signature
        summary = {"version": 1, "decision": reports[-1]["decision"] if reports else "block", "stop_reason": stop_reason, "iterations": len(reports), "elapsed_seconds": round(time.monotonic() - started, 4), "latest_run_id": reports[-1]["run_id"] if reports else None, "blocking_issues": reports[-1]["blocking_issues"] if reports else ["budget:no_checks_executed"]}
        _write_json(state_dir / "last_batch.json", summary)
        return summary


def status(state_dir: Path) -> dict[str, Any]:
    latest_path = state_dir / "latest.json"
    ledger_path = state_dir / "issues.json"
    latest = _read_json(latest_path) if latest_path.exists() else None
    ledger = _read_json(ledger_path) if ledger_path.exists() else {"issues": {}}
    issues = list(ledger["issues"].values())
    return {"latest": latest, "issue_counts": {state: sum(issue["status"] == state for issue in issues) for state in ("open", "resolved", "reopened")}, "open_issues": sorted((issue for issue in issues if issue["status"] != "resolved"), key=lambda issue: issue["id"])}
