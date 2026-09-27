# Feasibility with free components and user monitoring only

Updated 2026-09-27. This narrows the earlier implementation and corpus plans to the user's latest constraint: the assistant carries out engineering, curation and automated evaluation; the user monitors rather than supplying annotations or recruiting reviewers. No paid detector, hosted LLM or paid compute is a required component.

## Recommended deliverable

A local English academic/student writing assistant with calibrated paragraph-level AI signals, conservative sentence highlights when validated, exact/near-exact source matches within an identified local library, and evidence-grounded writing suggestions. Mixed-authorship and semantic source-reuse estimates remain experimental unless appropriate independent data supports their release.

The best opportunity for high precision is retrieved exact source evidence and selective AI flags within a tested domain. Universal authorship accuracy, definitive human-only labels, arbitrary word-origin attribution and whole-web plagiarism coverage are not established by this setup.

## Hardware observed

Read-only system inspection found NVIDIA RTX 3050 6 GB Laptop GPU (6,144 MiB reported by nvidia-smi), about 15.6 GiB usable system RAM and 78.1 GiB free disk. These observations are a feasibility input, not measured model performance. Use compact encoder inference, small batches and sequential model loading. Corpus indexing belongs on CPU/disk; optional local explanation generation must not compete with detector training for GPU memory.

## Free-component baseline

| Component | Implementation direction | Validation boundary |
|---|---|---|
| Detector baseline | Compare licensed existing classifiers against a simple text-classification baseline | Existing model scores are uncalibrated for this audience until tested. |
| Domain adaptation | Small encoder with a classification head, if baseline errors justify it | Memory/throughput smoke test before any larger run; no training a language model from scratch. |
| Paragraph and sentence analysis | Context windows and explicit offsets | Paragraph accuracy does not establish sentence accuracy; test each separately. |
| Plagiarism source matching | SQLite/full-text retrieval, shingles and exact/near-exact passage alignment | Only the installed corpus is searched; topic similarity alone is insufficient evidence. |
| Explanations | Deterministic templates grounded in scores and source matches | Optional local instruction model may improve readability but cannot certify authorship. |
| Interface | Local web UI and Python backend | Network isolation, original-text offsets, partial failures and report versioning are testable. |

Candidate model references: [MAGE checkpoint](https://huggingface.co/yaful/MAGE) declares Apache-2.0 and provides a trained classifier; [DeBERTa-v3-small](https://huggingface.co/microsoft/deberta-v3-small) declares MIT but is a base encoder, not a ready-made detector. It includes embedding parameters in addition to its 44M backbone; do not use the backbone count alone for memory sizing. Add newer licensed detectors only after reviewing their actual artifacts and independent results. [Binoculars](https://github.com/ahans30/Binoculars) is a research comparator, not the default deployment dependency on this hardware.

## What can be completed autonomously

Source/license inventory; permitted downloads; provenance manifests; parsing and deduplication; public-dataset splits; local generation with recorded settings; classifier comparison/adaptation; calibration; benchmark reporting; local reference indexing; frontend/backend implementation; integration tests; offline checks; reproducible packaging; and decision logging.

The process should produce a usable limited-scope product even if ambitious AI-detection gates fail: retain verified source matches and editorial feedback, expose only supported AI conclusions, and publish failed cases rather than conceal them. Continuing research is not a reason to invent a passing metric.

## Replace the human-review dependency

Earlier plans proposed new consented writing, true human post-edits and independent human ratings. Those are no longer prerequisites for the active prototype because the user will only monitor. Use suitable existing human-authored datasets and documented edit-history datasets where rights and labels are adequate. Preserve provenance strength and known limitations rather than treating every public essay as certified human-only.

Controlled sentence insertions and AI revisions can be generated locally with known operations. They support tests of those operations; an LLM impersonating a human editor does not supply real human–AI collaboration data. Likewise, an AI reviewer can identify candidate problems but cannot be reported as an independent human evaluator.

Therefore keep the following claims unverified without suitable independent evidence: accuracy on real human rewrites, exact AI contribution within an edited sentence, human-rated usefulness of suggestions, and fairness for inadequately represented student populations. The application can still be delivered with conservative labels and explicitly bounded tests.

## Accuracy and scope gates

Keep the earlier numerical gates as hypotheses to test, not estimates of expected performance. Prioritize: verified exact-match precision; human false-positive control; AI precision; then useful recall and coverage. Measure all of them together. A detector that answers only easy cases must report its abstentions.

Suggested scoped targets remain human false AI-involvement upper 95% confidence bound at most 1%, confident AI-highlight precision lower bound at least 95%, and exact source-match precision lower bound at least 98%, each with adequate independent samples and the definitions in the product plan. No such result exists yet. Fewer false accusations may require lower AI recall, especially on edited or unseen-model text.

Run the actual paragraph-length distribution, with short-input buckets tested separately. Do not restrict to long essays and then advertise the result for a pasted short paragraph. Use fresh generated outputs and unseen model families where possible; acknowledge that public test data may overlap an existing checkpoint's training corpus.

Two measures must remain separate: conditional alignment performance when the source is in the index, and end-to-end retrieval performance when it may be absent. Similarly, quality-preserving suggestions and movement of a detector score are separate results.

## Deliverable order

1. Acquisition and hardware report: exact dataset/model licenses and hashes, usable row counts, source overlap, memory use and timing. Select the first viable local detector candidate.
2. Reproducible evaluation report: split definitions, paragraph false positives/recall, confusion matrices, length/domain breakdowns and abstention coverage. Tune only on development/calibration data.
3. Local source-match engine and web report: paste text, optional detector result, source evidence, text-accessible highlights and uncertainty states.
4. Targeted classifier iteration: change data or model only in response to a documented error category; compare at the same false-positive operating point.
5. Grounded suggestions and packaging: reasons for edits, preserved citations/numbers, explicit rescan, reproducible setup and known limitations.

This sequence does not require the user to write code or label examples. Credential/account choices, terms acceptance, paid expenditure and public deployment remain user-controlled when applicable. Such dependencies should be avoided in the free local prototype when a suitable alternative exists.

The earlier calendar estimates assumed available human reviewers and should not be treated as a commitment under this setup. Estimate runtime from actual download, indexing and training measurements after the first milestone. Work and long-running jobs require an active session or explicitly launched local process; this plan does not imply unattended progress while the assistant is inactive.

Free here means no required license/API/compute rental fee. Existing hardware, storage, internet and electricity still provide resources. A local working application is feasible; a permanently available public service introduces separate hosting and operating requirements.
