import unittest
import json
from authorship_data.__main__ import parse_records, deduplicate, normalized, validate_license, near_duplicate_candidates, REF
from authorship_data.hc3 import parse_hc3, related_groups


class AuthorshipDataTests(unittest.TestCase):
    def records(self):
        return parse_records(b'id,prompt_id,text,generated\na,0,A real essay with several original words for a test,0\nb,1,A generated essay with several distinctive sentences and words,1\n')

    def test_source_labels_and_unknown_identity_preserved(self):
        rows=self.records()
        self.assertEqual([r['label'] for r in rows], ['human','ai'])
        self.assertIsNone(rows[0]['author_id'])
        self.assertIsNone(rows[1]['generator'])
        self.assertEqual(rows[0]['prompt_id'],'AIDE:0')

    def test_unknown_label_rejected(self):
        with self.assertRaises(ValueError):
            parse_records(b'id,prompt_id,text,generated\na,0,some text,2\n')

    def test_conflicting_exact_text_quarantined(self):
        a,b=self.records(); b['normalized_text_sha256']=a['normalized_text_sha256']
        rows,dupes,conflicts=deduplicate([a,b])
        self.assertEqual(rows,[])
        self.assertEqual(len(conflicts),1)

    def test_same_label_duplicate_preserves_source_row(self):
        a,b=self.records(); b['label']=a['label']; b['normalized_text_sha256']=a['normalized_text_sha256']
        rows,dupes,conflicts=deduplicate([a,b])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['duplicate_source_records'],[b['source_record']])

    def test_license_requires_publisher_and_release(self):
        m=dict(ref=REF,isPrivate=False,licenseName='Attribution 4.0 International (CC BY 4.0)',description='AIDE licensed under CC BY 4.0')
        validate_license(m,REF+' AIDE dataset is licensed under CC BY 4.0')
        with self.assertRaises(ValueError): validate_license(m,'No publisher evidence')

    def test_near_duplicate_relations_are_flagged_not_removed(self):
        rows=self.records()
        rows[0]['text']=' '.join('word'+str(i) for i in range(100))
        rows[1]['text']=rows[0]['text']+' extra'
        pairs,count=near_duplicate_candidates(rows)
        self.assertEqual(len(pairs),1)
        self.assertTrue(pairs[0]['label_conflict'])
        self.assertEqual(len(rows),2)

    def test_normalization_is_deterministic(self):
        self.assertEqual(normalized('  CAFÉ\ntext'),normalized('cafe\u0301 text'))

    def test_hc3_answers_share_source_question_group(self):
        rows=parse_hc3(json.dumps({'question':'What is learning?','human_answers':['Human answer.'],'chatgpt_answers':['AI answer.']}).encode())
        self.assertEqual(rows[0]['source_group'],rows[1]['source_group'])
        self.assertNotEqual(rows[0]['id'],rows[1]['id'])
        self.assertEqual(rows[0]['label'],'human')
        self.assertEqual(rows[1]['label'],'ai')
        self.assertIsNone(rows[0]['author_id'])

    def test_removed_duplicate_retains_cross_question_lineage(self):
        raw='\n'.join(json.dumps({'question':q,'human_answers':['Identical human answer.'],'chatgpt_answers':[q+' distinct AI answer.']}) for q in ['Question one','Question two']).encode()
        source=parse_hc3(raw)
        retained,duplicates,conflicts=deduplicate(source)
        relations=related_groups(source,duplicates,[])
        self.assertEqual(len(retained),3)
        self.assertEqual(len(relations),1)
        self.assertEqual(set(relations[0]['source_groups']),{source[0]['source_group'],source[2]['source_group']})
