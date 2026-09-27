"""Validate source provenance, not authorship accuracy."""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def run():
    from turingtint.corpus import corpus_summary
    db = ROOT / 'data/reference.sqlite'
    if not db.exists():
        return {'status': 'blocked', 'summary': 'No local reference corpus has been ingested.'}
    summary = corpus_summary(db)
    if not summary.get('document_count'):
        return {'status': 'blocked', 'summary': 'Reference corpus contains no searchable documents.'}
    from turingtint.corpus import open_readonly, ALLOWED_LICENSES
    from contextlib import closing
    with closing(open_readonly(db)) as connection:
        rows = connection.execute('SELECT * FROM documents').fetchall()
    for row in rows:
        metadata = json.loads(row['metadata_json'])
        if row['license_id'] not in ALLOWED_LICENSES or not metadata.get('license_evidence') or not metadata.get('attribution'):
            raise ValueError('A reference is missing supported license or attribution evidence: ' + row['document_id'])
        if hashlib.sha256(row['text'].encode('utf-8')).hexdigest() != row['content_sha256']:
            raise ValueError('Reference text does not match its recorded hash: ' + row['document_id'])
        if metadata.get('authorship_label') is not None:
            raise ValueError('The retrieval seed must not infer human authorship labels.')
    return {'status': 'passed', 'summary': f"{summary['document_count']} sources with license/attribution evidence and verified text hashes. This is an ingestion check, not retrieval accuracy validation.", 'evidence': [summary]}

if __name__ == '__main__':
    try:
        report = run()
    except Exception as exc:
        report = {'status': 'failed', 'summary': str(exc)}
    print(json.dumps(report))
    sys.exit(0 if report['status'] == 'passed' else 1)
