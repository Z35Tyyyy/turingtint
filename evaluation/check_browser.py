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

            research_requests = []
            research_mode = {'score': 0.0, 'truncated': False, 'error_status': None}
            def research_fixture(route):
                payload = route.request.post_data_json
                research_requests.append(payload)
                if research_mode['error_status']:
                    route.fulfill(status=research_mode['error_status'], content_type='application/json',
                                  body=json.dumps({'detail': 'The local research model is busy. Please retry shortly.'}))
                    return
                result = {
                    'request_id': payload['request_id'], 'status': 'experimental', 'product_approved': False,
                    'score_ai': research_mode['score'], 'score_kind': 'uncalibrated_softmax_class_0',
                    'input_characters': len(payload['text']), 'input_words': len(payload['text'].split()),
                    'original_tokens': 700 if research_mode['truncated'] else 120,
                    'input_tokens': 512 if research_mode['truncated'] else 120, 'max_tokens': 512,
                    'truncated': research_mode['truncated'], 'model_id': 'local/fixture',
                    'model_revision': 'test-revision', 'device': 'cpu', 'elapsed_ms': 125,
                    'limitations': ['Unvalidated research output.', '<img src=x onerror="window.injected=2">'],
                }
                route.fulfill(status=200, content_type='application/json', body=json.dumps(result))
            page.route('**/api/research/analyze', research_fixture)
            multiline = 'First paragraph includes an emoji 🧪 and careful observations.\n\nSecond paragraph remains part of the same submitted text.\n<img src=x onerror="window.injected=3">'
            page.locator('#passage').fill(multiline)
            page.locator('#research-analyze').click()
            page.locator('#research-result').wait_for(state='visible')
            assert research_requests[-1]['text'] == multiline
            assert page.locator('#research-characters').inner_text() == str(len(multiline))
            assert float(page.locator('#research-score').inner_text()) == 0.0
            assert len(page.locator('#research-score').inner_text().split('.')[1]) >= 6
            assert '%' not in page.locator('#research-score').inner_text()
            assert page.locator('#research-truncation').is_hidden()
            assert 'Not yet available' in page.locator('.overview-panel').inner_text()
            assert page.locator('#research-limitations img').count() == 0
            assert page.evaluate('window.injected || null') is None
            checks.append('Experimental test submits all multiline text and Unicode, renders a zero score precisely, and keeps authorship unavailable.')
            page.locator('#passage').fill(multiline + '\nAn additional line changes the input.')
            assert page.locator('#research-result').is_hidden()
            assert not page.locator('#research-score').inner_text()
            assert 'passage changed' in page.locator('#research-notice').inner_text()
            checks.append('Editing clears an experimental result and its score.')

            # Deliberately ignore AbortSignal in this fixture: the UI must reject
            # an old response even if cancellation cannot stop local inference.
            page.evaluate('''() => {
                window.savedResearchFetch = window.fetch;
                window.researchFetchCount = 0;
                window.fetch = (url, options) => {
                    if (url !== '/api/research/analyze') return window.savedResearchFetch(url, options);
                    window.researchFetchCount++;
                    const payload = JSON.parse(options.body);
                    return new Promise(resolve => { window.finishOldResearch = () => resolve(new Response(JSON.stringify({
                        request_id: payload.request_id, status: 'experimental', product_approved: false,
                        score_ai: 0.123456789, score_kind: 'uncalibrated_softmax_class_0',
                        input_characters: Array.from(payload.text).length, input_words: 30,
                        original_tokens: 120, input_tokens: 120, max_tokens: 512, truncated: false,
                        model_id: 'local/fixture', model_revision: 'test-revision', device: 'cpu', elapsed_ms: 100, limitations: []
                    }), {status: 200, headers: {'Content-Type': 'application/json'}})); });
                };
            }''')
            page.locator('#research-analyze').click()
            assert page.locator('#research-analyze').is_disabled()
            assert page.locator('#research').get_attribute('aria-busy') == 'true'
            page.locator('#research-analyze').dispatch_event('click')
            assert page.evaluate('window.researchFetchCount') == 1
            page.locator('#passage').fill(multiline + '\nThis newer passage must invalidate the pending result.')
            page.evaluate('async () => { window.finishOldResearch(); await new Promise(resolve => setTimeout(resolve, 75)); window.fetch = window.savedResearchFetch; }')
            assert page.locator('#research-result').is_hidden()
            assert not page.locator('#research-score').inner_text()
            assert page.locator('#research-analyze').is_enabled()
            checks.append('Duplicate experimental submits are blocked and late responses cannot replace edited text.')

            research_mode['error_status'] = 409
            page.locator('#research-analyze').click()
            page.get_by_text('The local research model is busy. Please retry shortly.', exact=True).wait_for(state='visible')
            assert page.locator('#research-result').is_hidden()
            assert page.locator('#research-analyze').is_enabled()
            research_mode.update(error_status=None, truncated=True, score=0.999987654321)
            page.locator('#research-analyze').click()
            page.locator('#research-result').wait_for(state='visible')
            assert 'first 512 of 700 tokens' in page.locator('#research-truncation').inner_text()
            assert float(page.locator('#research-score').inner_text()) < 1
            assert page.locator('#research-original-tokens').inner_text() == '700'
            assert page.locator('#research-input-tokens').inner_text() == '512 / 512 maximum'
            page.screenshot(path=str(output/'experimental-detector.png'), full_page=True)
            checks.append('Experimental errors do not produce a score; truncation and precise near-one scores remain visible.')
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
