"""Actual compact local-coach browser smoke; synthetic wording only."""
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
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = dict(os.environ, OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', TURINGTINT_COACH_PROFILE='compact',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'turingtint.app:app', '--host', '127.0.0.1', '--port', str(port)],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + '/api/health', timeout=1).close(); break
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
            text = 'Due to the fact that the weather was rainy, the event was postponed until a later date in the future.'
            page.locator('#passage').fill(text)
            expect(page.locator('#coach-run')).to_be_enabled()
            expect(page.locator('#analyze')).to_be_disabled()  # Missing historical MAGE never blocks the coach.
            with page.expect_response(lambda response: response.url.endswith('/api/coach/review'), timeout=180000) as pending:
                page.locator('#coach-run').click()
                expect(page.locator('#hybrid-run')).to_be_disabled()
            result = pending.value.json()
            assert result['status'] == 'complete', result.get('reason')
            assert result['model'] == 'Qwen/Qwen3-0.6B'
            assert result['suggestions'], 'Smoke fixture produced no actionable suggestions.'
            assert any(item['issue_type'] == 'redundancy' and item['rewrite'] and len(item['rewrite']) < len(item['quote'])
                       for item in result['suggestions']), 'The wordiness fixture needs an actual shorter rewrite, not an unrelated issue.'
            assert any('rain' in item['rewrite'].lower() and 'postpon' in item['rewrite'].lower()
                       for item in result['suggestions']), 'The rewrite must retain the cause and outcome: ' + repr(result['suggestions'])
            expect(page.locator('#simple-coach-results .revision-card')).to_have_count(len(result['suggestions']))
            page.locator('#simple-coach-results .revision-card button').first.click()
            selection = page.locator('#passage').evaluate('(el) => el.value.slice(el.selectionStart, el.selectionEnd)')
            assert selection == result['suggestions'][0]['quote']
            assert page.locator('#passage').input_value() == text
            out = ROOT / 'outputs/hybrid'; out.mkdir(parents=True, exist_ok=True)
            page.locator('#simple-coach').screenshot(path=str(out / 'coach-browser.png'))
            page.locator('#passage').fill('New text.')
            expect(page.locator('#simple-coach-results')).to_be_empty()
            browser.close()
        assert not external and not errors, (external, errors)
        report = dict(status='passed', actual='Local compact Qwen model and Chromium; no mocked coach response.',
                      checks=['works without historical detector', 'anchored suggestions rendered', 'sentence selection',
                              'original wording preserved', 'edited text clears feedback', 'no external browser requests'],
                      review=result, browser_errors=errors, external_requests=external)
        (out / 'coach-browser.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in report.items() if k != 'review'}))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill(); server.wait(timeout=10)


if __name__ == '__main__':
    run()
