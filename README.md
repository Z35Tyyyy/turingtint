# TuringTint

A local writing-analysis workspace for English academic and student prose.

The first prototype compares a pasted passage against an installed reference
library, highlights matching wording, shows the source and license, and suggests
reviewing quotation and attribution. Analysis does not transmit the passage to
an external service or save it in the reference library.

**Validated AI-authorship detection is not yet available.** The source report
returns null authorship scores. A separate **Test experimental detector** button
runs the installed local MAGE model for research: it shows an uncalibrated raw
score, full input counts and any truncation, without AI/human/mixed verdicts.
Source overlap is not proof of plagiarism, and no match means none was found in
the local library.

The second phase adds licensed corpus acquisition, frozen training/calibration
splits, a trained local baseline and a pinned pretrained detector comparison.
See the [experiment instructions](detector_eval/README.md) and
[measured results](research/phase2-results.md). These diagnostics do not
yet justify enabling authorship labels.

## Run locally

Python 3.12+ is required, including for bounded Windows subprocess handling.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe -m corpus_tools fetch --limit 12
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Open http://127.0.0.1:8765. The first corpus command downloads a small selection
of PLOS abstracts through Europe PMC, verifies article-level CC BY evidence,
and records provenance. Downloads happen during setup; analysis is offline.
Use the reference-example button to try a real source match.

To test the research detector, paste the complete paragraph into the same text
box and click **Test experimental detector**. Multiline pastes are supported.
The first request loads the model and can take longer; later requests reuse it.
The optional model and research dependencies must already be installed (see
[experiment setup](detector_eval/README.md)). The result shows how many characters,
words and model tokens were read. Inputs over 512 model tokens are explicitly
marked as truncated. Editing the passage invalidates the previous result.
Paragraphs stay local and are not saved by this endpoint.

The same application runs with `python -m turingtint` on other supported
platforms after installing `requirements.txt` into a virtual environment.

## Improvement loop

A coding agent selects a gap, implements a bounded change, runs checks, obtains
independent review, fixes findings, and reruns. The runner records evidence and
open/resolved/reopened issues. It does not independently modify source code or
keep an assistant working after its session ends.

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m playwright install chromium
.venv/Scripts/python.exe -m iteration run --protocol evaluation/protocol.json
.venv/Scripts/python.exe -m iteration status
.venv/Scripts/python.exe -m iteration open-issues
```

The full protocol intentionally blocks product promotion while authorship,
mixed-span, and held-out retrieval evidence is missing. Passing software tests
is a separate result. Exit codes: 0 promotes within the configured protocol,
1 records blockers, 2 reports invalid configuration. Reviews are bound to code,
input and configuration hashes; changing them invalidates old approval.

The phase 2 protocol also requires the local research artifacts described in
[experiment setup](detector_eval/README.md). A fresh web-only installation can
run the web app without downloading models; it cannot reproduce that full
research protocol until those inputs exist. Research tests involving tensors
need the optional PyTorch installation.

See [runner documentation](iteration/README.md),
[implementation rules](AGENTS.md), and [next iterations](research/NEXT.md).
Use one bounded sweep by default; rerun after changes or new evidence.

## Components

| Path | Purpose |
|---|---|
| `web/` | Accessible static interface; no external fonts or frontend services |
| `turingtint/` | Local API, SQLite corpus, bounded lexical source matching |
| `corpus_tools/` | License-filtered academic reference acquisition |
| `authorship_data/` | Provenance-checked AIDE and licensed HC3 subset acquisition |
| `detector_models/` | Pinned offline MAGE inference and artifact verification |
| `detector_eval/` | Frozen experiments, calibration, metrics and comparison reports |
| `iteration/` | Bounded checks, fingerprints, issue ledger and review gates |
| `evaluation/` | Software, real-browser and provenance checks; review evidence |
| `tests/` | Meaningful backend, parser and iteration regression tests |
| `research/` | Product, corpus, feasibility plans and next work |

Run `python -m unittest discover -s tests -v` for unit/integration checks.
`python evaluation/check_browser.py` checks real highlights, stale report
invalidation, partial-result warnings, hostile markup, mobile layout and
external-request isolation. Browser screenshots are written to `outputs/browser`.

## Current limits

The initial reference seed contains 12 PLOS abstracts, not full papers or the
whole internet. Exact/near-exact comparison suppresses short/common fragments;
semantic paraphrase detection and validated authorship estimates remain research
work. Matching has time/candidate limits and reports incomplete searches.
The reference sample demonstrates software behavior, not retrieval accuracy.

User text is untrusted data. The server binds to loopback, rejects cross-origin
browser requests, limits inputs and scans, and serves scripts under a restrictive
content-security policy. This local prototype is not a public multi-user service.

Raw corpora, models, local iteration histories, logs and virtual environments are
excluded from Git. Downloaded sources retain their own licenses and attribution.
No API key is required. Avoid committing private text or credentials.

The former paraphraser code was archived outside the active working tree before
this reset. Git history is retained. No former rewriting loss or detector score
is claimed as evidence for this detector.
