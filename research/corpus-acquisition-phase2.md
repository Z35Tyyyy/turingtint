# Phase 2 corpus acquisition: actual availability and limits

Completed 27 September 2026. Artifacts and timestamps are recorded under
`data/authorship/`; no split or model training was performed by the acquisition
tools. Nine parser, license and grouping tests pass.

## AIDE: public release is much smaller than the catalog description

The Learning Agency's current [official catalog](https://the-learning-agency.com/guides-resources/datasets/)
links to [this exact Kaggle release](https://www.kaggle.com/datasets/lburleigh/tla-lab-ai-detection-for-essays-aide-dataset)
and specifies CC BY 4.0. Anonymous Kaggle metadata independently agrees. Downloaded
version 5, updated 21 October 2024, contains a 1,688,645-byte ZIP with three members:
`AIDE_train_essays.csv`, `train_prompts.csv`, and a regeneration-instructions DOCX.

The **actual CSV has 1,378 essays: 1,375 human and 3 AI**, not the catalog's roughly
10,000 essays/seven prompts. Actual prompt counts are:

| Source prompt | Human | AI |
|---|---:|---:|
| 0: Car-free cities | 707 | 1 |
| 1: Does the electoral college work? | 668 | 2 |

No generator names or student/author identifiers occur in the essay CSV. The
unique essay ID supplies document lineage, not author identity. No exact duplicate,
label conflict or approximate near-duplicate pair was found. The source fields
are retained privately for audit.

The DOCX was inspected as XML, without executing its code. It describes synthetic
generation using Palm 2, Gemini 1.0 variants and GPT-4, three-shot student examples,
deduplication and distribution-matching. These are collection-level descriptions,
not per-record generator labels. Its only external links are Vertex AI model
documentation and a Universal Sentence Encoder tutorial; it does not link a
larger labeled artifact. Three AI cases cannot support meaningful detector
training or reliable recall estimation. The human essays can support a limited
external false-positive diagnostic with prompt/demographic limitations.

Canonical records: `data/authorship/aide/records.jsonl`.
SHA-256: `c60e1ed864d850b80c115f827cd46693059852fb7a24d22b01ddcdebf96e5471`.

## HC3 wiki_csai: usable for a separate engineering experiment

The [official HC3 card](https://huggingface.co/datasets/Hello-SimpleAI/HC3)
specifies CC BY-SA 4.0 subject to stricter source licenses. The
[official copyright table](https://github.com/Hello-SimpleAI/chatgpt-comparison-detection/blob/1f8c15c28f87e09a5abfd86ee6e15005dc7d2119/README.md)
explicitly identifies `wiki_csai` as Wikipedia under CC BY-SA. Other domains with
unknown/custom source rights were excluded.

Downloaded only `wiki_csai.jsonl`: 2,198,039 bytes, 842 question records, each with
one human answer and one ChatGPT answer. Dataset revision:
`4d0ff18143b5a7e1b1e79beb540c04549d1e59d3`.
Copyright-table revision: `1f8c15c28f87e09a5abfd86ee6e15005dc7d2119`.

After exact normalized deduplication, **1,613 answers remain: 771 human and 842 AI**.
There are 62 exact-duplicate groups accounting for 71 removed human answers, no
conflicting-label groups, and no approximate near-duplicate pairs above the
configured Jaccard threshold. This approximate search is not proof of full
independence. There are 839 question groups before relation union.

**Before splitting, union all `related_source_groups` in the manifest.** These are
derived from the pre-deduplication record map and preserve relationships between
different questions sharing the same human answer. Their surviving AI siblings
must remain in the same partition. A regression test checks this failure mode.

Canonical records: `data/authorship/hc3-wiki/records.jsonl`.
SHA-256: `94af560d2d28d98f6ef7959448e1082c3bb0fc765a269ab5de3675932f3912fa`.
The manifest retains license/attribution obligations, pinned URLs and raw hashes.

This is Wikipedia computer-science/AI question answering, not student writing.
Exact ChatGPT model/version and human author identities are unavailable.
Pretrained-detector training overlap is unverified. Use only as an explicitly
out-of-domain engineering baseline; do not infer student or modern-model accuracy.
Keep source questions, IDs, dataset metadata and labels out of text-only features.

## Nigerian Academic Writing Corpus: excluded pending evidence/access

[Mendeley DOI 10.17632/mfyx7pxwws.1](https://data.mendeley.com/datasets/mfyx7pxwws/1)
was published 14 April 2026 and states CC BY 4.0. DataCite metadata agrees. Its
description claims 4,239 historical Nigerian academic documents and 6,000 essays
from six newer models; those are publisher claims, not verified downloaded counts.

The human documents were harvested from Covenant University and University of
Ibadan repositories. Covenant University's
[official repository/OER policy](https://www.covenantuniversity.edu.ng/media/attachments/2022/06/20/policy-for-development-and-use-of-open-educational-resources.pdf)
limits general full-item reuse to research/study/educational/not-for-profit contexts
and requires copyright-holder permission for commercial reuse. Therefore free
repository access and a dataset-level CC BY statement do not establish per-item
open redistribution rights. A verified separately licensed synthetic subset could
be reconsidered independently.

Anonymous Python requests to the documented `api.data.mendeley.com` dataset/files
endpoints returned 401; older public endpoints returned 403 or timed out. No
account was created, terms accepted or authorization bypass attempted. Files,
per-record licenses, dates and lineage could not be verified, so none entered the
admitted corpora. Pre-November-2022 dating alone would also not prove absence of
all machine-assisted writing.

## Other candidates

The official [MAGE repository](https://github.com/yafuly/MAGE) says its distributed
detector was trained on the entire MAGE dataset, making that dataset unsuitable
as an assumed independent checkpoint test. [RAID](https://github.com/liamdugan/raid)
offers a labeled nonadversarial train CSV of roughly 802 MB, beyond this phase's
initial budget; repository MIT licensing is not a substitute for checking rights
to the underlying human-source content. Neither was admitted during this phase.
