"""Exercise the real local interface; no external application calls allowed."""
from __future__ import annotations
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def run():
    from playwright.sync_api import sync_playwright
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'turingtint.app:app', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    output = ROOT / 'outputs/browser'
    output.mkdir(parents=True, exist_ok=True)
    external, errors = [], []
    checks = []
    try:
        for _ in range(80):
            try:
                with urllib.request.urlopen(base + '/api/health', timeout=1):
                    break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Browser-test server exited before becoming ready.')
                time.sleep(.1)
        else:
            raise RuntimeError('Browser-test server did not become ready.')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1100})
            def restrict(route):
                if not route.request.url.startswith(base + '/'):
                    external.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()
            context.route('**/*', restrict)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base, wait_until='networkidle')
            assert page.locator('#corpus-count').inner_text() != 'Connecting…'
            page.screenshot(path=str(output/'workspace.png'), full_page=True)
            page.locator('#example').click()
            page.wait_for_function("document.querySelector('#passage').value.length > 0")
            original = page.locator('#passage').input_value()
            page.locator('#analyze').click()
            page.locator('#results').wait_for(state='visible')
            assert page.locator('#source-cards .source-card').count() >= 1
            assert page.locator('#annotated-text').inner_text() == original
            assert page.locator('#annotated-text mark').count() >= 1
            assert page.locator('#component-warning').is_hidden()
            page.screenshot(path=str(output/'source-report.png'), full_page=True)
            checks.append('Real corpus example produces a matching source and exact original text.')
            page.locator('#passage').fill('A revised paragraph now replaces the previous reference passage.')
            assert page.locator('#results').is_hidden()
            checks.append('Editing invalidates the old report.')

            request = urllib.request.Request(base+'/api/analyze', data=json.dumps({'text':original}).encode(), headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:
                partial = json.load(response)
            partial['source_matching']['status'] = 'partial'
            partial['source_matching']['warnings'] = ['Evaluation fixture: only part of the library was checked.']
            page.route('**/api/analyze', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps(partial)))
            page.locator('#passage').fill(original)
            page.locator('#analyze').click()
            page.locator('#results').wait_for(state='visible')
            assert page.locator('#source-cards .source-card').count() >= 1
            assert page.locator('#component-warning').is_visible()
            assert 'only part' in page.locator('#component-warning').inner_text()
            checks.append('Positive partial reports visibly retain incomplete-search warnings.')
            page.unroute('**/api/analyze')

            hostile = '<img src=x onerror="window.injected=1"> The zephyr orchard records purple telescopes and imaginary teacups while seven fictional gardeners measure their impossible moonlit harvest.'
            page.locator('#passage').fill(hostile)
            page.locator('#analyze').click()
            page.locator('#results').wait_for(state='visible')
            assert page.locator('#annotated-text').inner_text() == hostile
            assert page.locator('#annotated-text img').count() == 0
            assert page.evaluate('window.injected || null') is None
            checks.append('User markup renders literally without code execution.')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(output/'mobile.png'), full_page=True)
            checks.append('390px mobile view has no horizontal overflow.')
            assert not errors, errors
            assert not external, external
            checks.append('No external page requests or browser JavaScript errors.')
            browser.close()
        return {'status':'passed','summary':f'{len(checks)} browser integration checks passed.', 'evidence':[{'checks':checks,'screenshots':'outputs/browser/'}]}
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)

if __name__ == '__main__':
    try:
        report = run()
    except Exception as exc:
        report = {'status':'failed','summary':f'{type(exc).__name__}: {exc}'}
    print(json.dumps(report))
    sys.exit(0 if report['status']=='passed' else 1)
