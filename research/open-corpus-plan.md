# Openly licensed corpus plan

Research checked: 2026-09-27. Scope: English academic/student writing; local inference and source matching. The user's “os” is interpreted as open-source/openly licensed. This is a source-selection and acquisition plan, not a downloaded or validated corpus.

Latest constraint: the user monitors only. Under the [autonomous feasibility assessment](autonomous-feasibility.md), new human contributions described below are a future improvement rather than a prototype dependency. Use eligible existing provenance-supported datasets and clearly labeled synthetic operations; do not represent AI-generated edits or reviews as human evidence.

## Decision

Maintain three separate collections: labeled authorship data, a searchable reference library, and an independent evaluation set. A paper useful for source matching is not automatically verified human-authored detector data. Public availability, a code license and a data license are different things.

Recommended first sources: AIDE and ASAP 2.0 for essay data; an exact-release-verified PERSUADE subset if its license matches; CC BY/CC0 academic articles for references; locally generated examples with recorded provenance; and newly collected, consented human/mixed writing for final evaluation. Public mixed-authorship benchmarks are supplementary until their upstream permissions and label definitions are checked.

## 1. Authorship data inventory

| Source | Verified publisher/card statement | Intended role and admission condition |
|---|---|---|
| AIDE | Publisher describes 10,000 student/LLM essays across seven prompts and states CC BY 4.0. | Primary domain-specific seed. Pin the linked release, inspect labels/counts and hold out prompts. |
| ASAP 2.0 | Publisher describes approximately 24,000 student essays and CC BY with a link to 4.0. | Human-writing seed. Check source provenance, authorship limitations and overlap with other essay datasets. |
| PERSUADE, publisher-linked release | Publisher describes 14,000+ essays and CC BY 4.0. | Conditional seed: verify the exact file and release; do not merge indiscriminately with PERSUADE 2.0. |

Publisher evidence and download links: [The Learning Agency dataset catalog](https://the-learning-agency.com/guides-resources/datasets/). Exact artifact licenses and hashes remain an ingestion check; counts above are reported release descriptions, not locally verified counts. A dataset containing proprietary-model outputs can still be openly licensed and consumed offline; that does not require using the proprietary API.

| Supplementary source | Declared license/status | Decision |
|---|---|---|
| [RAID](https://huggingface.co/datasets/liamdugan/raid) | Dataset card declares MIT. Broad generators, domains and perturbations. | Conditional challenge data; identify upstream human-text permissions and pin a release. Avoid downloading the full multi-million-example collection initially. |
| [MAGE](https://huggingface.co/datasets/yaful/MAGE) | Dataset card declares Apache-2.0. Includes varied genres. | Conditional generalization data; source-level rights and scientific subset selection required. |
| [OpAI-Bench](https://huggingface.co/datasets/OpAI-Bench1/OpAI-Bench) | Dataset card declares Apache-2.0; progressive edit trajectories. | Conditional mixed-writing benchmark. Preserve all revisions in one split; verify upstream text rights. Edited-region labels do not prove every token's origin. |
| [MixSet](https://huggingface.co/datasets/ONE-Lab/MixSet) | No explicit dataset license established in the reviewed official card/repository. | Hold out of the admitted corpus until clarified. |
| [ArguGPT](https://github.com/huhailinguist/ArguGPT) | Human TOEFL material is purchased via LDC; some GRE human material is not redistributable. No blanket open grant established. | Do not treat the paired dataset as a fully open corpus. |
| [PELIC](https://github.com/ELI-Data-Mining-Group/PELIC-dataset) | CC BY-NC-ND 4.0. | Not part of the permissive default corpus. |
| [SEFORA](https://github.com/ShayanPey/SEFORA) | Data CC BY-NC; code MIT in reviewed README. | Keep separate from the permissive corpus; code permissions do not resolve data restrictions. |

PERSUADE requires particular care: [the publisher's page](https://the-learning-agency-lab.com/learning-exchange/persuade-dataset/) specifies CC BY 4.0 for its linked release, while [the PERSUADE 2.0 repository](https://github.com/scrosseye/persuade_corpus_2.0) explicitly specifies CC BY-NC-SA 4.0 for its larger release. Do not choose the more permissive statement without matching the actual artifact. If its provenance remains ambiguous, begin with AIDE/ASAP and defer that PERSUADE file. Do not sum these collections' sizes as if every essay were unique.

The permissive default is an engineering choice to keep future reuse straightforward, not a claim that every other license prohibits all research. Retain restricted/unclear entries in the inventory rather than silently importing them.

## 2. Local academic reference library

| Source | Selection rule | Coverage |
|---|---|---|
| [PMC Open Access subset](https://pmc.ncbi.nlm.nih.gov/tools/openftlist/), including PLOS | Admit article versions with explicit CC BY/CC0 and retain their license evidence. Exclude separately restricted third-party content. | Life sciences, medicine, public health and related academic prose. |
| [PLOS](https://plos.org/terms-of-use/) | Use article-level evidence despite the publisher's broadly permissive policy. Prefer PMC-hosted XML for initial extraction. | Straightforward academic starting slice; overlaps PMC rather than adding a separate unique corpus. |
| [arXiv](https://info.arxiv.org/help/license/reuse.html) | Explicit CC BY/CC0 versions only for the initial policy. The arXiv distribution license is not a blanket reuse grant to us. | CS, mathematics, physics, statistics and adjacent subjects. |
| [DOAJ](https://doaj.org/docs/faq/) | Use metadata for discovery, then inspect actual article rights and retrieve authorized full text. Metadata permission does not license the article. | Add education, social science and humanities to reduce biomedical bias. |
| User-supplied references | Local, access-controlled collection; no automatic redistribution. | Course-specific sources and authorized private material; separate from the openly redistributable corpus. |

Use current [PMC cloud documentation](https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/): retrieve permitted versions through documented services, inventory and per-version licensing metadata rather than assuming the old commercial/noncommercial directory layout. Anonymous HTTPS access is documented. Downloads occur during corpus setup; pasted text need not leave the machine during analysis. For arXiv, use its documented metadata/bulk routes with per-version rights checks and service limits.

Initial size targets, not acquired counts:

- Smoke index: 300 documents, roughly 100 from each of PMC/PLOS, eligible arXiv and other fields.
- Prototype index: 5,000 unique documents, approximately 2,000 PMC/PLOS, 1,500 arXiv and 1,500 other-field articles.
- Expand toward 25,000–50,000 only after measuring retrieval recall, storage, indexing time and RAM on the actual machine.

These are feasibility targets, not whole-literature coverage. If eligible articles in a planned category are scarce, report the shortfall rather than filling it with license-unknown text. Deduplicate preprints/published versions and PMC/PLOS overlaps. Store DOI/arXiv/PMCID family links so a mirrored paper is not treated as several independent sources.

The interface should say “Compared against this local reference library” and report corpus version/size. “No source match found in the local corpus” does not certify originality. Unseen web pages, paywalled papers, unprovided student assignments and private repositories remain outside coverage.

## 3. New labeled data and missing coverage

The open essay collections are a useful seed, but do not establish sufficient coverage of Indian English, university research writing or contemporary human–AI editing. Final evaluation needs consented writing with creation/edit history, including those groups. Do not infer language background from names or text style. Keep sensitive audit metadata outside model features and the reference search index.

Generate controlled local examples only from admitted sources, using several licensed model families with checkpoint hashes, prompts and sampling settings recorded. Include independent essays from matched prompts and source-grounded academic drafts; using only reverse paraphrases risks teaching a rewriting artifact rather than authorship. Avoid using only Qwen because it is already installed. Select model families and hardware-compatible variants during feasibility work, retaining at least one family for unseen-generator testing. Locally generated cases alone cannot justify a claim about every hosted frontier model.

Mixed-data operations: insert AI sentences into a human draft; append an AI continuation; apply grammar-only AI edits; perform substantive AI revision; and collect actual human edits of an AI draft. Preserve original/revised text, operation type, revision sequence and character alignment. An LLM simulating a human editor is synthetic AI editing, not genuine human post-editing. True collaboration requires real human contributions.

For authorship labels use separate fields for stated author/workflow, evidence level and uncertainty. Contemporary published papers are usable source references even when authorship is unknown; they must not automatically become “human-only” labels. Existing repository AI-edited targets remain AI-edited development material.

## 4. Sampling and splits

First build the product plan's 600-case development set: 200 human, 200 AI, 200 mixed. Aim for half student/argumentative prose and half research/academic prose within each class, with separate buckets for short and long paragraphs. If real mixed cases are missing, mark the gap; do not replace their label with synthetic human provenance.

After that audit, use an initial training pool target of 12,000 examples: 4,000 human, 4,000 AI and 4,000 mixed/workflow examples, subject to admission and genuine mixed-data availability. These are engineering sampling targets, not a sufficiency claim. Reserve calibration and final evaluation before expanding or generating descendants. Keep the independent 1,000-case calibration and 5,000-case launch-evaluation targets from the main plan separate; human independence is counted by source/author group, not paragraph count.

Split the source families before paragraph extraction or generation. Keep all originals, revisions, near duplicates, source-based generated descendants and shared prompt families grouped as appropriate. Audit overlap across AIDE/ASAP/PERSUADE and public detector benchmarks. Reserve a prompt-group challenge, a generator-family challenge and fresh chronological data. Run checks for accidental label cues such as generator disclaimers, CSV artifacts and dataset-specific formatting.

For plagiarism evaluation, start with 500 cases as in the product plan and expand to 1,000: exact reuse, small edits, semantic paraphrases, patchwork, quoted/cited text, independent same-topic writing and deliberate source-absent cases. Sources must be in the index for source-present tests; this is expected, not leakage. Query variants and their labels must stay out of model training and threshold tuning. Report source-present recall separately from overall end-to-end recall.

## 5. Admission manifest and acquisition order

Every admitted record needs:

```text
record_id, collection_role, dataset_name, dataset_release_or_commit
source_id, canonical_url, source_version, retrieved_at
license_id, license_url, license_evidence, license_checked_at
upstream_source, attribution, content_sha256, parser_version
language, domain, genre, length, authorship_label, label_evidence
source_family_id, author_group_if_known, prompt_family, dedup_cluster
generator_checkpoint_if_any, generation_settings, transformation_lineage
split, source_text_offsets, normalized_to_original_offset_map
```

Collection roles: detector training, calibration, blind evaluation, reference index or development-only. Do not store public student essays as searchable attribution evidence merely because they were admitted for training. Separate training permission, reference-index use and redistribution scope in the manifest.

Admission states: discovered → publisher license checked → artifact/upstream checked → deduplicated → label audited → admitted. Unknown-license rows remain excluded. Snapshot license evidence and pin hashes; a moving dataset card is not reproducible evidence of the file used. Download data only through publisher-linked or authorized routes. Do not accept competition terms or create accounts automatically to bypass an access limitation; record access requirements and use an available eligible source meanwhile.

Acquisition order:

1. Fetch release metadata/license files for AIDE and ASAP; reconcile the exact PERSUADE release before including it.
2. Build a 300-document local reference smoke index with license evidence and original text offsets.
3. Assemble and audit the 600-case development manifest, including existing cases only as marked historical development material.
4. Add permitted local generations and recorded mixed workflows; measure class/domain balance and duplication.
5. Freeze groups for calibration/final evaluation; then scale the training pool and 5,000-document reference index.
6. Add rights-audited subsets of RAID/MAGE/OpAI as named challenges rather than merging them blindly into training.

No bulk data download, new generation, corpus ingestion or detector training was performed for this planning update. The remaining concrete work is artifact verification, acquisition, curation and measurement; source selection alone does not establish model accuracy.
