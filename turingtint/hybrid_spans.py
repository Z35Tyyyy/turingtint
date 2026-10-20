"""Bounded sentence/newline diagnostics, never validated sentence authorship."""
import math
import re
import time

MAX_SPANS = 24
MAX_SPAN_CHARS = 1200
SPAN_SECONDS = 25


def sentence_ranges(text):
    start = 0
    boundaries = [m.end() for m in re.finditer(r'''[.!?]+["')\]]*(?=\s|$)|\n+''', text)]
    for end in [*boundaries, len(text)]:
        left, right = start, end
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if left < right:
            yield left, right
        start = end


def signal_label(prediction):
    scores = [c['score_ai'] for c in prediction['components']]
    if len(scores) < 2 or any(type(s) not in (int, float) or not math.isfinite(s) or not 0 <= s <= 1 for s in scores):
        raise ValueError('Invalid sentence scores.')
    if not prediction['coverage_complete']:
        return 'unscored'
    if max(scores) - min(scores) >= .25 or min(scores) < .5 <= max(scores):
        return 'disagree'
    if min(scores) >= .65:
        return 'stronger'
    if max(scores) <= .35:
        return 'weaker'
    return 'uncertain'


def analyze_spans(text, model, document_prediction):
    started = time.monotonic()
    spans, scored = [], 0
    # Prefix map keeps UTF-16 offsets linear even for large inputs with emoji.
    offsets = [0]
    for char in text:
        offsets.append(offsets[-1] + (2 if ord(char) > 0xffff else 1))
    for index, (start, end) in enumerate(sentence_ranges(text)):
        words = len(text[start:end].split())
        item = dict(start=offsets[start], end=offsets[end], label='unscored', low_context=words < 40, scores=[])
        if index >= MAX_SPANS:
            # One neutral remainder preserves a bounded response size.
            item.update(end=offsets[-1], reason='Sentence limit reached; remaining text was not scored.')
            spans.append(item)
            break
        if words < 8:
            item['reason'] = 'Too little context: fewer than 8 words.'
        elif end - start > MAX_SPAN_CHARS:
            item['reason'] = 'This sentence exceeds the local sentence-length budget.'
        elif time.monotonic() - started >= SPAN_SECONDS:
            item['reason'] = 'Sentence analysis time budget reached.'
        else:
            try:
                prediction = document_prediction if text[start:end] == text.strip() else model.predict(
                    [{'id': f'sentence-{index}', 'text': text[start:end]}], batch_size=1)[0]
                item['label'] = signal_label(prediction)
                if item['label'] == 'unscored':
                    item['reason'] = 'A model truncated this sentence; no whole-sentence color is assigned.'
                else:
                    item['scores'] = [dict(model=c.get('member', c['model_id']), score_ai=c['score_ai']) for c in prediction['components']]
                    item['reason'] = 'Scored separately from the full passage.'
                    scored += 1
            except Exception:
                item['reason'] = 'Sentence scoring unavailable; no signal assigned.'
        spans.append(item)
    return dict(segments=spans, offset_encoding='utf-16', scored_sentences=scored,
                complete=all(s['label'] != 'unscored' for s in spans), policy='sentence_signals_v1',
                note='Each sentence or newline-separated passage is scored separately. Colors are experimental signals, not authorship labels. Short context can make scores unstable. Sentence boundaries are approximate.')
