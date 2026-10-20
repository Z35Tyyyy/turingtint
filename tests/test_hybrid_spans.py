import unittest
from unittest.mock import Mock, patch

from turingtint.hybrid_spans import analyze_spans, sentence_ranges, signal_label


def result(a=.9, b=.85, complete=True):
    return dict(coverage_complete=complete, components=[
        dict(member='distilbert', model_id='one', score_ai=a),
        dict(member='modernbert', model_id='two', score_ai=b)])


class SentenceSignalsTests(unittest.TestCase):
    def test_ranges_preserve_unicode_and_whitespace(self):
        text = '  First sentence with an emoji \U0001f697 and enough words to score.\n\nAnother sentence contains enough words for the second detector comparison.  '
        model = Mock(); model.predict.return_value = [result()]
        output = analyze_spans(text, model, result())
        self.assertEqual(output['offset_encoding'], 'utf-16')
        self.assertEqual(len(output['segments']), 2)
        raw = text.encode('utf-16-le')
        spans = [raw[s['start'] * 2:s['end'] * 2].decode('utf-16-le') for s in output['segments']]
        self.assertEqual(spans, [text[a:b] for a, b in sentence_ranges(text)])
        self.assertEqual(model.predict.call_count, 2)
        self.assertTrue(all(s['low_context'] for s in output['segments']))

    def test_single_sentence_reuses_document_score(self):
        text = 'This sentence has enough words to score without another model call.'
        model = Mock()
        output = analyze_spans(text, model, result())
        model.predict.assert_not_called()
        self.assertEqual(output['segments'][0]['label'], 'stronger')

    def test_too_short_neutral_and_no_inference(self):
        model = Mock()
        output = analyze_spans('Very short.\nHi!', model, result())
        self.assertFalse(output['complete'])
        self.assertTrue(all(s['label'] == 'unscored' for s in output['segments']))
        model.predict.assert_not_called()

    def test_policy_disagreement_and_truncation(self):
        for a, b, label in [(.9, .8, 'stronger'), (.1, .2, 'weaker'), (.9, .4, 'disagree'), (.49, .51, 'disagree'), (.55, .6, 'uncertain')]:
            self.assertEqual(signal_label(result(a, b)), label)
        self.assertEqual(signal_label(result(complete=False)), 'unscored')
        with self.assertRaises(ValueError):
            signal_label(result(float('nan')))

    def test_bound_limit_preserves_unscored_remainder(self):
        model = Mock(); model.predict.return_value = [result()]
        text = 'This sentence contains enough words for a separate experimental model score. ' * 30
        output = analyze_spans(text, model, result())
        self.assertEqual(model.predict.call_count, 24)
        self.assertEqual(len(output['segments']), 25)
        self.assertEqual(output['segments'][-1]['end'], len(text))
        self.assertEqual(output['segments'][-1]['label'], 'unscored')

    def test_failure_and_time_limit_never_fabricate_signal(self):
        text = 'This first sentence has enough words for a model evaluation. This other sentence also contains enough words for a separate evaluation.'
        model = Mock(); model.predict.side_effect = RuntimeError('private failure')
        output = analyze_spans(text, model, result())
        self.assertTrue(all(s['label'] == 'unscored' for s in output['segments']))
        self.assertNotIn('private', str(output))
        model.reset_mock()
        with patch('turingtint.hybrid_spans.time.monotonic', side_effect=[0, 26, 27]):
            output = analyze_spans(text, model, result())
        model.predict.assert_not_called()


if __name__ == '__main__':
    unittest.main()
