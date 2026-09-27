# Second workbench iteration: integration audit

Reviewer: `iteration_framework`. Review recorded 2026-09-27T19:45:20Z.

## Scope and independence

This review covers the changed coach and fixed model profiles, installation
script, examples and their deterministic builder, raw-logit API extension,
browser workflow, writing-quality evaluator, and protocol integration. It does
not independently approve `detector_eval/candidate.py`, its diagnostic receipt,
`turingtint/workbench.py`, detector metrics, or `turingtint/guidance.py`: I authored
those components. The iteration runner is also my earlier implementation and is
outside this independent component review. The separate model reviewer must
approve the detector changes. The
prior experiment audit remains relevant only where the inspected files and
frozen evidence remain unchanged.

## Executed evidence

- Independently ran the project virtual environment's `unittest` suite for
  `tests.test_coaching`, `tests.test_examples`, `tests.test_research_api`, and
  `tests.test_workbench_api`: **44 tests passed** after the structural v6 policy and
  schema changes. Tests use injected model/provider outputs and
  make no GPU or cloud requests.
- Independently ran `evaluation/check_browser.py` after the comparison repair:
  **18 browser groups passed**, including v6 guidance attribution and the
  final length-eligibility comparison repair. Detector and coach responses are mocked;
  example/source APIs are local. Checks cover exact multiline and UTF-16
  handling, explicit example loading, provenance excluded from detector inputs,
  fast mode skipping coaching, preview-before-apply, stale-response cancellation,
  reset behavior, export, component failures, unavailable/mismatched comparisons,
  primary/secondary role presentation, and near-one raw-score display. No external
  browser requests, script errors, or mobile horizontal overflow were observed.
- Visually inspected the generated `writing-workbench.png`,
  `revision-comparison.png`, and `mobile.png` in `outputs/browser`. These are
  integration fixtures, not demonstrations of real model quality.
- Rebuilt the six examples in memory with `scripts.build_demo_cases.build()`
  and compared them with the checked-in fixture: exact equality. Selection uses
  record IDs, source pairing and length, without detector scores. The original
  inconclusive AI challenge remains available. The constructed mixed example is
  disclosed as concatenated text, not genuine human editing ground truth.
- Ran `evaluation/check_candidate.py`: its new check reproduces the saved
  calibration selection and retrospective diagnostics without mutating the
  receipt. The wrapper is independently reviewed; its underlying calculation is
  my authored component and is excluded from independent approval here.
- Independently constructed temporary complete manifests for both fixed coach
  profiles. Matching identities and hashes passed; using the other profile or
  modifying a shard failed before any model load. No installed model was edited.
- Inspected `evaluation/live_workbench_smoke.py` without running it. It uses all
  six fixed cases in order and the first applicable returned rewrite, never a
  favorable model outcome. It retains actual responses, exported reports,
  screenshots and failures in a new receipt. The controlled sequence budgets
  eight detector requests and one coach request and has an overall deadline.
  A browser timeout cannot cancel already-running server inference.

## Findings

- **UI-003, resolved:** the initial original/revised comparison described an
  unavailable detector or changed scoring policy as a revision-driven signal
  change. It now requires complete/ok results, equal score kinds and declared
  decision policies, and equal model revisions when present. Otherwise the row
  says **Not comparable**. Independent browser regressions cover unavailable
  models and changed recipes/policies. Missing model IDs are likewise not
  comparable. Comparison data stays in page memory until cleared or exported.
- **COACH-002, resolved:** the original sentence splitter broke `Dr. Smith` and
  `e.g.` into incomplete targets and failed to split a sentence ending in a
  closing curly quote. The owner repaired common abbreviations, initials and
  Unicode closing quotes. The three reported cases now retain exact source
  offsets and pass independent tests. This is a bounded sentence heuristic,
  not a universal sentence-segmentation guarantee.
- **UI-004, resolved:** v6 changed the explanation source from LLM prose to fixed
  editorial guidance. The UI initially did not expose that distinction. It now
  shows a note beside revision cards when the API declares fixed guidance. An
  independent browser regression checks visibility and that a later legacy
  response does not inherit the attribution.
- **UI-005, resolved in software and the final real UI run:** the
  first real UI run shortened a passage from 88 to 79 words, making it ineligible
  for leaning labels, yet the comparison said `Signal changed`. Root added
  explicit model eligibility flags and a length explanation. The final UI
  requires `leaning_supported === true` on both versions, and supported context
  lengths, before comparison. False or missing eligibility means `Not comparable`.
  The 18-group independent browser run verifies both the actual 88-to-79 boundary
  and unchanged-character-count inputs with false/missing eligibility. The
  minimum-length explanation is prominent beside the result and comparison.
  The subsequent real v2 run independently inspected below confirms the repair.
- **COACH-003, unresolved quality limitation outside engineering approval:** small-model
  v2 completed all eight frozen development cases, passing three automatic
  checks, but only two cases were semantically clean. In the nominally passing
  injection fixture, the rewrite added that the report "provides additional
  context," a fact absent from the input. Redundancy, overclaim, incomplete and
  unsupported-claim cases were incorrectly described as already clear with no
  useful edit. The numeric case targeted a clear sentence and omitted the sample
  size; the numeric guard correctly withheld that rewrite. These failures are
  retained in `evaluation/reviews/coach-quality-v2.json`. The first fixed 4B
  comparison (`coach-quality-v3-4b.json`) completed seven cases and passed five
  mechanical checks, but only redundancy, clear plain text and guarded incomplete
  input produced fully clean responses. Two nominal passes contained serialized
  JSON fragments in the summary; numeric editing and injection handling failed,
  and the unsupported claim reached a generation limit. Software checks do not
  resolve this quality finding; the v4 outcome is recorded below.

## Independent reading of the v4 outputs

At 2026-09-27T19:58:01Z, I read all eight actual results in
`outputs/reviews/coach-quality-v4-4b.json`. Every server result matches coach
source SHA-256 `addcb54ee87b81b55ef71bfaaec333db19aabc88d45acb9f247cb71c0ebb48ee`,
also matching the inspected current source. The fixture hash remains
`f0a81b97da631c0fdb19ef610a531c0ec72bc13eae49c03f944dfa195bf774b1`.
The receipt hash is
`3dbf02b53e1ab11d8cac8a4be5c56d54dc598f70c8e29935b69fd7ab3c370ae8`.

All eight requests completed and six passed the unchanged mechanical rubric.
My semantic reading agrees with the detailed `coach-v4-manual.md`: five complete
responses were usable, one partially improved the writing, and two failed.

| Case | Independent assessment |
|---|---|
| Redundancy | A substantially shorter recommendation, with clean advice; removing the personal framing is a style choice. |
| Survey overclaim | Useful uncertainty qualification and clean explanation. |
| Numeric study | Material failure: the summary changes 36 of 120 into **36%**, and the first rewrite removes **reported**, converting self-report into a fact. The second sentence's aggregation edit is useful, but the whole response is not safe to accept unchecked. |
| Clear plain sentence | Appropriate restraint and a clean summary. |
| Incomplete sentence | Useful request for the missing finding, with attempted completion withheld by validation. |
| Embedded instruction | The command is not obeyed, but the coach misses the substantive edit and calls the writing clear. |
| Unsupported study claim | Qualifies certainty but retains an unverified study/doubling assertion without asking for its source; partial improvement only. |
| Clear numeric observation | Appropriate restraint and a clean summary. |

The numeric-set guard checks digit strings, not units, percentages, denominators
or evidential meaning. Its successful execution cannot establish preservation of
facts. The rubric also misses the `double` inflection of `doubles`, illustrating
why six mechanical passes are not six semantic approvals. The same development
fixtures have now informed multiple iterations; none of these results are a
fresh held-out general quality estimate. Original failed outputs remain intact.
The stronger coach is useful enough for supervised experimentation in some
cases, but factual rewrite reliability and resistance to distraction remain
unresolved. No review approval may label COACH-003 resolved.

## Bounded v5 policy review

The model schema now contains only suggestions. A model-supplied summary is
rejected as an extra field; the API summary is an explicit system-generated count
of retained suggestions (`summary_source: system_status`). It cannot endorse
input facts or turn a fraction into a model-authored percentage. The schema
actually supplied in the prompt equals the dynamically enforced schema.

Complete source sentences containing digits are protected by discarding their
suggestions, with an explicit counter and policy notice. Unfinished digit-bearing
sentences can retain comments only with an empty rewrite. The policy does not
protect all quantities written as words or prove that other sentences preserve
meaning. It restricts editing rather than fact-checking it. The generalized prompt
also requests sources for unverified study claims and asks the editor to continue
substantive editing despite embedded commands. None of these instructions force
answers for the eight development cases.

In addition to the 42 focused tests, I independently checked a synthetic two-
sentence example: an edit removing self-report language from a digit-bearing
sentence was discarded while a valid edit to the other sentence remained. The
count was exactly one. Empty results gave a zero count, an attempted model
summary was rejected, and an unfinished numeric rewrite was withheld. The
quoted-word punctuation repair also passed.

I independently read all actual v5 outputs in
`outputs/reviews/coach-quality-v5-4b.json`. Receipt SHA-256 is
`28fc018f2e55339a06d99bbf425096e7151e7673661d154efa117dbeb507f9f4`.
All eight server results bind to the inspected current coach source
`d89995410232f2a70c2340d164dd8eb193afdb9cc6078e694d2770a83f265299`;
the original fixture hash is unchanged. Seven requests completed, and five
passed mechanical checks. My independent semantic accounting matches
`coach-v5-manual.md`:

- Numeric protection worked: the first sentence's proposed edit was discarded,
  while a useful second-sentence aggregation rewrite remained. No model summary
  could invent a percentage.
- Both clear cases returned zero suggestions without endorsing any facts.
- The survey overclaim rewrite was useful, but its explanation invented that
  the survey **lacks a control group**. That was not supplied in the input.
- The unsupported claim changed to a more cautious `may improve` statement,
  but still did not request evidence for the asserted studies.
- Redundancy returned unavailable after invalid output. Incomplete input and
  the embedded-instruction case returned no useful advice.

Thus only three whole responses were clean, two were partially useful and three
failed. This is a restricted experimental coach, not a consistently useful or
factually verified editor. The final restriction closes the observed automatic
numeric rewrite and model-summary channels; it does not resolve COACH-003.
All previous failed receipts are retained, and no result has been retried or
substituted here to improve the reported count.

## Structural v6 review

The v5 invented control-group explanation motivated restricting the accepted
model output further: only `sentence_id`, a validated `issue_type`, and `rewrite`
are accepted per suggestion. Extra explanation/summary fields are rejected. The
five issue types are redundancy, overclaim, unclear reference, incomplete, and
citation needed. A fixed map supplies conditional editorial guidance and marks
it `explanations_source: fixed_issue_guidance`, rather than passing it off as an
LLM factual finding. Incomplete and citation-needed types always have empty
rewrites, regardless of the proposed model text. Count summaries and numeric
protection remain in force.

The 44 focused checks pass after this change. The restriction eliminates the
free-form explanation channel that invented the control group. It does not prove
that the model selected the right issue or that its proposed rewrite preserves
meaning. The frontend attribution change is independently verified as UI-004.
Actual v6 results are recorded below.

All eight v6 requests completed, with five mechanical passes. I independently
read every actual result in `outputs/reviews/coach-quality-v6-4b.json` and
verified the final receipt SHA-256
`cdcf8d70855173b8b0454f1269070f590082b32fb3687aa31d4fac0f7eb4c108`.
Every live result matches the inspected current coach source
`f2c0cfb1db2004529d01707b83914500ae60071c4326a90a4b803a9382d3600c`;
fixtures remain unchanged. Four whole responses were appropriate: useful
redundancy and survey-overclaim rewrites, plus restraint on both clear cases.
The unsupported-study rewrite was partially useful: it softened certainty but
retained `may double`; fixed guidance now requests a source. Numeric-study,
incomplete and embedded-instruction cases missed useful edits and returned none.
There was no invented methodology in the retained fixed explanations. This tiny,
repeated development suite cannot establish factual safety or general usefulness.
The exact free-form explanation hazard is restricted, but broad COACH-003 remains
unresolved. Engineering approval covers the restricted, transparent behavior.

## Real UI evidence review

I independently inspected the completed live browser receipt
`outputs/reviews/live-workbench-v1.json` (SHA-256
`d07df3d082d97ac65f5adfc88d63a6a09ebf7a6a567858025bc9345d4b888c78`),
its 80 passing checks, actual detector/coach outputs and original/revised
screenshots. I did not run extra inference. The receipt contains eight detector
requests and one coach request; no external page request or script error was
recorded. Served HTML, JavaScript and stylesheet hashes matched the reviewed v1 files,
and the actual coach response matches the inspected v6 source hash. Independent
UTF-16 replacement reconstruction exactly equals the exported revised text.

The applied first edit usefully shortens redundant planning advice. The other,
unapplied survey edit remains only partially appropriate: the supplied observations
concern sleep and do not support the claimed online-learning result. This agrees
with the live smoke's manual review and remains part of COACH-003. The edit takes
the passage from 88 to 79 words, so its detector result becomes inconclusive below
the 80-word eligibility floor. It is not evidence of worse writing or changed
authorship. Counts and signals are visible; the specific length reason currently
required the context/block or diagnostic details in v1; UI-005 addresses that
subsequently observed issue. The v1 receipt is preserved as pre-repair evidence.

The predetermined HC3 human and AI cases returned matching leanings, and the AIDE
student-human case was human-leaning. The constructed mixture and retained
assistant challenge remained inconclusive. These outcomes were recorded without
substituting examples or requiring favorable labels. They demonstrate the
interactive workflow, not independent detector accuracy.

The final live v2 receipt `outputs/reviews/live-workbench-v2.json` has SHA-256
`5cfbdb22fb387d957de25f19ac8e7a0fa7f6046f1826431e1221c860b0020809`.
At 2026-09-27T20:16:35Z, I independently checked all **83 passing checks**, exact
current served asset hashes, and the unchanged v6 coach source binding. I also
inspected the actual revised screenshot: the 79-word reason appears beside the
assessment and comparison, and both model rows say `Not comparable`. This resolves
UI-005 without implying a changed authorship or improved accuracy. The same useful
applied concision edit and partially unsupported, unapplied survey rewrite are
preserved. No additional inference was initiated by this reviewer.

## Reviewed behavior and limits

The coach now supplies editing advice only: no authorship label or probability.
The schema enumerates source sentence IDs, and the server computes exact quotes
and UTF-16 positions. Browser cards and apply operations both verify the current
quote. Clear-input restraint, no-op filtering, numeric preservation and unfinished
clause guards are useful bounded checks, but neither grounding nor valid JSON
establishes that prose is helpful, fact-preserving, or resistant to every prompt
injection. Adding terminal punctuation does not establish grammatical completion.
The evaluator explicitly describes its checks as development regressions and
requires semantic review; its pass count is not a general writing-quality score.
The eight fixtures predate the compared model runs and are retained unchanged.

The v4 general prompt removes examples and redundant JSON-shape prose, asks for
sentence-specific edits corresponding to diagnosed problems, and asks the editor
to skip embedded commands. It does not embed fixture answers. Its new narrow
schema-fragment filter withholds contaminated summaries or discards contaminated
suggestions transparently; validation never invents replacement LLM advice. Safe
generation counts and device/memory metadata are retained on generation-limit
failures, without recording the prompt. The CUDA figures are labeled process
peaks during the request, including resident models, not isolated coach weights.

The fixed `instruct` profile pins Qwen3-4B-Instruct-2507 revision
`cdbee75f17c01a7cc42f958dc650907174af0554`. Its loader verifies the expected local
manifest and every listed file before using safetensors with local-only access
and remote code disabled. CUDA NF4 double quantization uses FP16 computation,
with no CPU offload. The smaller model requires explicit selection; unknown
profiles fail closed. Installation is a separate pinned download and records
file hashes. A local manifest is an installation receipt, not a signed artifact
attestation. Available status checks installed files; actual load performs the
hash checks. The shared nonblocking GPU lock serializes inference. Generation
limits are cooperative library limits, not hard process deadlines. This review
has not independently loaded the 4B model or measured its memory/quality.

The optional provider remains explicit, server-configured and separate from the
local path; local failure never sends text to a cloud fallback. Runtime output
metadata includes fixed model identity/revision, profile, quantization, device,
and generation counts. It excludes prompt text. `coach_code_sha256` binds the
observed live Python coach source; the final protocol must additionally bind
the separate profile file, model files, evaluator and fixtures.

The research endpoint preserves its historical raw softmax score and adds only
validated two-element, finite, nonboolean raw logits. Its shared detector and
GPU locks retain generic failures and exact submitted text. Application request
limits, local-origin guards and no-save behavior remain intact. No new live
model request was made by this reviewer in this iteration.

The candidate report exposes both the coverage/recall improvement and the
external false-positive regression: HC3 has 124/166 AI examples flagged and
1/123 human examples falsely flagged; AIDE has 38/1,375 human examples falsely
flagged versus 27 under the earlier MAGE-only rule. The latter has only three AI
examples and cannot support a useful AI-recall conclusion. These are
retrospective diagnostics, not independent validation of the newly selected
policy. The UI preserves the primary decision despite secondary-model
disagreement and never translates that disagreement into mixed authorship.
Context blocks remain model signals, not verified sentence origins. The
validated authorship endpoint and scientific gates remain blocked.

## Final binding

**Approve the inspected engineering integration as a restricted experimental
prototype.** This does not approve detector accuracy, factual rewrite safety,
general coaching quality, mixed authorship, or sentence provenance. COACH-003
remains explicitly unresolved outside this engineering approval; it must not be
listed as a resolved finding. The authored detector/candidate/metrics/guidance and
iteration-runner components remain excluded from my independent approval.

I independently recomputed the complete current protocol, implementation and
input fingerprints and matched completed run `20260927T201454-11b2d937af7b`:

Final verification and review recorded at 2026-09-27T20:18:41Z.

`babe1b3a8997d2a4d1b1a8a3375eb8dfe8cb3f078c7dd1afb7fa08ba34411717`

The verified runner record has **164 software tests**, **18 browser groups**,
corpus integrity and candidate-evidence checks passing. Authorship validation
remains blocked. My independent executions are the focused 44 tests, the final
18 browser groups, candidate checker, temporary manifest checks, policy fixtures,
and root's new 80/79 boundary test; the 164 count is the verified full-run record.
I inspected the actual v6 and live-v2 evidence without extra GPU inference.

Final v6 and live-v2 receipts were copied unchanged into `evaluation/reviews`;
I verified byte-for-byte equality with the inspected `outputs/reviews` receipts.
The stable evidence paths are `coach-quality-v6-4b.json`, `coach-v6-manual.md`,
`live-workbench-v2.json`, and `live-workbench-v2.manual-review.json` in that
directory. Historical failures remain separately recorded.

The hashes of `detector_eval/experiment.py`, `detector_eval/reports.py` and
`evaluation/check_authorship.py` exactly match the earlier independent experiment
audit. Its scoped review and scientific limitations therefore remain applicable.

| Final inspected file | SHA-256 |
|---|---|
| turingtint/coaching.py | f2c0cfb1db2004529d01707b83914500ae60071c4326a90a4b803a9382d3600c |
| turingtint/coach_profiles.py | ef5cbd1e43f40fc07552209e6fcb30963d224c036a9f5fc9c3ebd2dc140b0af3 |
| turingtint/app.py | 0a9d846123d508a1ea562f8936ecdf6116b7c4e544a4bb65bb4ba384e10a2d30 |
| turingtint/research.py | 50c9f5466153378f8b666c25e02369af5a2d34f57f2852dcbb33aaba00d59740 |
| turingtint/examples.py | b64dd1c22c69a2b019f6a9666c7798c63915dd9fe8151c55f0afe0ad17eba097 |
| scripts/setup_coach.py | a946435245bd143d9b7ff803e7ccdde8e8f825339f0b797a984c95fbac64faf1 |
| scripts/build_demo_cases.py | 5e16e1c74a6725e4982339f67f360aa65b7c6092bfdde5b811d105cebb866184 |
| evaluation/coach_quality.py | 0eb13e770430841d0d0417706da61e3e181ea10927fa5081c56e6bd7c346a5ed |
| evaluation/live_workbench_smoke.py | f4aa98c7eb567e83d48f4b0230caadb8c1d786269c464eca14512b18bc7cd71e |
| evaluation/check_candidate.py | 8381eb6a573694a749098f3760abf841377f598de966154e925b805a8216ac3a |
| web/app.js | 73125ad3485e26ab4faacac7e3abf092f1368447137323b6fb93c1688f7b89d4 |
| web/index.html | 4e29ea13a3ca6cb5f13e57c91fe0d3b83419d93a19e24f3790941fe6fea56294 |
| web/styles.css | 7b5848fdcdf84f5e5dd4256a6153602d7c6c64f89ef67a37d6fc105ecf89752c |
| evaluation/check_browser.py | 33dada3209e641c84e1bee95d20d769125419ad7ab1a65e2f898d326e00439a7 |
