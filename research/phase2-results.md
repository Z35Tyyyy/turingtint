# Phase 2: actual local detector comparison

Completed 27 September 2026. Two working local classifiers were evaluated on
frozen excerpts. **Neither is approved for user-facing authorship decisions.**
The next improvement should address target-domain data and generalization.

## What was acquired and trained

The public AIDE release contains 1,375 human-labeled essays and only three
AI-labeled essays. All 1,378 were reserved for external diagnostics. HC3's
rights-audited Wikipedia CS/AI subset provides an engineering fallback, with
1,464 usable excerpts after length filtering. Linked families are kept together;
the fixed split contains 882 training, 293 calibration and 289 test examples.
See the [corpus audit](corpus-acquisition-phase2.md) for licenses and exclusions.

A word/character TF-IDF logistic classifier was trained on 882 examples with
fixed parameters. Training and prediction took about 4.9 seconds with two CPU
threads. The pinned Apache-2.0 MAGE checkpoint was downloaded and safely converted
for local inference. Both classifiers received the same frozen excerpts.

MAGE scored 2,842 excerpts on the RTX 3050 Laptop GPU. Forward passes averaged
about 55 ms per excerpt; this excludes tokenization and model loading. Peak
PyTorch allocated GPU memory was 335 MiB. All excerpts fit the chosen 512-token
cap without truncation. The download was approximately 598 MB; the retained
original and converted weights together occupy roughly twice that space.

## Measured results

Thresholds were selected once using HC3 calibration data. The gap between the
human and AI thresholds means **uncertain**, not mixed authorship. Coverage is
the fraction receiving either conclusive label. AI recall counts abstentions
as misses. Human false flags use all human-labeled examples as the denominator.

| Model | HC3 human false flags | HC3 AI detected | HC3 coverage | AIDE human false flags | AIDE coverage |
|---|---:|---:|---:|---:|---:|
| TF-IDF + logistic regression | 0/123 (0%) | 124/166 (74.7%) | 75.1% | 67/1,375 (4.87%) | 13.5% |
| MAGE, raw-text variant | 1/123 (0.81%) | 113/166 (68.1%) | 70.6% | 27/1,375 (1.96%) | 80.3% |

MAGE made fewer false AI accusations on these student essays and answered more
often than the simple baseline. This does not establish AI recall on student
writing: AIDE has only three AI cases. No meaningful high-accuracy claim follows.

Zero mistakes on 123 HC3 human examples also does not establish a true rate below
1%. The baseline's one-sided 95% Wilson upper bound is 2.15%, assuming independent
families. MAGE's corresponding upper bound is 3.56%. This collection does not
establish author independence, and possible checkpoint training overlap remains
unverified. Both models miss the configured 80% HC3 AI-recall target.

The separately reported fixed 0.5-score diagnostic produces 654 baseline and
598 MAGE false AI flags among the 1,375 AIDE human essays. It is **not** MAGE's
published deployment rule; upstream uses preprocessing and a raw-logit boundary.
This raw-text experiment does not reproduce that recipe. MAGE's selected softmax
thresholds are close to one, which further illustrates why raw scores cannot be
presented as percentages of AI-authored text or calibrated authorship probability.

The [machine-readable aggregate report](../evaluation/results/phase2-comparison.json)
contains thresholds, confusion counts, coverage, length subgroups, bounds,
artifact hashes and blocked gates. Raw essays and per-record predictions remain
local and are excluded from Git. [Reproduction instructions](../detector_eval/README.md)
define acquisition, freezing, training, inference and report reconstruction.

## What the review loop changed

Independent reviewers found and verified fixes for five material problems:

- A fixed-threshold diagnostic incorrectly required nonexistent calibration metadata.
- Removing duplicate-family bridge nodes could split related examples across partitions.
- Predictions could be joined to stale text using IDs alone; text hashes are now mandatory.
- A model manifest could omit files; every artifact is now independently pinned and required.
- Strong aggregate recall could hide complete failure on an unseen generator; every unseen generator now needs sufficient support and recall.

The grouping fix did not change any already-frozen HC3 record or partition.
No settings were tuned using the test outcomes. The final check recomputes both
models' metrics from verified artifacts, and the iteration protocol retains all
authorship, mixed-span and retrieval-validation blockers.

## Decision and next experiment

Keep the pretrained approach as a candidate for further development; reject both
current operating points for release. Preserve these datasets as now-observed
diagnostic sets. They must not later be renamed as untouched final tests.

Acquire a rights-verified legacy student corpus spanning more assignment prompts,
then create a bounded, documented contemporary AI counterpart using local models.
Keep all variants of one assignment/source together and reserve entire prompt
families and at least one generator for a new evaluation. Human examples must
come from actual published human writing; generated imitations never become
human labels. Compare domain training, preprocessing and logit calibration on
development data before freezing the next test.

Mixed-span highlighting and plagiarism retrieval require their own evidence.
The existing source-matching web app remains usable; authorship scores stay unavailable.
