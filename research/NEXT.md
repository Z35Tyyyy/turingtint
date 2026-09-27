# Next iterations

The prototype has working source comparison and an evidence loop. It is not yet a validated AI detector. Keep these tasks linked to the open gates in `evaluation/protocol.json`.

1. **Retrieve an openly licensed essay seed.** Pin AIDE/ASAP artifacts and license evidence; inspect labels, prompt families, duplicate/source overlap and usable sample counts. No automatic terms acceptance or paid services. Keep paragraphs from one essay together.
2. **Benchmark local classifiers.** Compare a simple baseline and a licensed pretrained checkpoint on a frozen development set. Record resource use, class mapping, length buckets, human false-positive rate, recall and abstention. Published scores do not transfer automatically.
3. **Implement calibration and a held-out authorship check.** The authorship gate stays blocked until code calculates the declared metrics on independent evidence. Do not infer authorship from source matches or generic writing style.
4. **Benchmark retrieval separately.** Expand beyond the 12-abstract engineering seed; freeze exact/light-edit/quotation/common-phrase/same-topic/source-absent cases. Report corpus coverage separately from alignment correctness. Unit fixtures and the demo passage are not the accuracy test.
5. **Study mixed text and localization.** Find rights-audited workflow labels or use honestly labeled synthetic operations. Real human post-editing remains an evidence gap; do not substitute AI impersonation.
6. **Improve suggestions after evidence exists.** Preserve factual details and attribution; never claim that lowering a model score proves human authorship.

For every iteration: record hypothesis → implement bounded change → test → independent review → fix → rerun → retain unresolved gaps. The current journal remains `training/decisions.jsonl`; `.iteration/` contains local run history and issue states.
