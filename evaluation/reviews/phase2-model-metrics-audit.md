# Phase 2 model/metrics independent audit

Reviewer: plagiarism_research. Initial decision: request_changes, pending focused recheck.
Scope: detector_eval/metrics.py, detector_models/mage.py and requirements-ml.txt; related contract tests inspected. This is software correctness/provenance review, not approval of model accuracy or the datasets I acquired.

## P2-001: Artifact-list omission bypasses pinned-model integrity checks

Location: detector_models/mage.py:147-164 and 222-237 (initial snapshot).
`verify_manifest` validates only files enumerated by the supplied manifest. A manifest containing the expected model/revision/source/label constants, `files: []` and `inference_allowed: true` was accepted in a temporary-directory reproduction. Inference then independently looks for model.safetensors and loads directory configuration/tokenizer files, even if their integrity was never checked. The returned predictions still claim the pinned MAGE revision. This is a provenance/integrity flaw; safetensors and trust_remote_code=False still prevent this from becoming the ordinary pickle-execution path.

Require unique complete expected artifacts, mandatory config/tokenizer records and pinned original weights; bind converted safetensors to the actual audited tensor artifact, not merely a mutable claimed revision. Include missing/omitted artifact and altered manifest-plus-weight regression tests. The backend author was notified and is implementing a fix.

## P2-002: Aggregate recall hides total unseen-generator failure

Location: detector_eval/metrics.py:389-406 (initial snapshot).
Reproduction uses calibration human=.1 and AI=.9 from generator `seen`; test contains 300 correctly scored independent human families, 900 correctly scored AI families from `seen`, and 100 independent AI families from `unseen` all scored .1 (human). With both external evidence assertions true, evaluate returned product_approved=True: overall AI recall=.9, unseen-generator recall=0. The gate checks existence of an unseen generator rather than performance on it. All original20 unit tests passed, demonstrating the missing regression.

Require adequate independent-group sample sizes and row/family recall for each claimed unseen generator, or keep product approval blocked. Unknown generator identities should not silently satisfy completeness. The metrics author was notified and is implementing a fix.

## Other inspected behavior

- Labels are explicit: MAGE class0 AI/class1 human; predictions carry uncalibrated and product_approved=False flags, truncation, input hashes and pinned revision metadata.
- Inference uses local_files_only=True, trust_remote_code=False and safetensors. Conversion verifies the pinned original binary hash and uses torch.load(weights_only=True) with an explicit PyTorch>=2.6 check. Documentary upstream Python is stored as text and not executed.
- Raw-text preprocessing deviation from upstream recommendations is disclosed. Detector training overlap and target-population accuracy remain unverified.
- Metric confusion denominators count abstention separately; source-family false-positive events use any false flag; AI family recall requires all variants correct. Exact-text/group/ID calibration-test overlap is rejected when supplied. One-sided Wilson bounds and absence of author-independence proof are explicitly stated.
- Evidence booleans and frozen-threshold provenance are caller assertions, not authenticated proof. Passing software tests must not be described as measured product validation.
- requirements-ml.txt pins its named Python packages and documents a separate hardware-specific PyTorch installation. This review did not establish a complete transitive lockfile or audit every dependency for vulnerabilities.

## Initial snapshot hashes

Recorded at 2026-09-27T11:29:51.590491+00:00

| Path | SHA-256 |
|---|---|
| detector_eval/metrics.py | e49acef73e99c5440b98ad4a41c0b0efc894c4fce6acc53dc96965fc06592d11 |
| detector_models/mage.py | 55d89347d98eede9a811f01e157195bb05f5b4383e6a378e11afa8abcc74f63b |
| requirements-ml.txt | 58603507379b94fc8ed7be9f53425ab1eecee9c3c68d7f0da02a980cfd944a61 |
| tests/test_detector_metrics.py | 73291a9df8bfaabacb2e0f756640d610be53759a8b3bf5486156fbb099f07e7a |
| tests/test_detector_models.py | 048404c6496105d7490e1b70a26789d8e44320121c65363435d6e61f45a1af7f |

## Focused recheck: P2-002 resolved

Independently read the updated unseen-generator gates and reran all22 metric tests successfully. Each identified unseen generator now needs at least100 known source families and at least80% row/all-variants-correct family recall; missing test generator metadata blocks. The previously failing dominant-seen/catastrophic-unseen case is a regression test. This approves the metrics fix only; research evidence remains absent and P2-001 model-provenance recheck is pending.

detector_eval/metrics.py: `e49acef73e99c5440b98ad4a41c0b0efc894c4fce6acc53dc96965fc06592d11`

tests/test_detector_metrics.py: `73291a9df8bfaabacb2e0f756640d610be53759a8b3bf5486156fbb099f07e7a`


## Focused recheck: P2-001 resolved; software review approved

Decision: approve the inspected metrics and model-adapter software fixes at the hashes below. This is NOT approval of a production AI detector, measured target-domain accuracy, the experimental split, or model/dataset independence. Research gates remain blocked.

The adapter now requires a complete unique artifact set; rejects omissions/substitutions and symlinks; binds every original artifact to hardcoded audited hashes; requires converted weights to name the pinned original hash; and verifies converted safetensors against a canonical-byte hash. Canonical serialization sorts tensor/header metadata and checks the expected resulting checksum before enabling inference. Inference performs full verification and never uses the conversion-only derived-check bypass.

Independently reran9model-adapter tests with actual PyTorch available: all passed, zero skips. These include missing/duplicate/substituted artifact entries, altered artifact plus altered manifest hash, score orientation, truncation, global attention and nonfinite predictions. Independently reran the original empty-artifact-manifest reproduction with correct identity/license fields: it now raises ValueError requiring every pinned artifact exactly once. Together with the22metrics tests and P2-002 regression recheck above, both audit findings are resolved. I did not rerun full checkpoint inference; that experiment remains the implementing agent's separate evidence.

Final inspected snapshot recorded at 2026-09-27T11:31:39.982630+00:00

| Path | SHA-256 |
|---|---|
| detector_eval/metrics.py | e49acef73e99c5440b98ad4a41c0b0efc894c4fce6acc53dc96965fc06592d11 |
| detector_models/mage.py | 0527504e6fb0c525592fbaa995201979e904533d238d917124b5e78a439efea7 |
| requirements-ml.txt | 5aab33e686bb7b64d17fe1b45c35373979ad0dadbdfb54b24721b4c41b463e37 |
| tests/test_detector_metrics.py | 73291a9df8bfaabacb2e0f756640d610be53759a8b3bf5486156fbb099f07e7a |
| tests/test_detector_models.py | 78ba6e781bc1f62fabafba033c686b3886d5aaa135f2c4b957db8b7569555740 |


## Current model-metrics review slot refresh

Recorded at 2026-09-27T11:35:19.840146+00:00

Decision: approve the inspected software scope only; no new blocking findings. Independently executed all 10 current model tests and all 22 metrics tests, with zero failures or skips. The fresh reversed-label fixture and altered-artifact-plus-forged-manifest regression are included. P2-001 and P2-002 remain resolved.

Also inspected evaluation/protocol.json, evaluation/check_authorship.py and detector_eval/reports.py, plus their load_frozen/attach_scores/summarize_scores helpers. Both independent-review and model-metrics-review slots are mandatory. Predictions must cover exactly the frozen IDs, bind to excerpt text hashes, and identify the pinned model revision/preprocessing/token cap. Comparison recomputes metrics and verifies baseline artifact receipts and the complete local MAGE artifact set. Threshold selection uses only calibration rows; fixed-half results are explicitly diagnostic. The adapter always emits blocked and the comparison always states product_approved=false. These paths do not unlock user-facing authorship claims.

Limitations: this audit does not independently repeat full GPU inference, establish benchmark independence, certify dataset rights, audit transitive dependencies, or approve user-facing accuracy. A locally writable prediction receipt is provenance bookkeeping, not cryptographic proof that inference ran. Parent iteration review owns the full split/experiment implementation. Target-population, unseen-generator, mixed-span and retrieval research gates remain blocked.

| Path | SHA-256 |
|---|---|
| detector_eval/metrics.py | e49acef73e99c5440b98ad4a41c0b0efc894c4fce6acc53dc96965fc06592d11 |
| detector_models/mage.py | 0527504e6fb0c525592fbaa995201979e904533d238d917124b5e78a439efea7 |
| requirements-ml.txt | 5aab33e686bb7b64d17fe1b45c35373979ad0dadbdfb54b24721b4c41b463e37 |
| tests/test_detector_metrics.py | 73291a9df8bfaabacb2e0f756640d610be53759a8b3bf5486156fbb099f07e7a |
| tests/test_detector_models.py | 78ba6e781bc1f62fabafba033c686b3886d5aaa135f2c4b957db8b7569555740 |
| evaluation/protocol.json | 2fe8396927af53d5a5fa2dbf25bff45438d5f4318f691e4d3ab43bf115604dd5 |
| evaluation/check_authorship.py | 4f474f8f8b5bcf2a7215494a6f0776ae94febbb962cb2feea07351d9983a86f6 |
| detector_eval/reports.py | 65f993562b9dc6cd625b045646996a2da57379fd3b742842a701fb96006d67db |
| detector_eval/experiment.py | e48f6e1c6d837d3bdaeab701902bae46fb6a72c8a84fda669fcf1c45e2a337ce |
