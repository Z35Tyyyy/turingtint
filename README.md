# TuringTint

A local writing-analysis workspace for English academic and student prose.

**Analyze writing** runs two local machine-learning classifiers and a language
model review. The main report shows experimental model leanings, highlights the
context blocks that were scored, and provides specific revision suggestions with
the original wording, a reason and a proposed edit. A secondary source panel
checks wording against the installed reference library.

The primary classifier is the pretrained MAGE transformer. The project's trained
TF-IDF/logistic baseline remains a visible secondary diagnostic. The writing coach
uses a pinned local Qwen instruct model, or an explicitly selected OpenAI API model,
and provides editing advice without guessing authorship. Different block results
remain inconclusive for the whole passage; they do not establish mixed authorship.
**These are experimental predictions, not validated
authorship conclusions or percentages of AI-written text.**

Start with [the test walkthrough](TESTING.md): six labeled cases, optional fast
analysis, exact edit previews, and original/revised comparisons. The current
[model-policy experiment](research/candidate-diagnostic.md) reports gains and
false-positive regressions alongside the original detector results.

The second phase adds licensed corpus acquisition, frozen training/calibration
splits, a trained local baseline and a pinned pretrained detector comparison.
See the [experiment instructions](detector_eval/README.md) and
[measured results](research/phase2-results.md). These diagnostics do not
yet justify validated authorship claims. No model score or suggested rewrite
proves that writing is human or guarantees a lower detector score.

## Run locally

Python 3.12+ is required, including for bounded Windows subprocess handling.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe -m corpus_tools fetch --limit 12
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Open http://127.0.0.1:8765. The first corpus command downloads a small selection
of PLOS abstracts through Europe PMC, verifies article-level CC BY evidence,
and records provenance. Use **Load case** for the six writing examples, or
**Load a reference example** in the source panel to test source matching.

For model analysis, install the research dependencies and model artifacts in
[experiment setup](detector_eval/README.md), then install the writing coach:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-ml.txt
.venv/Scripts/python.exe scripts/setup_coach.py
```

The full historical evaluation protocol also fingerprints the smaller comparison
model. Install it with `scripts/setup_coach.py --profile small` when reproducing
that protocol on a fresh machine; the default UI continues to use `instruct`.

The default Qwen3-4B-Instruct-2507 coach downloads approximately 8.1 GB of Apache-2.0
weights and loads them with NF4 quantization on a CUDA GPU. The project also retains
the smaller 1.7B profile for comparison; setup and resource details are in the
[coach notes](research/llm-review.md). Paste a complete paragraph and click
**Analyze writing**. Uncheck **Include writing feedback** for faster model-only
testing. Model results arrive before the language-model review. First use loads
the models; subsequent requests reuse them. Applying a revision preserves the
original model signals for comparison after reanalysis; unrelated new text resets it.
Long or unsupported inputs show their limits rather than silently pretending
that the whole passage was assessed.

Local mode requires no API key and does not transmit or save your passage.
To use OpenAI instead, configure `OPENAI_API_KEY` and `TURINGTINT_OPENAI_MODEL`
in the server environment, restart, and explicitly select OpenAI in the UI.
That choice sends the passage to OpenAI and uses separately billed API access.
Keys are never entered into the page or returned by the server. See
[LLM setup and behavior](research/llm-review.md).

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
| `turingtint/` | ML workbench, local/API writing coach, source matching and local web API |
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
No API key is required for local mode. Avoid committing private text or credentials.

The former paraphraser code was archived outside the active working tree before
this reset. Git history is retained. No former rewriting loss or detector score
is claimed as evidence for this detector.
