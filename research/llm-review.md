# Local writing review: current implementation

The coach edits writing; it does not guess authorship. Results set `assessment:null`
and `authorship_opinion:"not_provided"`. The separate detector owns experimental
classification. No writing feedback claims to lower detector scores or prove
originality, plagiarism or factual correctness.

## Model and provider boundaries

`turingtint/coach_profiles.py` defines two fixed, pinned local profiles:

- `instruct` (default): Qwen/Qwen3-4B-Instruct-2507,
  revision `cdbee75f17c01a7cc42f958dc650907174af0554`,
  `.cache/coaching-model-4b`, CUDA NF4 double quantization with FP16 compute.
- `small` (explicit comparison): Qwen/Qwen3-1.7B,
  revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`,
  `.cache/coaching-model`, FP16 CUDA or FP32 CPU.

`TURINGTINT_COACH_PROFILE=small` explicitly selects the comparison. Unknown values
fail closed; model IDs and paths cannot be supplied through environment variables.
The larger profile requires CUDA and does not use CPU offload. Models load only
from installed safetensors with local-files-only and remote-code disabled. Complete
unique profile file lists and manifest checksums are checked before first load.
This is consistency with a trusted local acquisition receipt, not a signed
independent artifact attestation. No model download occurs during review.

The [4B official model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
identifies the Apache-2.0 non-thinking instruction model. A small actual CUDA NF4
operator probe passed on bitsandbytes0.47.0/torch2.6.0+cu124; full-model quality
must be established separately. The initial 4B comparison retains the exact v2
editing prompt and eight frozen fixtures used for the smaller model.

OpenAI is optional and requires explicit provider selection plus server-only
`OPENAI_API_KEY` and `TURINGTINT_OPENAI_MODEL`. Requests use the fixed official
Responses endpoint, `store:false`, strict JSON schema, no redirects and bounded
response bytes/time. There is no automatic cloud fallback. `store:false` is not
a zero-retention promise. No real paid API call was made in these experiments.
See [official structured output documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

## Output, grounding and limits

Input is limited to8,000 characters and3,072 full prompt tokens, without silent
truncation. Generation permits900 new tokens and90 seconds; Transformers checks
its time budget between decoding steps rather than imposing a hard process deadline.
A shared nonblocking GPU lock prevents overlapping model tasks in the app process.
No passage or review is persisted by the coaching module.

A fresh privacy-safe guided JSON decoder constrains output structure. It uses
[lm-format-enforcer's Transformers integration](https://github.com/noamgat/lm-format-enforcer).
The helper suppresses that dependency's prompt-bearing error logging without
changing global application logging. Refusal, incomplete generation or invalid
schema produces unavailable; no heuristic review is substituted.

The model receives the actual dynamic JSON schema and emits only typed suggestions:
sentence_id, issue_type and rewrite. The allowed types are redundancy, overclaim,
unclear_reference, incomplete and citation_needed. The application supplies fixed
honest editorial titles, explanations and actions per type, explicitly marked
explanations_source=fixed_issue_guidance. These are product guidance, not model
findings or fabricated LLM explanations. Incomplete and citation-needed items always
have empty rewrites. The LLM selects the type and any permitted rewrite.
The API summary is a system-generated count/status, marked summary_source=system_status;
it is not an LLM description of the passage. The LLM selects supplied sentence IDs. The server supplies exact source quotations
and UTF-16 offsets, even when identical sentences repeat. The conservative splitter
handles common academic abbreviations, decimal punctuation and Unicode closing
quotes, but is not a comprehensive linguistic sentence parser. The LLM proposes
at most two concrete replacement sentences; clear text can receive no edits and
incomplete text may receive review comments without a rewrite. There is no LLM
assessment/reason field and no forced240/320-character clipping. Generated strings
still undergo a2,000-character validation bound and the total token/time limits.

Transparent validation discards invalid/duplicate IDs, unchanged rewrites and
serialized schema fragments in rewrite prose. Free-form model explanations and
unknown issue types are rejected by the schema. Complete sentences containing digits are conservatively
protected: suggestions targeting them are discarded, with an explicit policy notice.
Unfinished numeric sentences can retain comments only with an empty rewrite. This
restriction prevents automatic edits to such observations; it does not fact-check
units or relationships. New numeric details in other rewrites and completion of an
obviously unfinished copular/causal clause withhold the rewrite. Terminal punctuation
is normalized, including after a quoted word without its own terminal punctuation.
These operations validate or format model content; they do not generate a review.
They cannot establish semantic factuality, preserve every relationship, or detect
all invented details. Authors must review proposed changes before applying them.

## Frozen development checks and observed failures

`evaluation/coach_quality_fixtures.json` contains eight synthetic cases frozen
before inference (SHA256 `f0a81b97da631c0fdb19ef610a531c0ec72bc13eae49c03f944dfa195bf774b1`).
`evaluation/coach_quality.py` calls only the already-running loopback API and never
loads another GPU model. It checks actual shortening, softened overclaims, preserved
numbers, restraint on clear writing, handling of incomplete input and embedded
instructions, exact spans and terminal punctuation. Server code fingerprints bind runs
to the loaded implementation. This is development regression evidence, not a
held-out general writing-quality benchmark or authorship-accuracy evaluation.

Small-model v1 completed all8 requests but passed0 strict checks. Missing punctuation
caused several failures; there were also unnecessary edits, wrong-sentence/no-op
rewrites, incomplete replacements and meaning drift. Its redundancy and overclaim
edits did show useful changes. Evidence: `outputs/reviews/coach-quality-v1.json`.

Small-model v2 passed3/8 automated checks, but only the two clear-text cases were
semantically clean. The injection rewrite added unsupported additional context;
numeric feedback targeted the wrong sentence and dropped120 (withheld); the other
cases were wrongly called already clear. The suite's overclaim regex also misses
the inflection 'double', so manual review is mandatory. Evidence:
`outputs/reviews/coach-quality-v2.json`. Further prompt-only tuning was not treated
as a successful solution; the stronger fixed local model was then compared without changing the v2 prompt or fixtures.

## First 4B comparison and bounded follow-up

The fixed NF4 4B model completed 7/8 requests and passed 5/8 mechanical checks
(`outputs/reviews/coach-quality-v3-4b.json`). Manual inspection found a useful
redundancy rewrite, a sound overclaim rewrite accompanied by a contaminated
JSON-like summary, appropriate edit restraint on both clear cases (one also had a contaminated summary), and useful incomplete
sentence feedback with an attempted completion withheld by the existing guard.
It identified numeric-study redundancy but supplied no edit, became distracted by
the embedded command, and reached a generation limit on the unsupported-claim case.
Five mechanical passes therefore do not mean five fully clean model responses.
The first request took 40.1 seconds including model load; CUDA peak allocation
was approximately 2.8 GiB. Later complete calls took roughly 7-12 seconds.

A bounded v4 follow-up simplifies general editorial instructions, removes examples
and redundant JSON-shape text, requires diagnosed problems to map to suggestions,
and instructs the model to skip embedded commands. A narrow validator withholds
serialized schema-key fragments in prose transparently; it does not repair them
into invented LLM advice. Safe generation counts are retained for limit failures.
The eight fixtures and rubric remain unchanged. The live rerun completed all eight requests and passed six mechanical checks
(`outputs/reviews/coach-quality-v4-4b.json`). Manual review found five usable
responses, partial unsupported-claim improvement, missed editing under injection,
and a material numeric factuality failure: 36 of120 became36% in the summary and
the rewrite removed self-report qualification. The existing numeric-set guard
cannot validate units or evidential modality. These defects remain unresolved;
see `evaluation/reviews/coach-v4-manual.md`. No quality guarantee is justified.

## Final bounded v5 policy

The v4 numeric summary hallucination motivated removal of the free-form model
summary channel. System count/status now replaces it. The observed loss of a
self-report qualifier motivated conservative protection of complete digit-bearing
sentences, with comments only for unfinished numerical input. Dynamic schema is
provided to the model; general instructions request sources for unverified study
claims and continue substantive editing despite commands in text. These changes
are restrictions and guidance, not semantic verification. The unchanged eight-case
live rerun completed seven requests and passed five mechanical checks. Numeric
protection retained the useful nonnumeric edit and prevented the observed numeric
rewrite hazard; both clear cases were untouched. However redundancy returned an
invalid review, incomplete/injection cases got no advice, and overclaim explanation
invented a missing control group. Unsupported-claim rewriting improved uncertainty
but did not request a source. See `evaluation/reviews/coach-v5-manual.md` and
`outputs/reviews/coach-quality-v5-4b.json`. Broad semantic factuality remains
unresolved; no blanket quality improvement or general reliability is claimed.
Previous failures and original receipts remain intact.

## Final typed v6 design

The observed v5 invented control-group explanation motivated a structural restriction:
there is no longer any accepted free-form LLM explanation field. The model selects
one of five editorial issues and an optional rewrite; the product provides fixed
conditional guidance. This eliminates that explanation-generation channel without
pretending the guidance came from an LLM. It does not prove the selected issue is
correct or the rewrite preserves every fact. The same eight fixtures and unchanged
judge completed8/8 requests, with5/8 mechanical passes. Manual review found useful
redundancy/overclaim rewrites, two correct clear-text abstentions, partial unsupported
claim remediation, and three no-edit misses (numeric passage, incomplete text,
injection). The unsupported rewrite retains unverified 'may double'; fixed guidance
asks for a source. No accepted v6 output invented study methods, but this tiny known
suite cannot establish general factual safety. See `evaluation/reviews/coach-v6-manual.md`
and `outputs/reviews/coach-quality-v6-4b.json`. Actual UI validation is separate.
Earlier failures remain.

## Historical prototype findings (superseded behavior)

Earlier code asked the1.7B model for authorship opinions and appended bracketed
questions instead of concrete edits. That model flipped a known assistant-written
sample to human-leaning, invented covariates, produced malformed JSON and sometimes
hit generation limits. These findings remain in `outputs/reviews/llm-coach-smoke.json`,
`llm-coach-public-raw.txt`, `llm-coach-guided-smoke.json`, and
`coaching-smoke-summary.md`. Guided bounded output later produced two successful
functional examples, but that did not validate authorship or factual preservation.
Those old opinions, copied-quote grounding and narrow character caps are no longer
the current contract described above.
