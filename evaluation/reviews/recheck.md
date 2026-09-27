# Independent fix recheck

Reviewer: plagiarism_research. Recorded at 2026-09-27T11:03:49.129872+00:00.
Decision: approve the reviewed software fixes only. No detector-accuracy, mixed-authorship localization or general retrieval benchmark approval is implied.
Subject SHA-256: `f8c852abd4433c58a36a691642c7bf729ae61423d936ef50b3a8da9fb866852d`.
Completed verification run: `20260927T110253-cd290f15f052`.

## Resolutions

- **AUDIT-001 resolved:** both check adapters now emit evidence lists accepted by the runner. Independently reran the corpus adapter through `_check`; it passed and verified 12 sources, attribution/license evidence and text hashes. The unchanged completed run records 45 software tests, zero failures/errors/skips and a passed software adapter.
- **AUDIT-002 resolved:** `web/app.js` renders an explicit incomplete-analysis warning independently of whether source matches exist. I read the updated browser regression: it intercepts an otherwise real positive report, marks status partial and injects a warning, then asserts both a source card and visible warning. Independently reran that browser check through `_check`; all six integration assertions passed, including this regression, stale-report invalidation, literal markup rendering, mobile overflow and absence of external requests/page errors.
- **AUDIT-003 resolved:** temporary-file output redirection has been replaced with bounded nonblocking pipes. Each stream is counted at runtime and exceeding 1 MiB fails and terminates the child tree; retained stdout is at most 1 MiB and stderr at most 4,000 bytes. Independently ran the runaway stdout/stderr, dual-stream draining, and inherited-handle deadline tests: all three passed (1.618 seconds total). The runtime remains a trusted-check runner, not a security sandbox. The inherited-handle test explicitly cleans up its deliberate Windows orphan; this review does not claim arbitrary descendant containment after a parent exits.

No new blocking findings in this focused recheck. The current completed run still blocks the authorship-validation, mixed-span-validation and retrieval-benchmark gates as intended. Current fingerprints were recomputed and matched the completed run before issuing this review. The earlier independent-audit.md remains the historical request-changes record.

## Source hashes

| Path | SHA-256 |
|---|---|
| iteration/runner.py | 39ba0aa1be5fcf41f365f47b27f50308063b88c002ad65adf4457b8843e58143 |
| evaluation/protocol.json | 23d2090a15da5b53cc199ace1d106955cb4a277e9320f2f6c97c7ce73cd7ed5c |
| evaluation/check_software.py | abf19c49244e49bca99f8d46b9c12ff2663214caac2926ca162e841b2376bea3 |
| evaluation/check_corpus.py | 8f79c94e76684f9f15bfc7505d6fab91ce11c68d98dc26c5502ce14f8588fe8e |
| evaluation/check_browser.py | 3d6c1fe88490156ca920c823fca41a059e0e13871cb10122fad6605d294526ee |
| web/app.js | fc06579998d9981a1c9e0b273a0376ab0d242fcd9edd2d01c9b87eb9c8d12d28 |
| web/index.html | e4e8a978d33f840df3ad894be0512ac817fee761a65d993b4edce74f8a431efe |
| tests/test_iteration.py | 4188af01b302fc717ef6c3ac1bf7db42fac50039e5577962616579c811cf13df |
| turingtint/app.py | 92785ae069603029cbaa9bfc5da171b2315fb7455ad789d02991b6be72dfd2e7 |
| turingtint/corpus.py | f380548f02bbacee4587398c8c5460a0a0ac84e21979fcfc130d47d409b7d779 |
| turingtint/matching.py | 49d911c300af4bf25b6631419fc43de91cb8f9c974584c51867a254afe85da40 |
| turingtint/text.py | 42fe9fe03b3411a9505112a2630945d42faaf6a962a2b65e893f066a73091598 |
