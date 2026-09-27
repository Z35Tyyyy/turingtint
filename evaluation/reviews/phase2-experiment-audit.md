# Independent phase 2 experiment audit

Reviewer: `iteration_framework`, independent of the experiment preparation,
training, and report implementation. I implemented `detector_eval/metrics.py`;
this report is **not an independent audit of that metrics library**. Its separate
unseen-generator finding was supplied by another reviewer and fixed with tests.

Initial review checkpoint: 2026-09-27T11:31:43.688115+00:00.
Final artifact follow-up: 2026-09-27T11:35:56.146083+00:00.

Decision: **approve within the independent-review scope**. The corrected
experiment code and recomputed comparison are suitable for the explicitly limited
engineering diagnostic. No product accuracy, student-writing generalization,
pretraining independence, or sentence/mixed-authorship approval is given. The
completed-artifact checks are recorded below; the separate model/metrics reviewer
provides independent assessment of the components I implemented.

## Material findings and verified fixes

### EXP-001: Fixed-threshold diagnostic required nonexistent calibration metadata — resolved

`summarize_scores` originally called `evaluate(..., require_prompt_disjoint=True)`
for a predefined threshold object without calibration prompts. That always
raised `Prompt-disjoint evaluation requires known calibration and test prompts`
and prevented report generation. The parent removed the impossible requirement
from that fixed diagnostic; the calibrated test evaluation still checks actual
calibration/test prompt separation first. A four-row calibration/test fixture
now completes and keeps `product_approved: false`.

### EXP-002: Removed source-family bridge could permit cross-split leakage — resolved

Reproduction: retained `left` and `right` source families, related-source entries
`[removed, left]` and `[removed, right]`, and no retained `removed` record. The
original implementation filtered absent families before joining them; the
`left0` fixture went to train and `right0` went to test. Their source families are
connected through the omitted node and should remain together.

The corrected implementation preserves abstract `source_group:` nodes, including
absent ones, and connects retained records to those nodes. The same fixture now
has one split unit and one split. The regression
`test_removed_bridge_still_joins_retained_families` passes.

I separately compared all relationships in the current HC3 acquisition manifest
against prepared splits: there were **zero affected cross-split components in
that installed release**, even before the fix. Regeneration after the fix exactly
matches the frozen HC3 records; this correction does not silently repartition the
existing experiment.

### EXP-003: Matching prediction IDs could attach scores for stale text — resolved

`attach_scores` originally accepted a prediction for ID `one` with a supplied
text digest different from the frozen excerpt's digest. The reproduction
accepted score `0.99` despite the mismatch. IDs alone do not bind a score to the
scored excerpt.

The corrected implementation requires complete, unique prediction IDs and a
matching text hash. It explicitly distinguishes raw UTF-8 hashes from normalized
excerpt hashes. The mismatch now raises `Prediction text hash does not match the
frozen excerpt`. The relevant regression passes. `reports.py` uses normalized
hashes for saved baseline predictions and raw hashes for MAGE outputs, matching
their producer contracts.

## Other verified behavior

- Eight tests in `tests/test_detector_experiment.py` passed independently.
- Input content hashes are checked before excerpt preparation. Contradictory
  full-text labels raise an error; contradictory clipped-excerpt labels are
  quarantined before splitting. Repeated normalized excerpts are dropped.
- One deterministic excerpt is produced per retained document: a natural
  80–250-word paragraph when available, otherwise a short whole document or the
  first 250 words. Mid-sentence clipping is explicitly recorded and is not
  presented as sentence localization evidence.
- Source families, prompts, duplicate full text, and duplicate excerpt text are
  joined before the stable split decision. Row ordering does not change output.
- `load_frozen` checks the frozen records hash and disjoint IDs, split units,
  source groups, prompts, and text hashes. A temporary fixture with a shared
  component in train and test was rejected as cross-split leakage.
- The TF-IDF feature union and logistic model fit only the train partition.
  Hyperparameters are fixed in code, with no test-driven search. Threshold
  selection receives calibration rows; the separate test receives frozen
  thresholds. These facts were checked in code, not by independently retraining
  a second model during this audit.
- Missing author/source independence is retained as unknown. The frozen manifest
  explicitly sets author and near-duplicate independence to false.
- `reports.py` verifies frozen data and baseline model/prediction receipts,
  validates the pinned MAGE manifest and declared prediction preprocessing, and
  recomputes diagnostics from text-bound predictions.
- `evaluation/check_authorship.py` returns `blocked` for a successful diagnostic
  and `failed` for missing/inconsistent artifacts. It cannot turn this experiment
  into a product-authorship pass. No product detector integration was added.

The installed HC3 preparation contains 1,464 retained excerpts: train 389 human /
493 AI; calibration 126 human / 167 AI; test 123 human / 166 AI. These are
engineering split counts, **not independently validated population sample
sizes**. Of the excerpts, 702 are classified as natural paragraphs, 517 as whole
short documents, and 245 as potentially mid-sentence 250-word clips.

## Resource-report wording — resolved in follow-up

The initial `reports.py` resource summary hardcodes `batch_size: 1` and sums
per-record `batch_elapsed_ms`. The prediction producer accepts batches up to four
and repeats the batch timing on each row; records did not encode batch size at
this checkpoint. With batches larger than one, the sum would overstate elapsed
time. The current declared run uses batch size one, so this does not invalidate
its classification metrics. Bind batch configuration in prediction metadata and
describe this timing as model-forward time because tokenization is excluded.

The corrected report removes the unverified numeric batch-size field and names
the quantity `summed_per_record_model_forward_seconds`. Its scope explicitly
excludes loading and tokenization, discloses repeated batch timing for larger
batches, and identifies this experiment's CLI batch-size-one invocation. This
resolves the claim made by this diagnostic. A future general throughput benchmark
should still record batch configuration in the producer's own receipt.

## Completed comparison and protocol follow-up

I called `build_comparison(Path.cwd())` after both MAGE prediction files were
complete. The result exactly matches
`evaluation/results/phase2-comparison.json`, excluding its newly generated
timestamp. This rechecks frozen input hashes, baseline receipts, the pinned MAGE
manifest, score metadata, text bindings, and metric/report assembly.

I also independently counted predictions using the exported frozen thresholds,
without calling the metric helpers. False-AI counts, AI true-positive counts,
answered counts, human coverage, overall coverage, and the corresponding ratios
matched for all eight model/subset combinations: calibrated and fixed-half
diagnostics on both the HC3 test split and external AIDE data.

| Calibrated diagnostic | Human false-AI flags | AI true positives | Conclusive coverage |
|---|---|---|---|
| TF-IDF/logistic, HC3 test | 0 / 123 (0%) | 124 / 166 (74.7%) | 217 / 289 (75.1%) |
| MAGE raw text, HC3 test | 1 / 123 (0.81%) | 113 / 166 (68.1%) | 204 / 289 (70.6%) |
| TF-IDF/logistic, AIDE external | 67 / 1,375 (4.87%) | Only three AI examples; no useful recall conclusion | 186 / 1,378 (13.5%) |
| MAGE raw text, AIDE external | 27 / 1,375 (1.96%) | Only three AI examples; no useful recall conclusion | 1,106 / 1,378 (80.3%) |

Coverage materially changes interpretation: the baseline answered only 186 human
AIDE cases and falsely flagged 67 of them (36.0% answered-human FPR); MAGE answered
1,104 human cases and falsely flagged 27 (2.45%). The report preserves both the
all-human and answered-human denominators. Neither comparison supports a student
writing release. Even the baseline's zero false flags on 123 HC3 human examples
has a reported one-sided Wilson upper bound of approximately 2.15%, conditional
on the independence assumption; author independence is not verified here.

Running `python evaluation/check_authorship.py` completed with exit code zero and
a valid JSON result whose status is **blocked**. Both model entries and the
comparison-level `product_approved` fields remain false. The protocol now includes
the authorship data, detector implementations, frozen inputs, model files, and
prediction artifacts in its fingerprints. Its authorship-validation gate depends
on that explicitly blocked check; mixed-span and retrieval-benchmark gates remain
unfulfilled. Review approval cannot override those missing scientific gates.

The scored MAGE artifacts report zero token truncations for these prepared
excerpts. The comparison nevertheless correctly preserves the raw-text/512-token
recipe limitation and does not advertise the upstream model's published accuracy
as the measured behavior of this local setup.

Follow-up artifact binding:

| Reviewed file | SHA-256 |
|---|---|
| detector_eval/reports.py | 65f993562b9dc6cd625b045646996a2da57379fd3b742842a701fb96006d67db |
| evaluation/protocol.json | 2fe8396927af53d5a5fa2dbf25bff45438d5f4318f691e4d3ab43bf115604dd5 |
| evaluation/results/phase2-comparison.json | ae90ca4158d64e6ede0ac690e896ac8cde2fd402730896c6b8573d5594b4055e |

## Initial snapshot binding and limits

This table records the initial checkpoint. The later `reports.py` hash and the
completed comparison validation in the follow-up section above supersede its
initial report-code hash; artifact validation is complete, not pending.

| Reviewed file | SHA-256 |
|---|---|
| detector_eval/experiment.py | e48f6e1c6d837d3bdaeab701902bae46fb6a72c8a84fda669fcf1c45e2a337ce |
| tests/test_detector_experiment.py | f84fa9732e08e6f0bcfe484b3ea4dcf08a623f0d8110d33c7ae315ae9acea5f1 |
| detector_eval/reports.py | b1be7d0c6a9306c3a5c543150ac4b856cd70a565f171aa4ae682ff1bd1048ef9 |
| evaluation/check_authorship.py | 4f474f8f8b5bcf2a7215494a6f0776ae94febbb962cb2feea07351d9983a86f6 |

These hashes bind the code examined at the checkpoint. Later changes and actual
comparison artifacts require follow-up verification. This audit does not prove
that benchmark text is absent from pretrained model training, that family IDs
identify independent authors, or that diagnostic performance transfers from
Wikipedia question answering to academic/student writing.

## Final iteration binding

At 2026-09-27T11:37:48.468709+00:00, I verified that completed run
`20260927T113628-5440b0fb9678` and a fresh fingerprint of the current protocol,
implementation, and declared inputs both have subject SHA-256
`162fa6063d3277ce3a40a6fae11bf0069b3b11504711fb38ec38163d82472976`.
The inspected experiment, report, check, protocol, and comparison hashes remain
identical to their reviewed snapshots. The run records passing software, corpus,
and browser checks and an intentionally blocked authorship check.

The accompanying `phase2-experiment-review.json` approves only this scoped
engineering review, explicitly resolves EXP-001/EXP-002/EXP-003, and leaves the
scientific release gates intact. Independent model/metrics review remains a
separate slot because I implemented the metrics library.
