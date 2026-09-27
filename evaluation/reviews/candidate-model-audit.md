# Independent candidate model audit

Scope: candidate score selection, primary-model runtime policy, raw-logit API, reproducible demo provenance, candidate evidence checker, and protocol input binding. This review excludes my coaching implementation and does not approve scientific accuracy, authorship localization, or product release.

## Finding and resolution

CANDIDATE-001: the protocol initially omitted evaluation/results/phase2-comparison.json even though both calibration receipt verification and runtime loading consume it. The root agent added this exact path to input_paths; independently confirmed before this report. No unresolved blocking software finding in the inspected scope.

## Independent checks

- 34 focused workbench, research API and demo tests passed; evaluation/check_candidate.py passed and reproduced saved outcomes.
- Independently enumerated native-margin cutoffs under family-level empirical error caps: human_max 9.19921875 and ai_min 11.2890625. Calibration has 126 human rows/groups and 167 AI rows in 166 groups; row independence must not be presumed.
- Independently counted saved predictions: calibration TP122/FP1/TN91/FN1 with 34 human and44 AI abstentions; HC3 test TP124/FP1/TN87/FN3 with35 human and39 AI abstentions; AIDE TP1/FP38/TN1077/FN1 with260 human and1 AI abstentions. These reproduce the selected-policy report.
- Independently rebuilt the six demo cases and compared the complete object with the saved fixture. Selection uses provenance/IDs/length, not successful detector scores; the assistant-written challenge remains visible.
- Runtime validates finite two-class logits and consistency with the saved softmax, uses the frozen margin recipe, and leaves missing/truncated primary evidence inconclusive. Secondary TF-IDF cannot veto or replace MAGE. Whole-passage conclusions require consistent covered block evidence; disagreement does not establish mixed authorship.
- Candidate checker recalculates calibration selection and all retrospective diagnostic fields. The scientific authorship gate remains blocked independently of this integrity check.

## Material limitations retained

The margin representation improves retrospective HC3 recall to124/166 (74.7%) and coverage to215/289 (74.4%), but AIDE human false AI flags increase from27/1375 with original MAGE to38/1375 (2.76%). This is an explicit quality regression. Only three AIDE AI examples exist; known source families are not independent authors. HC3 may overlap MAGE training. These previously observed data and empirical one-percent caps cannot support generalization or confidence guarantees. No new model weights were trained by this policy change.

The score repair preserves double-precision ordering lost through float32 softmax saturation. It does not produce calibrated probabilities. Demo provenance labels are evidence about origins, not guarantees of detector correctness. No GPU inference was launched for this audit.

## Inspected snapshot

Recorded 2026-09-27T19:51:10.353264+00:00

- `detector_eval/candidate.py`: `06d2a1e7528726eae16eac1bfff1cd854774ed1ae6f01c8e282e897da1136bc3`
- `turingtint/workbench.py`: `a1c8acffef51d3f39c136e25dc9230ef7e235c8806df11deb5de6260e392358a`
- `turingtint/research.py`: `50c9f5466153378f8b666c25e02369af5a2d34f57f2852dcbb33aaba00d59740`
- `turingtint/examples.py`: `b64dd1c22c69a2b019f6a9666c7798c63915dd9fe8151c55f0afe0ad17eba097`
- `scripts/build_demo_cases.py`: `5e16e1c74a6725e4982339f67f360aa65b7c6092bfdde5b811d105cebb866184`
- `evaluation/check_candidate.py`: `8381eb6a573694a749098f3760abf841377f598de966154e925b805a8216ac3a`
- `evaluation/protocol.json`: `8999fb3014ec112240f5f692a9cd4635b97a28720f63ae3e718ce9eb545d2772`
- `evaluation/results/phase2-comparison.json`: `ae90ca4158d64e6ede0ac690e896ac8cde2fd402730896c6b8573d5594b4055e`
- `evaluation/results/candidate-diagnostic.json`: `17188315e0e0c62c6f88c0c591830a707aa93eff77a3e6e2ccde0b0d24f56058`
- `evaluation/fixtures/demo-cases.json`: `5702d534abcc1fd4d956a8126afb6dd31cf9ef4f6d9f48b2a247ac097983e139`
- `tests/test_workbench.py`: `bea30ee7be345c6087fd6814abbdfb2d8ab483a3846e5c1b67dbb41887ec05f6`
- `tests/test_research_api.py`: `8ff9a7fe31c604c61a8bf22b7aab2298e50178af1e8bcdb9fdf8572a235a4416`
- `tests/test_examples.py`: `47b99598abccf8cbd4b3f63a6e2b74952bf1993c29e4ab1b55009cbbb9ac1048`

## Final comparison-eligibility delta

Independently inspected the final backend/frontend delta after the real UI exposed
an88-to79-word revision. Backend leaning_supported defaults false and becomes true
only for fully scored supported-length contexts with verified thresholds; aggregate
eligibility requires every context. Context-length status and minimum words are
explicit. These additions describe existing eligibility and change the displayed
reason; they do not modify weights, raw-logit recipe, frozen cutoffs or _lean logic.

CANDIDATE-002 found during this recheck: the first UI patch checked length alone,
ignoring per-model threshold eligibility. A later permissive check also admitted
missing eligibility metadata. Resolved: comparableModels requires explicit true
on both versions. Browser regressions cover false and missing metadata even at
equal character counts, as well as an actual88-to79-word edit. Unsupported versions
show Not comparable, not a revision-driven signal change.

Independent validation:23 workbench tests passed; direct80/79-word and missing-
threshold probes confirmed eligibility false with raw scores still available.
Eighteen mocked browser integration checks passed, including explicit eligibility,
minimum-length explanation, model/schema changes, unavailable models and stale
response invalidation. These checks use mocks and make no quality or GPU-inference
claim. The separate actual UI run is outside this report's test claim.

Snapshot comparison confirmed candidate selection code, raw-logit adapter, frozen
phase2/candidate receipts, demo provenance builder/fixtures and protocol unchanged
from the earlier inspected snapshot. Updated files are fingerprinted below. Scope
still excludes my coaching implementation and does not approve model accuracy,
rewrite factuality or scientific release. No unresolved blocking software finding
remains in this inspected comparison/model scope.

Delta recorded 2026-09-27T20:13:58.839392+00:00

- `turingtint/workbench.py`: `7fbc1b9287c16a9f19cce318a51401c0c38b8c18ae69e7fdaa04293d783851a3`
- `tests/test_workbench.py`: `8bf341e0b095c0ff66dcfb89199cc52ad21dea1907c530f3eb82b31da293d87e`
- `web/app.js`: `73125ad3485e26ab4faacac7e3abf092f1368447137323b6fb93c1688f7b89d4`
- `evaluation/check_browser.py`: `33dada3209e641c84e1bee95d20d769125419ad7ab1a65e2f898d326e00439a7`
- `evaluation/protocol.json`: `8999fb3014ec112240f5f692a9cd4635b97a28720f63ae3e718ce9eb545d2772`

Final binding: 2026-09-27T20:18:01.926781+00:00 independently recomputed the complete implementation/input/config fingerprint using iteration.runner.fingerprints; it matches final run20260927T201454-11b2d937af7b subject `babe1b3a8997d2a4d1b1a8a3375eb8dfe8cb3f078c7dd1afb7fa08ba34411717`. Separate reviewer integration evidence reports83 actual UI checks and the corrected79-word Not comparable display. This scoped approval excludes reviewer-authored coaching code and all scientific/semantic quality approval.
