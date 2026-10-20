"""Hybrid safety/accounting contracts; these fixtures do not measure accuracy."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from detector_models.hybrid import HybridDetector
from detector_models.pretrained import verify_files, PretrainedDetector
from turingtint.app import create_app
from turingtint.coaching import GPU_LOCK
from turingtint.hybrid import HybridResearch


def row(score, truncated=False, identity='a'):
    return dict(id=identity, score_ai=score, model_id='fixture', model_revision='pinned', score_kind='fixture',
                original_tokens=700 if truncated else 20, input_tokens=512 if truncated else 20,
                max_tokens=512, truncated=truncated, device='cpu')


class HybridTests(unittest.TestCase):
    records = [{'id': 'a', 'text': 'Private test paragraph.'}]

    def hybrid(self, left=None, right=None):
        models = [Mock(), Mock()]
        models[0].predict.return_value = [left or row(.2)]
        models[1].predict.return_value = [right or row(.8)]
        return HybridDetector(factory=lambda name: models[0 if name == 'distilbert' else 1]), models

    def test_equal_mean_disagreement_and_no_verdict(self):
        detector, models = self.hybrid()
        result = detector.predict(self.records)[0]
        self.assertAlmostEqual(result['score_ai'], .5)
        self.assertTrue(result['disagreement'])
        self.assertTrue(result['coverage_complete'])
        self.assertFalse(result['product_approved'])
        self.assertFalse(result['calibrated'])
        self.assertNotIn('label', result)
        self.assertNotIn('text', result)
        for model in models:
            model.predict.assert_called_once_with(self.records, batch_size=1)

    def test_coverage_and_disagreement_are_separate(self):
        detector, _ = self.hybrid(row(.2, True), row(.21))
        result = detector.predict(self.records)[0]
        self.assertFalse(result['coverage_complete'])
        self.assertFalse(result['disagreement'])
        self.assertTrue(result['components'][0]['truncated'])

    def test_no_silent_fallback(self):
        detector, models = self.hybrid()
        models[1].predict.side_effect = RuntimeError('model failed')
        with self.assertRaises(RuntimeError):
            detector.predict(self.records)
        models[1].predict.side_effect = None
        models[1].predict.return_value = []
        with self.assertRaises(ValueError):
            detector.predict(self.records)

    def test_invalid_component_rejected(self):
        for field, value in [('score_ai', float('nan')), ('score_ai', True), ('score_ai', 1.2),
                             ('id', 'wrong'), ('model_revision', ''), ('input_tokens', 30),
                             ('truncated', True), ('original_tokens', False)]:
            with self.subTest(field=field, value=value):
                broken = row(.2); broken[field] = value
                detector, _ = self.hybrid(broken)
                with self.assertRaises(ValueError):
                    detector.predict(self.records)

    def test_members_and_budget_validation(self):
        for members in [('distilbert',), ('distilbert', 'distilbert'), ('distilbert', 'unknown')]:
            with self.assertRaises(ValueError):
                HybridDetector(members, factory=Mock())
        detector, _ = self.hybrid()
        for size in (True, 0, 5, 1.1):
            with self.assertRaises(ValueError):
                detector.predict(self.records, batch_size=size)

    def test_artifact_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp); data = b'original'
            (path / 'artifact').write_bytes(data)
            spec = {'test': {'files': {'artifact': {'size': len(data), 'kind': 'sha256', 'hash': hashlib.sha256(data).hexdigest()}}}}
            with patch('detector_models.pretrained.SPECS', spec):
                verify_files('test', path)
                (path / 'artifact').write_bytes(b'modified')
                with self.assertRaises(ValueError):
                    verify_files('test', path)

    def test_temperature_labels_and_token_type_compatibility(self):
        import torch
        predictor = PretrainedDetector.__new__(PretrainedDetector)
        predictor.name = 'distilbert'
        predictor.spec = dict(max_tokens=512, model_id='fixture', revision='pinned')
        predictor.temperature, predictor.device, predictor.torch = 2.0, 'cpu', torch
        def tokenize(text, **kwargs):
            if isinstance(text, str):
                return {'input_ids': [1, 2]}
            self.assertIs(kwargs.get('return_token_type_ids'), False)
            return {'input_ids': torch.tensor([[1, 2]]), 'attention_mask': torch.tensor([[1, 1]])}
        predictor.tokenizer = tokenize
        predictor.model = lambda input_ids, attention_mask: {'logits': torch.tensor([[0.0, 2.0]])}
        result = predictor.predict(self.records)[0]
        self.assertAlmostEqual(result['score_ai'], .73105858, places=6)
        self.assertFalse(result['truncated'])


class HybridAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        detector, models = HybridTests().hybrid(row(.2, identity='web-hybrid'), row(.8, identity='web-hybrid'))
        self.factory = Mock(return_value=detector)
        self.service = HybridResearch(self.factory)
        self.client = TestClient(create_app(Path(self.temp.name) / 'missing.sqlite', hybrid_detector=self.service))

    def test_lazy_loading_and_experimental_only(self):
        self.factory.assert_not_called()
        for _ in range(2):
            result = self.client.post('/api/research/hybrid', json={'text': 'Test paragraph.', 'request_id': 'test'}).json()
            self.assertEqual(result['request_id'], 'test')
            self.assertEqual(result['status'], 'experimental')
            self.assertFalse(result['product_approved'])
            self.assertEqual(len(result['components']), 2)
            self.assertNotIn('text', result)
        self.factory.assert_called_once()
        self.assertEqual(self.client.get('/api/health').json()['authorship']['status'], 'unavailable')

    def test_loading_failure_redacted_and_retryable(self):
        self.factory.side_effect = RuntimeError('PRIVATE /secret/path')
        response = self.client.post('/api/research/hybrid', json={'text': 'Test'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('PRIVATE', response.text)
        self.assertIn('setup-hybrid.ps1', response.text)
        self.factory.side_effect = None
        self.assertEqual(self.client.post('/api/research/hybrid', json={'text': 'Retry'}).status_code, 200)

    def test_shared_lock_and_input_guards(self):
        with GPU_LOCK:
            self.assertEqual(self.client.post('/api/research/hybrid', json={'text': 'Test'}).status_code, 409)
        self.assertEqual(self.client.post('/api/research/hybrid', json={'text': ' '}).status_code, 422)
        self.assertEqual(self.client.post('/api/research/hybrid', json={'text': 'Test'}, headers={'Origin': 'https://untrusted.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/research/hybrid', json={'text': 'Test'}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
