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
            text = 'This deliberately constructed paragraph checks local model execution. It is a software fixture, not a sample for measuring detector accuracy.'
            page.locator('#passage').fill(text)
            page.locator('#hybrid-run').click()
            expect(page.locator('#analyze')).to_be_disabled()
            expect(page.locator('#hybrid-status')).to_have_text('Comparison complete. Authorship remains unverified.', timeout=120000)
            expect(page.locator('#hybrid-results')).to_contain_text('rasbt/ai-text-detector-distilbert')
            expect(page.locator('#hybrid-results')).to_contain_text('rasbt/ai-text-detector-modernbert')
            out = ROOT / 'outputs/hybrid'
            out.mkdir(parents=True, exist_ok=True)
            page.locator('#hybrid-panel').screenshot(path=str(out / 'browser.png'))
            rendered = page.locator('#hybrid-results').inner_text()
            page.locator('#passage').fill('Different text.')
            expect(page.locator('#hybrid-results')).to_be_empty()
            page.route('**/api/research/hybrid', lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': 'Fixture model unavailable.'})))
            page.locator('#hybrid-run').click()
            expect(page.locator('#hybrid-status')).to_have_text('Fixture model unavailable.')
            browser.close()
        assert not external and not errors, (external, errors)
        report = dict(status='passed', real='Chromium, local server, and first hybrid inference with pinned weights.',
                      mocked='Only final 503 error response.', external_requests=external, browser_errors=errors,
                      checks=['real component scores rendered', 'concurrent analysis button disabled', 'edited text invalidates results', '503 error displayed'],
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
