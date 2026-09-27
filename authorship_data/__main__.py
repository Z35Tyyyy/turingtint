import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
import urllib.request
import zipfile

REF = 'lburleigh/tla-lab-ai-detection-for-essays-aide-dataset'
CATALOG = 'https://the-learning-agency.com/guides-resources/datasets/'
PAGE = 'https://www.kaggle.com/datasets/' + REF
API = 'https://www.kaggle.com/api/v1/datasets/'
MAX_BYTES = 250_000_000


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def validate_license(metadata, catalog):
    if metadata.get('ref') != REF or metadata.get('isPrivate') is not False:
        raise ValueError('Wrong dataset identity or dataset is not public')
    if metadata.get('licenseName') != 'Attribution 4.0 International (CC BY 4.0)':
        raise ValueError('Dataset release metadata does not state CC BY 4.0')
    if 'AIDE' not in metadata.get('description', '') or 'licensed under CC BY 4.0' not in metadata['description']:
        raise ValueError('Missing dataset-specific license statement')
    if REF not in catalog or not re.search(r'AIDE dataset is licensed under CC BY 4\.0', catalog):
        raise ValueError('Publisher catalog must identify this release and its license')


def parse_records(raw):
    rows = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if rows.fieldnames != ['id', 'prompt_id', 'text', 'generated']:
        raise ValueError('Unexpected AIDE essay schema; review before admitting')
    records = []
    seen_ids = set()
    for row in rows:
        if row['generated'] not in ('0', '1') or not row['text'].strip() or not row['id'] or not row['prompt_id']:
            raise ValueError('Invalid label, text, prompt or essay id')
        if row['id'] in seen_ids:
            raise ValueError('Duplicate source id; resolve source lineage before admitting')
        seen_ids.add(row['id'])
        records.append(dict(id='AIDE:' + row['id'], text=row['text'],
                            label='human' if row['generated'] == '0' else 'ai',
                            prompt_id='AIDE:' + row['prompt_id'],
                            source_group='AIDE:essay:' + row['id'],
                            author_id=None, generator=None, source_dataset='AIDE',
                            content_sha256=sha(row['text'].encode()),
                            normalized_text_sha256=sha(normalized(row['text']).encode()),
                            source_record=row))
    return records


def deduplicate(records):
    groups = defaultdict(list)
    for record in records:
        groups[record['normalized_text_sha256']].append(record)
    admitted, duplicates, conflicts = [], [], []
    for key, items in groups.items():
        if len({r['label'] for r in items}) > 1:
            conflicts.append(dict(normalized_text_sha256=key, ids=[r['id'] for r in items]))
            continue
        if len(items) > 1:
            duplicates.append(dict(kept=items[0]['id'], removed=[r['id'] for r in items[1:]]))
        item = dict(items[0])
        item['duplicate_source_records'] = [r['source_record'] for r in items[1:]]
        admitted.append(item)
    return admitted, duplicates, conflicts


def near_duplicate_candidates(records):
    """Candidate audit, not exhaustive proof of independence; never drops rows."""
    sets = []
    buckets = defaultdict(list)
    pairs = set()
    for i, record in enumerate(records):
        words = re.findall(r'\w+', normalized(record['text']))
        grams = {sha(' '.join(words[j:j+5]).encode())[:16] for j in range(max(0, len(words)-4))}
        sets.append(grams)
        for signature in sorted(grams)[:16]:
            for previous in buckets[signature]:
                pairs.add((previous, i))
                if len(pairs) > 200_000:
                    raise ValueError('Near-duplicate candidate budget exceeded; audit manually')
            buckets[signature].append(i)
    matches = []
    for left, right in sorted(pairs):
        a, b = sets[left], sets[right]
        if not a or not b or min(len(a), len(b)) / max(len(a), len(b)) < .8:
            continue
        similarity = len(a & b) / len(a | b)
        if similarity >= .8:
            matches.append(dict(left=records[left]['id'], right=records[right]['id'],
                                five_word_jaccard=similarity,
                                label_conflict=records[left]['label'] != records[right]['label']))
    return matches, len(pairs)


def acquire(output):
    output.mkdir(parents=True, exist_ok=True)
    consumed = 0
    receipts = []
    def download(url, name, limit):
        nonlocal consumed
        req = urllib.request.Request(url, headers={'User-Agent': 'TuringTintResearchAcquisition/0.1'})
        chunks, size = [], 0
        with urllib.request.urlopen(req, timeout=40) as response:
            while chunk := response.read(65536):
                size += len(chunk)
                consumed += len(chunk)
                if size > limit or consumed > MAX_BYTES:
                    raise ValueError('Download budget exceeded')
                chunks.append(chunk)
        raw = b''.join(chunks)
        (output / name).write_bytes(raw)
        receipts.append(dict(url=url, artifact=name, bytes=size, sha256=sha(raw), retrieved_at=stamp()))
        return raw
    catalog = download(CATALOG, 'publisher-catalog.html', 5_000_000).decode('utf-8')
    metadata = json.loads(download(API+'view/'+REF, 'release-metadata.json', 5_000_000))
    validate_license(metadata, catalog)
    version = metadata['currentVersionNumber']
    if not isinstance(version, int) or version < 1:
        raise ValueError('Invalid release version')
    archive = download(API+'download/'+REF+'?datasetVersionNumber='+str(version), 'release.zip', 100_000_000)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        if sum(i.file_size for i in zipped.infolist()) > MAX_BYTES or len(zipped.infolist()) > 100:
            raise ValueError('Unpacked archive exceeds budget')
        artifacts = [dict(name=i.filename, bytes=i.file_size, sha256=sha(zipped.read(i))) for i in zipped.infolist()]
        raw_records = parse_records(zipped.read('AIDE_train_essays.csv'))
        prompts = list(csv.DictReader(io.StringIO(zipped.read('train_prompts.csv').decode('utf-8-sig'))))
    prompt_map = {p['prompt_id']:p for p in prompts}
    if any(r['source_record']['prompt_id'] not in prompt_map for r in raw_records):
        raise ValueError('Essay references missing prompt')
    records, duplicates, conflicts = deduplicate(raw_records)
    near, candidates = near_duplicate_candidates(records)
    (output/'records.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records), encoding='utf-8')
    (output/'prompts.json').write_text(json.dumps(prompts, ensure_ascii=False, indent=2), encoding='utf-8')
    counts = {key:dict(Counter(r['label'] for r in records if r['prompt_id']==key)) for key in sorted({r['prompt_id'] for r in records})}
    manifest = dict(created_at=stamp(), status='admitted', source_dataset='AIDE', version=version,
                    kaggle_dataset_id=metadata['id'], release_updated_at=metadata['lastUpdated'],
                    official_catalog_url=CATALOG, official_release_url=PAGE,
                    license_id='CC-BY-4.0', license_url='https://creativecommons.org/licenses/by/4.0/',
                    license_evidence='Publisher AIDE-specific CC BY 4.0 statement and exact Kaggle release metadata agree; snapshots retained.',
                    attribution='AIDE (2024), The Learning Agency Lab; distributed by L Burleigh, Kaggle.',
                    downloads=receipts, archive_members=artifacts, raw_rows=len(raw_records),
                    admitted_rows=len(records), labels=dict(Counter(r['label'] for r in records)),
                    prompt_label_counts=counts, prompt_names={f'AIDE:{p["prompt_id"]}':p['prompt_name'] for p in prompts},
                    known_generator_rows=0, known_author_rows=0,
                    source_group_semantics='Published unique essay id; not a student/author identifier.',
                    duplicate_groups=duplicates, conflicting_label_groups=conflicts,
                    near_duplicate_pairs=near, near_duplicate_candidates_checked=candidates,
                    near_duplicate_method='16 minimum SHA256 5-word shingle candidate signatures, exact Jaccard >=0.8; approximate discovery, not exhaustive.',
                    no_split_created=True, records_sha256=sha((output/'records.jsonl').read_bytes()),
                    limitations=['Catalog advertises about 10000 essays/seven prompts; actual release counts above govern use.',
                                 'No author/student ids or per-essay generator identities supplied.',
                                 'Unknown generator and author independence cannot be established.',
                                 'Source documents/prompts are not model features; source_record is local audit metadata only.'])
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ['raw_rows','admitted_rows','labels','prompt_label_counts','known_generator_rows','duplicate_groups','conflicting_label_groups','near_duplicate_pairs']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Acquire public publisher-linked AIDE without account credentials.')
    parser.add_argument('--output', type=Path, default=Path('data/authorship/aide'))
    acquire(parser.parse_args().output)
