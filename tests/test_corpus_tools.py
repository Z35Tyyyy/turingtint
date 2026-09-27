import unittest
from corpus_tools.__main__ import parse_article


def article(license_url='https://creativecommons.org/licenses/by/4.0/', abstract='<abstract><p>Clear <italic>research</italic> summary.</p></abstract>', body=''):
    return f'''<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta>
    <title-group><article-title>Sample paper</article-title></title-group>
    <permissions><license xlink:href="{license_url}"><license-p>Credit authors.</license-p></license></permissions>
    {abstract}</article-meta></front><body>{body}</body></article>'''.encode()


class CorpusParserTests(unittest.TestCase):
    def test_attribution_and_scope(self):
        parsed = parse_article(article())
        self.assertEqual(parsed['text'], 'Clear research summary.')
        self.assertEqual(parsed['license_id'], 'CC-BY-4.0')
        self.assertEqual(parsed['metadata']['indexed_scope'], 'abstract_only')
        self.assertIsNone(parsed['metadata']['authorship_label'])

    def test_structured_abstract_preserves_block_and_inline_boundaries(self):
        structured = '<abstract><title>Abstract</title><sec><title>Background</title><p>The micro<italic>organism</italic> was studied.</p></sec><sec><title>Methods</title><p>We recorded outcomes.</p></sec></abstract>'
        parsed = parse_article(article(abstract=structured))
        self.assertEqual(parsed['text'], 'Abstract Background The microorganism was studied. Methods We recorded outcomes.')

    def test_reject_restricted_unknown_and_spoofed_license(self):
        for url in ['https://creativecommons.org/licenses/by-nc/4.0/', '',
                    'https://creativecommons.org.evil.test/licenses/by/4.0/']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_article(article(url))

    def test_absent_abstract_never_invents_text(self):
        with self.assertRaises(ValueError):
            parse_article(article(abstract='', body='<p>Actual body.</p>'))
        parsed = parse_article(article(abstract='', body='<p>Actual body.</p>'), full_text=True)
        self.assertEqual(parsed['text'], 'Actual body.')
        self.assertEqual(parsed['metadata']['indexed_scope'], 'body')

    def test_absent_all_text_rejected(self):
        with self.assertRaises(ValueError):
            parse_article(article(abstract=''), full_text=True)

    def test_conflicting_licenses_rejected(self):
        raw = article().replace(b'</permissions>', b'<license>Noncommercial use only.</license></permissions>')
        with self.assertRaises(ValueError):
            parse_article(raw)

    def test_full_text_omits_reference_and_figure_text(self):
        raw = article(body='<p>Supported body paragraph.</p><fig><caption><p>Figure caption.</p></caption></fig>')
        result = parse_article(raw, full_text=True)
        self.assertIn('Supported body paragraph.', result['text'])
        self.assertNotIn('Figure caption.', result['text'])


if __name__ == '__main__':
    unittest.main()
