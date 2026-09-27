# Authorship data acquisition

These commands download public, publisher-linked research artifacts without
accounts, credentials or commercial APIs. They never send user text.

```powershell
python -m authorship_data --output data/authorship/aide
python -m authorship_data.hc3 --output data/authorship/hc3-wiki
python -m unittest discover -s tests -p test_authorship_data.py -v
```

Read `research/corpus-acquisition-phase2.md` before using the records. Neither
corpus establishes product accuracy. No train/calibration/test split is created.

Canonical model-facing fields are `id`, `text`, `label` (`human` or `ai`),
`prompt_id`, `source_group`, `generator`, `author_id`, and `source_dataset`.
Unknown identities remain null. Hashes, `source_record` and
`duplicate_source_records` are local audit metadata, not model inputs.

Exact normalized duplicates are deduplicated, preserving original rows. Label
conflicts are quarantined (source remains in raw artifact). Approximate
five-word-shingle near-duplicate candidates are flagged without automatic removal.
For HC3, the manifest's `related_source_groups` must be unioned BEFORE splitting:
different questions can share a deduplicated human answer while retaining distinct
AI answers. Grouping only by surviving question IDs would leak related material.

Every acquisition retains original release metadata, license evidence, artifact
hashes and timestamps. HC3 artifacts and its upstream copyright table are pinned
to immutable revisions. AIDE pins the explicitly reported Kaggle version.
The AIDE download budget is 250 MB total (100 MB archive); HC3 is capped at 30 MB.
Networking is setup-only; local processing uses Python's standard library.
