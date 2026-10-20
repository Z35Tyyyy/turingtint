"""No-training local ensemble and explicit acquisition CLI."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

from .mage import validate_records
from .pretrained import SPECS, PretrainedDetector, download_model

DEFAULT_MEMBERS = ('distilbert', 'modernbert')
SPREAD_THRESHOLD = 0.25


class HybridDetector:
    def __init__(self, members=DEFAULT_MEMBERS, *, device='cpu', factory=None):
        self.members = tuple(members)
        if not 2 <= len(self.members) <= 3 or len(set(self.members)) != len(self.members) or not set(self.members) <= SPECS.keys():
            raise ValueError('Select two or three distinct supported models.')
        factory = factory or (lambda name: PretrainedDetector(name, device=device))
        self.models = [factory(name) for name in self.members]

    def predict(self, records, *, batch_size=1):
        validate_records(records)
        if type(batch_size) is not int or not 1 <= batch_size <= 4:
            raise ValueError('Batch size must be 1 to 4.')
        predictions = [model.predict(records, batch_size=batch_size) for model in self.models]
        if any(len(rows) != len(records) for rows in predictions):
            raise ValueError('Incomplete member output; no partial ensemble is allowed.')
        results = []
        for i, record in enumerate(records):
            components = []
            for name, rows in zip(self.members, predictions):
                row = rows[i]
                score = row.get('score_ai')
                if row.get('id') != record['id'] or type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError('Invalid member identity or score.')
                for key in ('model_id', 'model_revision', 'score_kind', 'device'):
                    if not isinstance(row.get(key), str) or not row[key]:
                        raise ValueError('Missing member provenance.')
                for key in ('original_tokens', 'input_tokens', 'max_tokens'):
                    if type(row.get(key)) is not int or row[key] < 1:
                        raise ValueError('Invalid token accounting.')
                if (row['input_tokens'] > min(row['original_tokens'], row['max_tokens'])
                        or type(row.get('truncated')) is not bool
                        or row['truncated'] != (row['original_tokens'] > row['input_tokens'])):
                    raise ValueError('Inconsistent input coverage.')
                component = {k: row[k] for k in ('model_id', 'model_revision', 'score_ai', 'score_kind', 'device',
                    'original_tokens', 'input_tokens', 'max_tokens', 'truncated')}
                component.update(member=name, weight=1 / len(self.members))
                components.append(component)
            scores = [r['score_ai'] for r in components]
            spread = max(scores) - min(scores)
            results.append(dict(id=record['id'], model_id='local/hybrid-pretrained',
                model_revision='equal_mean_v2:' + ','.join(c['member'] + '@' + c['model_revision'] for c in components),
                score_ai=math.fsum(scores) / len(scores), score_kind='experimental_equal_mean',
                components=components, score_spread=spread, disagreement=spread >= SPREAD_THRESHOLD,
                disagreement_threshold=SPREAD_THRESHOLD, coverage_complete=not any(c['truncated'] for c in components),
                product_approved=False, calibrated=False,
                text_sha256=hashlib.sha256(record['text'].encode('utf-8')).hexdigest()))
        return results


def main():
    parser = argparse.ArgumentParser(description='Offline pretrained hybrid; no training or validated authorship verdict.')
    parser.add_argument('command', choices=['download', 'predict'])
    parser.add_argument('--models', nargs='+', choices=list(SPECS), default=list(DEFAULT_MEMBERS))
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--device', choices=['cpu', 'cuda', 'auto'], default='cpu')
    args = parser.parse_args()
    if args.command == 'download':
        for name in dict.fromkeys(args.models):
            download_model(name)
            print(json.dumps({'event': 'model_ready', 'member': name}), flush=True)
        return
    if args.input is None or args.output is None:
        parser.error('predict requires --input and --output.')
    pending = args.output.with_name(args.output.name + '.partial')
    if args.output.exists() or pending.exists() or args.input.resolve() == args.output.resolve():
        parser.error('Use a new output path; existing output and partial evidence are preserved.')
    from .__main__ import read_records
    records = read_records(args.input, limit=args.limit)
    detector = HybridDetector(args.models, device=args.device)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with pending.open('x', encoding='utf-8') as stream:
        for record in records:
            stream.write(json.dumps(detector.predict([record])[0], allow_nan=False) + '\n')
            stream.flush()
    pending.replace(args.output)
    print(json.dumps({'event': 'hybrid_complete', 'records': len(records), 'product_approved': False}))


if __name__ == '__main__':
    main()
