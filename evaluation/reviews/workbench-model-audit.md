# Workbench model and API independent review

Reviewer: plagiarism_research. 2026-09-27T19:14:38.738343+00:00

Decision: approve inspected software scope, with scientific validation still blocked. Independently executed 16 workbench model/artifact tests and 7 workbench API tests: all passed. No blocking findings in the inspected code. This review excludes coaching.py implemented by this reviewer and excludes frontend behavior assigned to another reviewer.

Thresholds are recomputed only from declared calibration rows, and checked against the phase-2 comparison, frozen-record/prediction hashes, training receipt and pinned MAGE artifacts. Missing or inconsistent evidence disables model leaning labels rather than inventing a threshold. Baseline pickle loading uses the exact trusted-local bytes checked against its receipt; this does not authenticate an untrusted receipt or make arbitrary pickle safe. Inputs cannot supply model paths.

The wrapper enforces the 512-token MAGE experiment setting and treats token truncation or inconsistent metadata as inconclusive/unavailable. Context blocks preserve all original text and UTF-16 offsets. Scoring is bounded to 12 windows, with explicit unscored remainder. Fewer than 80 words receives raw scores without leaning. Whole-passage leaning requires complete two-model coverage and consistent block decisions. Score means are diagnostic only; thresholds are never applied to averaged scores. Disagreement is not classified as mixed authorship. Output says experimental/product_approved=false/validated=false and disclaims probabilities, plagiarism and validated localization. These conventions still require empirical target-population evaluation before any accuracy claim.

The API defaults to local coaching and requires explicit cloud-provider selection. Host/origin/body/input guards remain active, credentials/custom endpoints cannot be supplied through the body, status does not load models, and exceptions are sanitized. The shared nonblocking GPU lock is acquired before MAGE load/inference and released on all guarded paths. Coaching oversize/token-budget failures return component unavailability rather than silently shortening the passage. No new API-level submitted-text persistence was found.

| Path | SHA-256 |
|---|---|
| turingtint/workbench.py | 269fc5eadd1a5feb51297294fa2a0ff5d395fe5770163b6304dba2ca917a59dc |
| tests/test_workbench.py | efaa1cad046c6ecd6ed2a3aac499aabd8cc5bf921b6f8f8639efa67f19c6be4d |
| turingtint/app.py | 1514a483d969a77ee1f7cb898e49424889bf3622de6376c4142d928da884739f |
| turingtint/research.py | 78162cae707b8345d3c954c8e6c8a7de3c4db6a0bcdc3ff3e28abd58b85083fc |
| tests/test_workbench_api.py | e83e78c2c3b47e7312a7eb1ad13b1d3441bf6012c04912a985b4dbdbe8e9df95 |
| detector_eval/metrics.py | e49acef73e99c5440b98ad4a41c0b0efc894c4fce6acc53dc96965fc06592d11 |
| detector_eval/experiment.py | e48f6e1c6d837d3bdaeab701902bae46fb6a72c8a84fda669fcf1c45e2a337ce |
| evaluation/results/phase2-comparison.json | ae90ca4158d64e6ede0ac690e896ac8cde2fd402730896c6b8573d5594b4055e |

Actual local artifact check: load_verified_thresholds() completed successfully against the installed phase-2 evidence and recomputed TF-IDF human_max=0.3748099081460813/ai_min=0.6359574963543734 and MAGE human_max=0.9998989105224609/ai_min=0.9999876022338867. These are provisional score cutoffs, not probabilities or validated target-domain operating points.

## Guided-decoding privacy helper independent review

2026-09-27T19:22:21.210110+00:00

Read turingtint/guidance.py, tests/test_guidance.py and all logging sites in the installed lm-format-enforcer tokenenforcer.py. The helper changes only that dependency module's logging name binding, implements ERROR/basicConfig/debug/exception without retaining arguments, and leaves global/application logging untouched. A new parser and token-prefix state are created per request. Independently ran all three helper tests, including actual forced internal parser error, EOS fallback, absence of passage/exception logging and preserved control logging: passed, zero skips. No blocking finding in this helper. It is not a guarantee against every future dependency logging change; dependency version and regression coverage remain relevant.

| Path | SHA-256 |
|---|---|
| turingtint/guidance.py | d9b521f7a3a11b1f5fa37798c36a174f09e1a44bd2b62b2cdc25e88d1a503d98 |
| tests/test_guidance.py | 97484ff1aa9feb56a5b2162e0f22b53bcdb096838907ac76fd40346d6b0aea2b |

Final subject verification at 2026-09-27T19:23:20.093741+00:00: all current implementation/input artifacts match completed run 20260927T192206-929d64dd7977 and subject `d06d7647805bc76989cbfb2ffcb64b88199fb59bb17bf2268e3e7f51aedf7be1`; all separately inspected file hashes above also still match. Scoped approval excludes coaching.py, its implementation tests and frontend behavior, and does not approve accuracy or scientific validation.
