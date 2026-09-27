"""Acquire only the explicitly licensed HC3 Wikipedia CS/AI subset."""
import argparse
from collections import Counter
import json
from pathlib import Path
import urllib.request
from .__main__ import sha, stamp, normalized, deduplicate, near_duplicate_candidates

REPO = 'Hello-SimpleAI/HC3'
COPYRIGHT = 'https://raw.githubusercontent.com/Hello-SimpleAI/chatgpt-comparison-detection/main/README.md'


def parse_hc3(raw):
    records=[]
    for row_number,line in enumerate(raw.decode('utf-8').splitlines(),1):
        row=json.loads(line)
        if set(row) != {'question','human_answers','chatgpt_answers'} or not isinstance(row['question'],str):
            raise ValueError('Unexpected HC3 wiki schema')
        group='HC3:wiki_csai:question:'+sha(normalized(row['question']).encode())
        for field,label,generator in [('human_answers','human',None),('chatgpt_answers','ai','ChatGPT (exact model/version not supplied)')]:
            if not isinstance(row[field],list): raise ValueError('Answers must be lists')
            for index,text in enumerate(row[field]):
                if not isinstance(text,str) or not text.strip(): raise ValueError('Empty or malformed answer')
                records.append(dict(id=f'{group}:{label}:{row_number}:{index}',text=text,label=label,
                                    prompt_id=group,source_group=group,author_id=None,generator=generator,
                                    source_dataset='HC3-wiki_csai',content_sha256=sha(text.encode()),
                                    normalized_text_sha256=sha(normalized(text).encode()),
                                    source_record=dict(row_number=row_number,question=row['question'],
                                                       answer_field=field,answer_index=index,source_row=row)))
    return records


def related_groups(source_records, duplicates, near):
    lookup={row['id']:row['source_group'] for row in source_records}
    relations=[]
    for group in duplicates:
        ids=[group['kept'],*group['removed']]
        relations.append(dict(reason='exact_normalized_text',record_ids=ids,
                              source_groups=sorted({lookup[key] for key in ids})))
    for pair in near:
        ids=[pair['left'],pair['right']]
        relations.append(dict(reason='near_duplicate_text',record_ids=ids,
                              source_groups=sorted({lookup[key] for key in ids})))
    return relations


def acquire(output):
    output.mkdir(parents=True,exist_ok=True)
    receipts=[]
    total=0
    def get(url,name,limit=10_000_000):
        nonlocal total
        with urllib.request.urlopen(url,timeout=40) as response:
            raw=response.read(limit+1)
        total+=len(raw)
        if len(raw)>limit or total>30_000_000: raise ValueError('HC3 acquisition budget exceeded')
        (output/name).write_bytes(raw)
        receipts.append(dict(url=url,artifact=name,sha256=sha(raw),bytes=len(raw),retrieved_at=stamp()))
        return raw
    metadata=json.loads(get('https://huggingface.co/api/datasets/'+REPO,'release-metadata.json'))
    revision=metadata['sha']
    if metadata.get('cardData',{}).get('license')!='cc-by-sa-4.0' or metadata.get('private'):
        raise ValueError('HC3 public license metadata changed')
    base=f'https://huggingface.co/datasets/{REPO}/resolve/{revision}/'
    card=get(base+'README.md','dataset-card.md').decode()
    commit=json.loads(get('https://api.github.com/repos/Hello-SimpleAI/chatgpt-comparison-detection/commits/main','copyright-revision.json'))['sha']
    copyright_url=f'https://raw.githubusercontent.com/Hello-SimpleAI/chatgpt-comparison-detection/{commit}/README.md'
    rights=get(copyright_url,'publisher-copyright.md').decode()
    if 'license: cc-by-sa-4.0' not in card or '| wiki_csai   | Wikipedia | CC-BY-SA |' not in rights:
        raise ValueError('Missing subset-specific source license evidence')
    raw=get(base+'wiki_csai.jsonl','source-wiki_csai.jsonl')
    source_records=parse_hc3(raw)
    records,duplicates,conflicts=deduplicate(source_records)
    near,candidates=near_duplicate_candidates(records)
    relations=related_groups(source_records,duplicates,near)
    (output/'records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    manifest=dict(created_at=stamp(),status='admitted_for_out_of_domain_experiments',
                  source_dataset='HC3-wiki_csai',revision=revision,official_url='https://huggingface.co/datasets/'+REPO,
                  copyright_revision=commit,copyright_url=copyright_url,
                  license_id='CC-BY-SA-4.0',license_url='https://creativecommons.org/licenses/by-sa/4.0/',
                  license_evidence='Official HC3 card states CC-BY-SA4; official project copyright table identifies wiki_csai as Wikipedia CC-BY-SA. Other domains excluded.',
                  attribution='Guo et al. (2023), How Close is ChatGPT to Human Experts? HC3 wiki_csai; human answers sourced from Wikipedia.',
                  downloads=receipts,raw_rows=len(source_records),question_rows=len(raw.splitlines()),admitted_rows=len(records),
                  labels=dict(Counter(r['label'] for r in records)),prompt_groups=len({r['prompt_id'] for r in records}),
                  known_author_rows=0,generator_counts=dict(Counter(r['generator'] or 'human/unknown' for r in records)),
                  duplicate_groups=duplicates,conflicting_label_groups=conflicts,near_duplicate_pairs=near,
                  related_source_groups=relations,
                  near_duplicate_candidates_checked=candidates,no_split_created=True,
                  records_sha256=sha((output/'records.jsonl').read_bytes()),
                  source_group_semantics='Question identity shared across human and ChatGPT answers; not author identity.',
                  limitations=['Wikipedia CS/AI question answers, not student essays or academic paragraphs.',
                               'Old ChatGPT snapshot, exact model unspecified. Not contemporary-generator validation.',
                               'Pretrained-detector training overlap unverified; results cannot be claimed independent until audited.',
                               'Near-duplicate discovery uses approximate candidate signatures, not exhaustive independence proof.',
                               'No student or author identities supplied. Preserve attribution/share-alike obligations.',
                               'Source question and raw metadata must not enter text-only model features.'])
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ['question_rows','raw_rows','admitted_rows','labels','prompt_groups']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('data/authorship/hc3-wiki'))
    acquire(parser.parse_args().output)
