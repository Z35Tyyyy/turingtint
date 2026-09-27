# Local reference acquisition

Run from the repository root:

```powershell
python -m corpus_tools fetch --limit 12 --db data/reference.sqlite --output data/corpus-seed/
```

This explicit setup command contacts the official Europe PMC REST API to retrieve
PLOS ONE articles published in 2018–2021. It never reads or transmits a user's
analysis input. Analysis can subsequently use the SQLite reference library offline.
The seed is a retrieval smoke test, not representative plagiarism coverage.

By default only the actual article abstract is indexed. Add `--full-text` to index
the abstract and body paragraphs. The XML article permissions must contain an
explicit Creative Commons Attribution URL (CC BY 2.0, 2.5, 3.0 or 4.0).
Unknown, ambiguous, restrictive or missing licenses are rejected; publisher name
and API open-access flags alone do not establish the license. Missing abstracts
are rejected in default mode. References, figures and supplementary files are not
included in the text index.

`manifest.json` records accepted/rejected candidates, timestamps, hashes, license
and indexed scope. Each accepted document has an attribution/provenance JSON file.
These are retrieval references, with no inferred human-authorship ground truth.
The source XML hash identifies the retrieved version; full XML is not retained.

Fetching is bounded to at most 100 candidates in one search response, three
attempts per request, 25-second request timeouts and 12 MB per response. A partial
seed returns a nonzero exit code with the actual counts. Re-running uses stable
PMC document IDs; database insertion behavior is provided by the corpus backend.
The output directory describes the latest run; use a new directory if retaining
multiple acquisition manifests.

Official API documentation: https://europepmc.org/RestfulWebService
Official permitted open-access retrieval information:
https://europepmc.org/downloads/openaccess
