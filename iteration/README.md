# Bounded local improvement loop

This standard-library runner records evidence for development decisions. A
developer or coding agent selects an open issue, changes the design or code,
runs the checks, inspects the result, requests independent review, and repeats.
The runner does not edit code, manufacture human examples, call remote models,
or turn successful unit tests into detector-accuracy claims.

```powershell
python -m iteration run --protocol evaluation/protocol.json --max-iterations 2 --max-seconds 120
python -m iteration status
python -m iteration open-issues
python -m unittest discover -s tests -p test_iteration.py
```

The commands run relative to the current project; `--root PATH` selects another
project. State defaults to `.iteration/` and can be changed with `--state-dir`.
`run` exits 0 for **promote**, 1 for **block**, and 2 for invalid configuration.
Promotion applies only to the requirements actually specified in that protocol.

## The development cycle

1. Read `open-issues`; choose one concrete, testable gap.
2. Record the intended change and its acceptance evidence in the project journal.
3. Implement a bounded change and add a meaningful regression check when needed.
4. Run the protocol. Fix failed checks; gather real evidence for blocked gates.
5. Ask separate reviewers to assess implementation and evaluation methodology.
6. Attach review evidence bound to the exact recorded subject fingerprint.
7. Promote only after required checks, gates, reviews, and earlier blocking
   findings all have passing evidence. Otherwise choose the next gap and repeat.

`--max-iterations` allows 1–100 verification sweeps, default 1. It is not a
background self-editing daemon. A passing sweep stops immediately; two identical
blocked outcomes stop as `no_progress`. `--max-seconds` sets a total execution
budget, default 120 seconds, and each check has its own timeout. Timed-out process
groups are terminated. File hashing, startup, termination, and report writes add
small overhead; this is not a hard real-time scheduler. Repeated checks cannot
resolve missing research or licensing evidence by themselves.

## Protocol

Configuration is trusted, reviewed local code configuration. It must never be
copied directly from a model response, pasted user text, or retrieved document.
Only explicitly allowlisted project-local `.py` scripts execute, through the
current Python interpreter with an argument array and `shell=False`. These
scripts have the user's local permissions; the allowlist is **not a sandbox**.
Do not put credentials or secrets in arguments, summaries, or diagnostics.

```json
{
  "version": 1,
  "allowed_scripts": ["evaluation/checks.py"],
  "implementation_paths": ["detector", "iteration", "evaluation"],
  "input_paths": ["tests/fixtures", "corpus/manifest.json"],
  "checks": [
    {
      "id": "regressions",
      "script": "evaluation/checks.py",
      "args": ["regressions"],
      "required": true,
      "timeout_seconds": 60,
      "output": "json"
    }
  ],
  "gates": [
    {
      "id": "software_behavior",
      "description": "Functional regression checks must pass.",
      "check_ids": ["regressions"],
      "required": true
    },
    {
      "id": "heldout_accuracy",
      "description": "Independent accuracy evidence is still required.",
      "check_ids": [],
      "required": true
    }
  ],
  "review_slots": [
    {"id": "implementation", "required": true},
    {"id": "evaluation", "required": true}
  ]
}
```

All six arrays are required. Declare actual implementation and input files or
directories; missing paths are errors. Directory declarations cover descendants,
excluding `.git`, `.venv`, `node_modules`, `__pycache__`, `.pyc`, and the state
directory. Check scripts and runner code are automatically fingerprinted. Include
dependency lock files, corpus manifests, seeds, model files/configurations, and
other relevant artifacts in the declarations. Anything omitted cannot be
verified by this runner. SHA-256 metadata is stored, not file contents.

A gate passes only when its **nonempty** `check_ids` all pass. An empty list means
evidence has not been implemented and stays blocked. A check with `output:
"exit_code"` uses process exit status; `output: "json"` requires one JSON object
on stdout and exit code zero:

```json
{
  "status": "passed",
  "summary": "All regression fixtures passed.",
  "evidence": [{"artifact": "evaluation/results/regressions.json"}]
}
```

Allowed statuses are `passed`, `failed`, and `blocked`. Other payload fields are
preserved, but the runner does not calculate or endorse their metrics. Check
output is limited to 1 MiB; up to 4 KiB of stderr is retained for diagnosis. The
check is responsible for writing durable evidence, validating metric definitions,
testing confidence intervals and subgroup coverage, and returning a truthful
status. Passing JSON cannot override a nonzero process exit code. A changed
implementation/input/configuration during a sweep invalidates its pass results.

## Independent review evidence

After a run, copy `latest.fingerprints.subject_sha256` from `status` into a review
bundle. Each reviewer writes a separate evidence file outside generated state and
declared implementation/input paths. Binding reviews to the subject avoids stale
approvals; independent review is an attributed attestation, not authenticated
proof of a reviewer's identity. Required slots need distinct reviewer IDs.

```json
{
  "version": 1,
  "reviews": [{
    "slot": "evaluation",
    "reviewer_id": "evaluation-reviewer",
    "independent": true,
    "subject_sha256": "COPY_THE_SUBJECT_SHA256_FROM_STATUS",
    "decision": "request_changes",
    "summary": "Check family overlap before interpreting accuracy.",
    "evidence_paths": ["reviews/evaluation.md"],
    "findings": [{
      "id": "family_leakage",
      "summary": "Related revisions cross development and test partitions."
    }],
    "resolved_findings": []
  }]
}
```

```powershell
python -m iteration run --protocol evaluation/protocol.json --reviews reviews/bundle.json
```

Approvals use `decision: "approve"`, no open `findings`, and nonempty local evidence
files. A later review must explicitly name addressed issue IDs in
`resolved_findings`; a general approval does not silently clear earlier findings.
Evidence files are hashed into the report. Invalid, missing, duplicate, or stale
reviews block required slots. Reviewers must examine the evidence themselves;
creating approval JSON is not a substitute for review.

## State and unresolved issues

Each run has `.iteration/runs/<id>.json`, with fingerprints, check results,
gate/review decisions, and next actions. `latest.json` points to the most recent
report; `last_batch.json` records the bounded loop outcome. `issues.json` records
open, resolved, and reopened issue histories with run IDs and resolution evidence.
Writes use atomic replacement and an exclusive `run.lock` prevents concurrent
writers. After an interrupted process, inspect the lock's PID before manually
removing a stale lock. Completed run reports can help recover an interrupted
multi-file write; the directory is not a transactional database.

Removing or weakening a failing check/gate does not clear its existing required
issue. Restore it and provide passing evidence. State files are local audit
artifacts and can be tampered with by a local user; they are not a security or
certification boundary. Do not delete state to claim a gap was resolved.
