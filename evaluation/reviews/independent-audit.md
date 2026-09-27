# Independent adversarial audit

Reviewer: plagiarism_research (independent of the reviewed runner, browser and backend implementation).
Decision: request_changes. Static review and targeted local checks; not a penetration test or detector-accuracy validation.

## Findings

### AUDIT-001: Check adapters violate runner evidence schema (high, reproducible)

`evaluation/check_software.py:18` and `evaluation/check_corpus.py:19` emit an object in `evidence`; `iteration/runner.py:266` requires a list. Calling `_check(Path.cwd(), {'id':'corpus','script':'evaluation/check_corpus.py','timeout_seconds':10}, 10)` returned exit code zero but status failed and summary `Check did not emit a valid JSON result: Evidence must be a list.` Thus real software/corpus success cannot satisfy the protocol. Emit a list in both adapters, and exercise each through the runner contract. This fails closed rather than falsely promoting.

### AUDIT-002: Partial positive match results look complete in browser (medium, reproducible)

`web/app.js:85-86` only exposes an incomplete message when there are no matches and never renders `component.warnings`. `turingtint/matching.py` sets a normal positive-match summary even when status is partial. Reproduction: load first two installed source abstracts, concatenate, temporarily set `matching.MAX_CANDIDATES=1` in the test process, call `analyze_sources`. Observed status partial, one match, warning that results are partial, and a normal positive summary. Browser users see only the normal summary and source card. Render status/warnings for every report, including positive matches; preserve this in browser regression coverage.

### AUDIT-003: Child output cap does not cap temporary disk consumption (medium, code verified)

`iteration/runner.py:230-246` redirects both child streams to temporary files, waits for process completion and only then reads a limited stdout prefix. `MAX_OUTPUT_BYTES` limits stored report output, not bytes written by a running child. A buggy allowed check can continuously print to stdout or stderr and fill disk before its timeout; stderr is never size-checked. Enforce a runtime stream/file-size bound and terminate the child tree on breach, or clearly scope the claimed bound to report size. The runner explicitly trusts scripts, so this is a resource robustness issue, not arbitrary-code sandbox bypass. No disk-filling test was run.

## Other reviewed behavior

- Current protocol's empty validation-gate dependencies stay blocked (`bool(dependencies)`); no automatic measured-authorship claim or missing-validation false pass found.
- Already recorded unresolved blocking issues survive removal of their protocol entry because the ledger retains them. Protocol mutation and implementation/input changes alter fingerprints. This does not authenticate reviewer identities or protect against a developer deleting state; trusted-local scope is explicit.
- Browser uses textContent/createTextNode for submitted/source text and HTTP(S)-only source links. No markup execution path found. Source navigation is an explicit external link, while analysis fetches are same-origin.
- Browser revision checks, abort on edits, echoed-text checks and UTF-16 offset checks address stale highlights. No stale-highlight finding in static review; no interactive race test was performed.
- Backend has body/text/token limits, two scan slots, source-candidate/expansion/match limits and a matching deadline. No backend outbound network request found. CLI binds 127.0.0.1; source acquisition is a separate setup command.
- Corpus summary scans and fingerprinting are not part of the matching deadline; large future corpora should be profiled. The installed 12-document corpus does not demonstrate scalability.
- Positive results consistently describe shared wording, not plagiarism verdicts. Authorship is unavailable with null score, not an invented human score.

## Scope note from earlier corpus integration

Backend reviewer independently observed block-boundary concatenation in corpus extraction (for example `doctor.MethodsIn`). This is outside this independent backend/browser/runner audit; I implemented that importer and therefore cannot independently approve it. Parent has been notified to fix block separators and refresh the seed. Metadata attribution also needs an explicit formatted citation. Do not mistake the current provenance smoke check for a retrieval benchmark.

## Snapshot binding

The hashes below bind the actual files read in this review. If any change, this report does not approve the new snapshot; rerun relevant checks and request follow-up review. No application source files were edited during this audit.

Recorded at: 2026-09-27T10:59:19.231564+00:00

| Path | SHA-256 |
|---|---|
| iteration/runner.py | 931080d50bf3da548bca5c7e9a35ae31c5b08813379743b0985dd09af63b16aa |
| evaluation/protocol.json | a1a7c42467c6a7bdceea66b5b3134c74cece0bb50c656a930f4ac65bde267575 |
| evaluation/check_software.py | 232e01c198ea827ccf622bae7951ba05f7e6d4d2c5787cfb2945595ce3115233 |
| evaluation/check_corpus.py | 13b9495eeccfc21db0b3c424029ce3ef16efacb0bc76c36050d17dcfe11ecbd6 |
| web/app.js | 38554b2fe7c0e35ab3ac403c00152ffa5ef7fcbfe0e65840ee1ae4a5b35222e8 |
| web/index.html | 3e5fa11d3460edad48be9be553e6c01c8d84be95022633e1ef5d7783465d18d6 |
| turingtint/app.py | 92785ae069603029cbaa9bfc5da171b2315fb7455ad789d02991b6be72dfd2e7 |
| turingtint/corpus.py | f380548f02bbacee4587398c8c5460a0a0ac84e21979fcfc130d47d409b7d779 |
| turingtint/matching.py | 49d911c300af4bf25b6631419fc43de91cb8f9c974584c51867a254afe85da40 |
| turingtint/text.py | 42fe9fe03b3411a9505112a2630945d42faaf6a962a2b65e893f066a73091598 |
| turingtint/__main__.py | d15f381fcf6bd9487c65168c0dd717a921e343c82e8a532ea47bd0ce2258f47a |
