"""Fetch a bounded PLOS seed corpus from the official Europe PMC REST API."""
import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

API = 'https://www.ebi.ac.uk/europepmc/webservices/rest'
QUERY = 'ISSN:1932-6203 AND OPEN_ACCESS:Y AND FIRST_PDATE:[2018-01-01 TO 2021-12-31]'


def now():
    return datetime.now(timezone.utc).isoformat()


def content(node):
    if node is None:
        return ''
    blocks = {'abstract', 'sec', 'title', 'p', 'list', 'list-item', 'disp-quote', 'license-p'}
    def pieces(element):
        if element.text:
            yield element.text
        for child in element:
            block = child.tag.rsplit('}', 1)[-1] in blocks
            if block:
                yield ' '
            yield from pieces(child)
            if block:
                yield ' '
            if child.tail:
                yield child.tail
    return ' '.join(''.join(pieces(node)).split())


def body_paragraphs(node):
    if node is None or node.tag in {'fig', 'table-wrap', 'supplementary-material', 'ref-list'}:
        return
    if node.tag == 'p':
        if content(node):
            yield content(node)
        return
    for child in node:
        yield from body_paragraphs(child)


def license_from_xml(root):
    """Accept explicit canonical CC BY URLs only, never publisher assumptions."""
    licenses = root.findall('./front/article-meta/permissions/license')
    found = []
    for node in licenses:
        urls = list(node.attrib.values())
        for child in node.iter():
            urls.extend(child.attrib.values())
        for url in urls:
            parsed = urllib.parse.urlsplit(url)
            match = re.fullmatch(r'/licenses/by/(2\.0|2\.5|3\.0|4\.0)/?', parsed.path)
            if (parsed.scheme in ('http', 'https') and
                    parsed.hostname in ('creativecommons.org', 'www.creativecommons.org') and
                    not parsed.username and not parsed.query and not parsed.fragment and match):
                found.append((f'CC-BY-{match[1]}', url, content(node)))
    if len({entry[0] for entry in found}) != 1:
        raise ValueError('unknown_or_ambiguous_license')
    # A separate restrictive license in the permissions block needs manual review.
    for node in licenses:
        if re.search(r'non.?commercial|no.?derivatives|by-nc|by-nd|by-sa', ET.tostring(node, encoding='unicode'), re.I):
            raise ValueError('conflicting_license')
    return found[0]


def parse_article(raw, *, full_text=False):
    root = ET.fromstring(raw)
    license_id, license_url, evidence = license_from_xml(root)
    meta = root.find('./front/article-meta')
    title = content(meta.find('./title-group/article-title'))
    abstract = '\n\n'.join(content(n) for n in meta.findall('./abstract') if content(n))
    if full_text:
        paragraphs = list(body_paragraphs(root.find('./body')))
        text = '\n\n'.join(([abstract] if abstract else []) + paragraphs)
        scope = 'abstract_and_body' if abstract else 'body'
    else:
        text, scope = abstract, 'abstract_only'
    if not title or not text:
        raise ValueError('missing_title_or_requested_text')
    authors = [' '.join(filter(None, (content(n.find('given-names')), content(n.find('surname')))))
               for n in meta.findall('./contrib-group/contrib/name')]
    doi = next((content(n) for n in meta.findall('./article-id') if n.get('pub-id-type') == 'doi'), '')
    return dict(title=title, text=text, license_id=license_id, license_url=license_url,
                metadata=dict(authors=authors, doi=doi, license_evidence=evidence,
                              attribution=f"{'; '.join(authors) or 'Authors recorded at source'}. {title}. {license_id}.",
                              indexed_scope=scope, role='retrieval_reference',
                              authorship_label=None))


def request(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'TuringTintCorpusSetup/0.1 (licensed-reference-seed)'})
            with urllib.request.urlopen(req, timeout=25) as response:
                data = response.read(12_000_001)
                if len(data) > 12_000_000:
                    raise ValueError('response_too_large')
                return data
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(1 + attempt)


def fetch(args):
    from turingtint.corpus import ingest_document
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = dict(started_at=now(), query=QUERY, provider='Europe PMC',
                    purpose='retrieval_reference_only', requested=args.limit, entries=[])
    manifest_path = output / 'manifest.json'
    def save():
        manifest['updated_at'] = now()
        manifest['accepted'] = sum(e['status'] == 'accepted' for e in manifest['entries'])
        temporary = output / 'manifest.json.tmp'
        temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        temporary.replace(manifest_path)
    save()
    params = urllib.parse.urlencode(dict(query=QUERY, format='json', resultType='core', pageSize=min(args.limit * 3, 100)))
    try:
        results = json.loads(request(API + '/search?' + params))['resultList']['result']
    except Exception as exc:
        manifest['error'] = str(exc)
        save()
        raise
    for result in results:
        if manifest.get('accepted', 0) >= args.limit:
            break
        pmcid = result.get('pmcid', '')
        if not re.fullmatch(r'PMC\d+', pmcid):
            continue
        entry = dict(document_id=pmcid, retrieved_at=now(), status='rejected')
        try:
            raw = request(API + '/' + pmcid + '/fullTextXML')
            article = parse_article(raw, full_text=args.full_text)
            article['metadata'].update(retrieved_at=entry['retrieved_at'],
                                       source_xml_sha256=hashlib.sha256(raw).hexdigest(),
                                       api_url=API + '/' + pmcid + '/fullTextXML')
            article['url'] = 'https://europepmc.org/articles/' + pmcid
            article['metadata']['attribution'] += ' ' + article['url']
            ingestion = ingest_document(args.db, document_id=pmcid,
                                        source_provider='Europe PMC / PLOS ONE', **article)
            (output / (pmcid + '.json')).write_text(json.dumps(article, indent=2, ensure_ascii=False), encoding='utf-8')
            entry.update(status='accepted', title=article['title'], license_id=article['license_id'],
                         license_url=article['license_url'], indexed_scope=article['metadata']['indexed_scope'],
                         source_xml_sha256=article['metadata']['source_xml_sha256'],
                         content_sha256=hashlib.sha256(article['text'].encode()).hexdigest(),
                         ingestion=ingestion)
        except (ValueError, ET.ParseError, urllib.error.URLError, TimeoutError) as exc:
            entry['reason'] = str(exc)
        manifest['entries'].append(entry)
        save()
        print(pmcid, entry['status'], entry.get('reason', ''), flush=True)
        time.sleep(0.35)
    manifest['completed_at'] = now()
    save()
    print(json.dumps(dict(accepted=manifest['accepted'], requested=args.limit, manifest=str(manifest_path))))
    return 0 if manifest['accepted'] == args.limit else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('fetch')
    command.add_argument('--limit', type=int, default=12)
    command.add_argument('--db', default='data/reference.sqlite')
    command.add_argument('--output', default='data/corpus-seed/')
    command.add_argument('--full-text', action='store_true', help='Index body paragraphs as well as abstract')
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('--limit must be between 1 and 100')
    return fetch(args)


if __name__ == '__main__':
    raise SystemExit(main())
