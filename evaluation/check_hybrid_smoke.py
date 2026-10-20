"""Bounded real-checkpoint software smoke; synthetic inputs are not accuracy data."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'


def run():
    import torch
    from detector_models.hybrid import HybridDetector
    torch.set_num_threads(2)
    rows = [
        {'id': 'synthetic-short', 'text': 'This deliberately constructed paragraph checks local model execution. It is a software fixture, not a sample for measuring detector accuracy.'},
        {'id': 'synthetic-long', 'text': 'This deliberately repeated sentence checks tokenizer coverage and explicit truncation reporting. ' * 85},
    ]
    started = time.perf_counter()
    with patch('socket.socket.connect', side_effect=AssertionError('Network forbidden during smoke inference')):
        detector = HybridDetector()
        results = detector.predict(rows)
    assert all(not r['product_approved'] and not r['calibrated'] for r in results)
    assert results[0]['coverage_complete']
    assert not results[1]['coverage_complete']
    assert results[1]['components'][0]['truncated']
    assert not results[1]['components'][1]['truncated']
    for result in results:
        assert abs(result['score_ai'] - sum(c['score_ai'] for c in result['components']) / 2) < 1e-12
    report = dict(status='passed', scope='Synthetic software smoke only; no accuracy or human evidence.',
                  network='Socket connection attempts blocked during model loading and inference.',
                  elapsed_seconds=round(time.perf_counter() - started, 3), results=results)
    out = ROOT / 'outputs/hybrid/smoke.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}))


if __name__ == '__main__':
    run()
