"""Deterministic browser checks for review state, delayed responses and safe edits.

Model responses are fixtures here; check_coach_browser.py runs actual inference.
"""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TEXT = '🌱 The garden was designed in order to help students relax.\n\nThe trees provide shade throughout the afternoon.'
QUOTE = 'The garden was designed in order to help students relax.'
REWRITE = 'The garden was designed to help students relax.'


def utf16(text):
    return len(text.encode('utf-16-le')) // 2


def hybrid(request_id, text):
    split = text.index('\n') if '\n' in text else len(text)
    segments = [dict(start=0, end=utf16(text[:split]), label='disagree', low_context=True,
                     scores=[dict(model='distilbert', score_ai=.9), dict(model='modernbert', score_ai=.4)], reason='Scored separately.')]
    if '\n\n' in text:
        segments.append(dict(start=utf16(text[:split + 2]), end=utf16(text), label='unscored', low_context=True, scores=[], reason='Too little context.'))
    return dict(request_id=request_id, product_approved=False, status='experimental', disagreement=True,
                coverage_complete=False, score_ai=.65, score_spread=.5, limitations=[],
                components=[dict(member=name, model_id='fixture/' + name, score_ai=score, input_tokens=12, original_tokens=20,
                                 max_tokens=512, truncated=truncated) for name, score, truncated in [('distilbert', .9, True), ('modernbert', .4, False)]],
                sentence_signals=dict(offset_encoding='utf-16', segments=segments, complete=False))


def coach(request_id, text):
    suggestions = []
    if QUOTE in text:
        start = text.index(QUOTE)
        suggestions.append(dict(start=utf16(text[:start]), end=utf16(text[:start + len(QUOTE)]), quote=QUOTE,
                                issue='Possible redundant wording.', why='This can be said more concisely.',
                                suggestion='Remove the extra words.', rewrite=REWRITE))
    return dict(request_id=request_id, status='complete', authorship_opinion='not_provided', model='fixture/local',
                suggestions=suggestions, limitations=['Fixture feedback for UI checks only.'])


def run():
    from playwright.sync_api import sync_playwright, expect
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'turingtint.app:app', '--host', '127.0.0.1', '--port', str(port)],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    checks, errors, external = [], [], []
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + '/api/health', timeout=1).close(); break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Server exited before startup.')
                time.sleep(.1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: external.append(request.url) if not request.url.startswith(base + '/') else None)
            state = dict(available=True, hold=None, pending=[], error=None, calls=[])

            def status(route):
                route.fulfill(json=dict(detector=dict(available=False), coaching=dict(local=dict(available=state['available']), openai=dict(available=False))))

            def respond(route, kind):
                body = route.request.post_data_json
                if state['error'] == kind:
                    route.fulfill(status=503, json={'detail': 'Fixture unavailable.'})
                else:
                    result = hybrid(body['request_id'], body['text']) if kind == 'signals' else coach(body['request_id'], body['text'])
                    route.fulfill(json=result)

            def request(route, kind):
                state['calls'].append(kind)
                if state['hold'] == kind:
                    state['pending'].append((route, kind))
                else:
                    respond(route, kind)

            page.route('**/api/workbench/status', status)
            page.route('**/api/research/hybrid', lambda route: request(route, 'signals'))
            page.route('**/api/coach/review', lambda route: request(route, 'writing'))

            def fresh():
                state.update(hold=None, pending=[], error=None, calls=[])
                page.goto(base)
                expect(page.locator('#review-model-status')).to_contain_text('ready' if state['available'] else 'unavailable')
                page.locator('#passage').fill(TEXT)

            def finish_pending():
                route, kind = state['pending'].pop(0); respond(route, kind)

            fresh(); state['hold'] = 'writing'
            page.locator('#hybrid-run').click()
            expect(page.locator('#writing-stage')).to_have_attribute('data-state', 'running')
            expect(page.locator('.sentence-excerpt')).to_have_text(TEXT)
            expect(page.locator('#signal-stage')).to_have_attribute('data-state', 'done')
            expect(page.locator('#hybrid-run')).to_be_disabled()
            assert state['calls'] == ['signals', 'writing']
            expect(page.locator('.coverage-note')).to_contain_text('only the beginning')
            assert not page.locator('#hybrid-results details').evaluate('(el) => el.open')
            page.locator('.sentence-mark').first.focus(); page.keyboard.press('Enter')
            expect(page.locator('#sentence-feedback')).to_be_focused()
            expect(page.locator('.sentence-detail')).to_contain_text('Models disagree')
            expect(page.locator('#sentence-feedback')).to_contain_text('when it is ready')
            finish_pending()
            expect(page.locator('#sentence-feedback .revision-card')).to_have_count(1)
            expect(page.locator('#hybrid-run')).to_be_enabled()
            assert page.locator('#passage').input_value() == TEXT
            checks.append('One action returns signals before coaching and joins feedback to the keyboard-selected sentence')
            out = ROOT / 'outputs/hybrid'; out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / 'review-desktop.png'), full_page=True)

            page.locator('#sentence-feedback .primary-button').click()
            assert page.locator('#passage').input_value() == TEXT.replace(QUOTE, REWRITE)
            expect(page.locator('#hybrid-run')).to_have_text('Review changes')
            expect(page.locator('#sentence-feedback')).to_be_empty()
            expect(page.locator('#hybrid-results')).to_be_empty()
            expect(page.locator('#highlight-view')).to_be_disabled()
            page.locator('#undo-edit').click()
            assert page.locator('#passage').input_value() == TEXT
            expect(page.locator('#undo-edit')).to_be_hidden()
            checks.append('Apply preserves emoji/newlines and invalidates old signals; Undo restores exact original')

            state['hold'] = None
            page.locator('#hybrid-run').click()
            expect(page.locator('.suggestion-link')).to_have_count(1)
            page.locator('.suggestion-link').click()
            page.locator('#sentence-feedback .primary-button').click()
            page.locator('#passage').fill('My further manual edit.')
            expect(page.locator('#undo-edit')).to_be_hidden()
            checks.append('Undo cannot overwrite manual edits after applying a suggestion')

            fresh(); state['hold'] = 'signals'
            page.locator('#hybrid-run').click()
            expect(page.locator('#signal-stage')).to_have_attribute('data-state', 'running')
            page.locator('#passage').fill('New text while signals are running.')
            finish_pending()
            expect(page.locator('#hybrid-run')).to_be_enabled()
            expect(page.locator('#hybrid-results')).to_be_empty()
            assert state['calls'] == ['signals']
            checks.append('Late detector response is discarded and no coach request is made for edited text')

            fresh(); state['hold'] = 'writing'
            page.locator('#hybrid-run').click()
            expect(page.locator('#writing-stage')).to_have_attribute('data-state', 'running')
            page.locator('#edit-view').click()
            page.locator('#passage').fill('New text while the coach is running.')
            finish_pending()
            expect(page.locator('#hybrid-run')).to_be_enabled()
            expect(page.locator('#simple-coach-results')).to_be_empty()
            expect(page.locator('#sentence-feedback')).to_be_empty()
            assert page.locator('#passage').input_value() == 'New text while the coach is running.'
            checks.append('Late coach response cannot replace edited text or attach stale suggestions')

            fresh(); state['error'] = 'writing'
            page.locator('#hybrid-run').click()
            expect(page.locator('#coach-run')).to_be_visible()
            expect(page.locator('#simple-coach-status')).to_have_text('Fixture unavailable.')
            expect(page.locator('.sentence-excerpt')).to_have_text(TEXT)
            state['error'] = None
            page.locator('#coach-run').click()
            expect(page.locator('.suggestion-link')).to_have_count(1)
            assert state['calls'] == ['signals', 'writing', 'writing']
            checks.append('Coach failure keeps highlights; retry requests only coaching')

            fresh(); state['error'] = 'signals'
            page.locator('#hybrid-run').click()
            expect(page.locator('.suggestion-link')).to_have_count(1)
            page.locator('.suggestion-link').click()
            expect(page.locator('#hybrid-status')).to_have_text('Fixture unavailable.')
            expect(page.locator('.sentence-mark')).to_have_class('sentence-mark sentence-unscored')
            expect(page.locator('#sentence-feedback .primary-button')).to_be_enabled()
            checks.append('Detector failure leaves neutral text and usable writing feedback')

            state['available'] = False; fresh()
            page.locator('#hybrid-run').click()
            expect(page.locator('#writing-stage')).to_have_attribute('data-state', 'skipped')
            assert state['calls'] == ['signals']
            expect(page.locator('#simple-coach-status')).to_contain_text('Settings')
            checks.append('Missing local coach does not block signal review')

            state['available'] = True; fresh()
            page.locator('#open-settings').click()
            assert page.locator('#advanced-tools').evaluate('(el) => el.open')
            page.locator('#review-coaching').uncheck()
            page.locator('#hybrid-run').click()
            expect(page.locator('#writing-stage')).to_have_attribute('data-state', 'skipped')
            assert state['calls'] == ['signals']
            checks.append('Settings can skip coaching without changing detector behavior')

            fresh(); page.locator('#hybrid-run').click()
            expect(page.locator('.suggestion-link')).to_have_count(1)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('.sentence-mark').first.click()
            expect(page.locator('#sentence-feedback')).to_be_focused()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(out / 'review-mobile.png'), full_page=True)
            page.locator('#new-writing').click()
            expect(page.locator('#passage')).to_have_value('')
            expect(page.locator('#hybrid-run')).to_be_disabled()
            expect(page.locator('#sentence-feedback')).to_be_empty()
            page.locator('#passage').fill('A fresh document.')
            expect(page.locator('#hybrid-run')).to_have_text('Review text')
            checks.append('Mobile has no overflow, sentence selection reveals feedback, and New writing resets the view')
            browser.close()
        assert not errors and not external, (errors, external)
        report = dict(status='passed', evidence='Chromium with deterministic API fixtures; no accuracy claims.', checks=checks,
                      browser_errors=errors, external_requests=external)
        (out / 'review-browser.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill(); server.wait(timeout=10)


if __name__ == '__main__':
    run()
