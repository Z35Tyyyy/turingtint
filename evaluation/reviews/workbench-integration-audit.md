# Workbench integration independent audit

Reviewer: `iteration_framework`. Review started 2026-09-27T19:15:55Z.

This review covers the new coach, API integration, shared inference lock, model
installation script, and browser workflow. I did not implement those components.
It **does not independently approve `turingtint/workbench.py`, the detector
metrics library, or the subsequent privacy helper `turingtint/guidance.py`**,
which I implemented; their review belongs to a separate reviewer. This is an
engineering review of an experimental workbench, not
approval of authorship accuracy, mixed authorship, sentence localization, factual
rewrites, or plagiarism conclusions.

## Evidence inspected and executed

- Read `turingtint/coaching.py`, `turingtint/app.py`,
  `turingtint/research.py`, `scripts/setup_coach.py`, the new coaching/API tests,
  `web/app.js`, `web/index.html`, and `evaluation/check_browser.py`.
- Independently ran `python -m unittest tests.test_coaching
  tests.test_workbench_api tests.test_research_api -v` in the project virtual
  environment after all coach changes: **29 tests passed**. These cover unchanged
  multiline input,
  provider selection, no application text persistence, strict input validation,
  generic failures, inherited origin/host/body guards, shared GPU exclusion,
  lazy loading, quote anchoring, Unicode offsets, invalid output, and failed
  provider responses.
- Independently ran `python evaluation/check_browser.py` after all frontend
  changes: **11 browser checks passed**. Model and coach outputs are mocked;
  reference matching uses the real
  local corpus. The suite verifies Unicode/multiline preservation, safe rendering
  of HTML-like input, exact revision replacement, stale-response rejection even
  when cancellation is ignored, ordered detector/coaching requests, isolated
  component failures, explicit export, empty browser storage, and explicit
  provider selection. There were no external browser requests or script errors.
- Inspected `outputs/browser/writing-workbench.png` and `mobile.png`: the
  experimental explanation, context-block signals, separate coach opinion,
  optional raw-score details, revisions, and secondary source panel are visible.
  The browser check also verifies no horizontal overflow at 390 pixels.
- Ran an additional temporary manifest fixture: a complete inventory with valid
  hashes passed `verify_local`; changing a model shard then raised the checksum
  mismatch before any model loader was called. No real weights or user text were
  modified by this fixture.

These tests establish the described software behavior. Mocked model outputs and
screenshots do not measure the accuracy or quality of the installed models.

## Findings and boundaries

One material dependency privacy defect and two frontend presentation defects
were identified. All are resolved in the final inspected implementation:

- **COACH-001 (resolved through separate independent review):** pinned
  `lm-format-enforcer` 0.11.3's
  `TokenEnforcer._compute_allowed_tokens` catches an unexpected error, decodes
  the entire prompt token sequence, and passes that text to root
  `logging.exception`. Its other error branch also logs generated characters.
  The application-level generic exception handler cannot prevent these
  dependency log calls. A synthetic forced-parser-error fixture reproduced
  passage text in captured logging without loading a real model; the library
  swallowed the error and returned EOS. I then implemented a narrowly scoped
  `guidance.py` helper replacing only this dependency module's logging binding,
  not Python's root/application logging. Its three tests verify lazy optional
  imports, fresh parser state, and the actual forced-error path: EOS is returned,
  no prompt/exception marker reaches logging, ordinary control logging remains
  available, and invalid JSON is unavailable rather than a fabricated result.
  Root independently caught an initial missing `ERROR` constant; it was added,
  and the regression strengthened to assert EOS outside a caught callback.
  These implementation tests are **not** my independent approval of the helper.
  Root subsequently inspected and tested the correction. Reviewer
  `plagiarism_research` also independently inspected the helper and dependency
  logging sites and ran all three helper tests, recorded in
  `workbench-model-audit.md`. That separate review supports resolving this finding.

- **UI-001:** unavailable coach results supply `reason`, while the renderer read
  `summary`, hiding specific size/busy/setup explanations. Resolved: the renderer
  now reads `reason` first and a new browser regression preserves setup advice.
- **UI-002:** the truncation message described an unhighlighted remainder, while
  unscored context blocks can render as inconclusive highlights. The explanation
  now refers to incomplete blocks remaining inconclusive and retains coverage
  details. A visible reminder to review facts and placeholders was also added
  beside revision cards and checked in the final screenshot/browser run.

The final frontend also shows each classifier's leaning in the main assessment,
retains numerical scores under details, and requires exact quote/UTF-16 matching
before showing any revision card. Withheld rewrites retain anchored advice but
have no rewrite box or apply button. The final browser checks cover these cases.

The default coach loads a pinned local Qwen revision only after an explicit
analysis. Model files are hash-checked before loading; Transformers uses
`local_files_only=True`, disables remote code, and loads safetensors. Setup is a
separate pinned download. The generated manifest is a trusted local installation
receipt, not a signature protecting against an attacker who can replace both
artifacts and the receipt.

The optional API path uses server-side configuration, a fixed provider URL, no
redirects or environment proxy, and `store:false`. It requires an explicitly
selected provider; local failures do not fall back to a cloud request. The UI
defaults to local and discloses passage transmission before the user clicks
Analyze. The independent checks mocked this provider; no paid/cloud inference
was performed. Application no-save behavior does not establish a provider's
retention policy or constitute operating-system packet capture.

The shared nonblocking lock excludes simultaneous MAGE and local-coach loading
or inference. ML runs before coaching in the UI, and health/source routes stay
independent. Browser cancellation invalidates results but cannot forcibly stop
an already-running server inference. Generation has output/token and stopping
limits; the library's generation time limit is not a hard process deadline.
The lock also does not by itself prove both cached models fit in GPU memory.

Coach output must match a strict structure. Exact, unique source quotes are
anchored with UTF-16 offsets; absent or ambiguous quotes are discarded. Suggested
edits require an unchanged input revision and exact current quote. Applying one
invalidates the previous report. Untrusted passage/model text is rendered using
text nodes, not HTML, and no model output is executed as a command.

Guided JSON generation constrains syntax and schema, not factual content. The
final schema/post-validation limit output to two suggestions, 240-character
fields and 320-character quotes/rewrites. Incomplete/time/token-limited generation
and malformed output have safe distinct unavailable reasons; no JSON repair or
heuristic fallback fabricates a result. Generation metadata contains counts and
an EOS flag, not prompts or generated text. A new
numeric guard withholds rewrites containing digit sequences absent from the
passage outside bracketed placeholders; it preserves anchored review comments.
It does not validate numbers reused in a different context, numbers written as
words, statements inside brackets, or other factual claims.

Quote anchoring verifies where an edit applies; it does **not** verify whether a
rewrite preserves facts, is useful, or follows every prompt instruction. Free
LLM prose is not semantically validated. The UI keeps coach opinions separate
from detector signals and asks the writer to review facts and meaning. Raw
detector scores are explicitly uncalibrated, context blocks are not sentence
authorship localization, and disagreement is inconclusive. The validated
authorship endpoint remains unavailable.

## Final binding

**Approve the scoped coach/API/browser integration.** This approval must not be
represented as product or scientific validation. I verified the hashes of
`detector_eval/experiment.py`, `detector_eval/reports.py`, and
`evaluation/check_authorship.py` are unchanged from `phase2-experiment-audit.md`;
that prior scoped review and its scientific limitations remain applicable.

At 2026-09-27T19:23:11Z, I independently recomputed the current protocol,
implementation, and input fingerprint and matched it to completed run
`20260927T192206-929d64dd7977`:

`d06d7647805bc76989cbfb2ffcb64b88199fb59bb17bf2268e3e7f51aedf7be1`

The recorded run has 142 software tests and 11 browser checks passing, reference
corpus ingestion passing, and authorship evidence blocked. I independently ran
the focused checks described above; the full test count is the verified runner
record. Scientific gates remain blocked. This review's model/coach browser
evidence is mocked; a final real GPU UI smoke is being performed separately and
is not claimed as completed here.

| Inspected file | SHA-256 |
|---|---|
| turingtint/coaching.py | 6696959a8ecbdaa12274539c5662446a2857867c562a7a40b7bbfa872921df81 |
| turingtint/app.py | 1514a483d969a77ee1f7cb898e49424889bf3622de6376c4142d928da884739f |
| turingtint/research.py | 78162cae707b8345d3c954c8e6c8a7de3c4db6a0bcdc3ff3e28abd58b85083fc |
| scripts/setup_coach.py | edb390ddfd4e00bbd2aa9f3bf8158a9ba1d0bc6fe64f454020825ab80b493279 |
| tests/test_coaching.py | 87a153e81e036c5a26c305100e5f43a0c44ca544346528b357c58769bf138d2c |
| tests/test_workbench_api.py | e83e78c2c3b47e7312a7eb1ad13b1d3441bf6012c04912a985b4dbdbe8e9df95 |
| web/app.js | 64762fd006a74fc6363814978443a1e5eb821204c1757a4521314880555842fa |
| web/index.html | 3e6ce9a3541051804262c4758c84a155a855e1c18a3254fbbf27f071294499cc |
| web/styles.css | 1148a98c3cd54e72f0258bd4977a890872cc0bfac9a13259dd5e5ddc541e177f |
| evaluation/check_browser.py | d80f438402f1c6d49329cd651a468ee86f64c5a996a25f90c732d5aa47280450 |
