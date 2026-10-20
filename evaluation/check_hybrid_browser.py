"""Real local browser + real hybrid inference, using a synthetic software fixture."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def run():
    from playwright.sync_api import sync_playwright, expect
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = dict(os.environ, OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'turingtint.app:app', '--host', '127.0.0.1', '--port', str(port)],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + '/api/health', timeout=1).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Server exited before startup.')
                time.sleep(.1)
        errors, external = [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: external.append(request.url) if not request.url.startswith(base + '/') else None)
            page.goto(base)
            assert not page.locator('#advanced-tools').evaluate('(el) => el.open')
            text = 'This deliberately constructed paragraph checks local model execution. It is a software fixture, not a sample for measuring detector accuracy.'
            page.locator('#passage').fill(text)
            page.locator('#hybrid-run').click()
            expect(page.locator('#analyze')).to_be_disabled()
            expect(page.locator('#hybrid-heading')).to_have_text('The models give similar scores.', timeout=120000)
            expect(page.locator('.simple-model').first).to_contain_text('DistilBERT')
            expect(page.locator('.simple-model').last).to_contain_text('ModernBERT')
            expect(page.locator('.sentence-excerpt')).to_have_text(text)
            assert page.locator('.sentence-mark').count() == 2
            page.locator('.sentence-mark').first.focus()
            page.keyboard.press('Enter')
            expect(page.locator('.sentence-detail')).to_contain_text('Limited context')
            expect(page.locator('.sentence-detail')).to_contain_text('distilbert:')
            out = ROOT / 'outputs/hybrid'
            out.mkdir(parents=True, exist_ok=True)
            page.locator('#hybrid-panel').screenshot(path=str(out / 'browser.png'))
            rendered = page.locator('#hybrid-results').inner_text()
            assert not page.locator('.score-details').evaluate('(el) => el.open')
            page.screenshot(path=str(out / 'simple-desktop.png'), full_page=True)
            page.locator('#passage').fill('Different text.')
            expect(page.locator('#hybrid-results')).to_be_empty()
            def disagreement(route):
                request_id = route.request.post_data_json['request_id']
                components = [dict(member=name, model_id='fixture/' + name, score_ai=score,
                    input_tokens=512 if truncated else 700, original_tokens=700,
                    max_tokens=512 if truncated else 8192, truncated=truncated)
                    for name, score, truncated in [('distilbert', .98, True), ('modernbert', .40, False)]]
                route.fulfill(content_type='application/json', body=json.dumps(dict(
                    request_id=request_id, product_approved=False, status='experimental', components=components,
                    score_ai=.69, score_spread=.58, disagreement=True, coverage_complete=False, limitations=[])))
            page.route('**/api/research/hybrid', disagreement)
            page.locator('#hybrid-run').click()
            expect(page.locator('#hybrid-heading')).to_have_text('The models disagree.')
            expect(page.locator('#hybrid-status')).to_contain_text('inconclusive')
            expect(page.locator('.coverage-note')).to_contain_text('only the beginning')
            assert 'Experimental average' not in page.locator('#hybrid-results').inner_text()
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(out / 'simple-mobile.png'), full_page=True)
            page.unroute('**/api/research/hybrid', disagreement)
            page.route('**/api/research/hybrid', lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': 'Fixture model unavailable.'})))
            page.locator('#hybrid-run').click()
            expect(page.locator('#hybrid-status')).to_have_text('Fixture model unavailable.')
            browser.close()
        assert not external and not errors, (external, errors)
        report = dict(status='passed', real='Chromium, local server, and first hybrid inference with pinned weights.',
                      mocked='Disagreement/truncation fixture and final 503 error response.', external_requests=external, browser_errors=errors,
                      checks=['real component scores rendered', 'concurrent analysis button disabled', 'edited text invalidates results',
                              'advanced tools and technical averages collapsed by default', 'plain-language disagreement and truncation',
                              'mobile viewport has no horizontal overflow', '503 error displayed',
                              'real sentence highlights preserve text and expose scores with keyboard selection'],
                      rendered_result=rendered, accuracy_evidence=False)
        (out / 'browser.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill(); server.wait(timeout=10)


if __name__ == '__main__':
    run()
