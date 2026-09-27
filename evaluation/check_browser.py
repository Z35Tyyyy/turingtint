"""Real local source retrieval plus mocked model/coach UI contracts; no GPU or paid calls."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def utf16(text):
    return len(text.encode('utf-16-le')) // 2


def model_fixture(payload, *, truncated=False):
    text = payload['text']
    return {
        'request_id': payload['request_id'], 'status': 'experimental', 'product_approved': False,
        'validated': False, 'assessment': {'label': 'inconclusive', 'summary': 'The two local model signals disagree.'},
        'models': [
            {'id': 'first', 'name': 'First local model', 'status': 'complete', 'label': 'human_leaning', 'score_ai': 0.0, 'score_kind': 'uncalibrated', 'reason': 'A human-leaning model output.'},
            {'id': 'second', 'name': 'Second local model', 'status': 'complete', 'label': 'ai_leaning', 'score_ai': 0.999987654321, 'score_kind': 'uncalibrated', 'reason': 'An AI-leaning model output.'},
        ],
        'segments': [{'start': 0, 'end': utf16(text), 'text': text, 'label': 'inconclusive', 'reason': 'Disagreement remains inconclusive, not mixed authorship.', 'models': []}],
        'offset_encoding': 'utf-16', 'input': {'characters': len(text), 'words': len(text.split()), 'analyzed_characters': len(text), 'truncated': truncated},
        'limitations': ['Experimental signals, not established authorship.'], 'elapsed_ms': 125,
    }


def coach_fixture(payload):
    quote = payload['text'][:40]
    return {
        'request_id': payload['request_id'], 'status': 'complete', 'provider': payload.get('provider', 'local'), 'model': 'local/fixture',
        'assessment': {'label': 'ai_leaning', 'reason': 'A coach opinion must not replace the detector decision.'},
        'summary': 'Make the opening more specific while preserving the evidence.',
        'suggestions': [{'quote': quote, 'start': 0, 'end': utf16(quote), 'issue': 'Clarify the opening', 'why': 'Readers need a clear connection to the evidence.', 'suggestion': 'Use a more focused opening.', 'rewrite': 'A clearer opening supported by the evidence.'}],
        'limitations': ['Review factual meaning before applying a suggestion.'], 'elapsed_ms': 200,
    }


def run():
    from playwright.sync_api import sync_playwright, expect
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'turingtint.app:app', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    output = ROOT / 'outputs/browser'
    output.mkdir(parents=True, exist_ok=True)
    external, errors, checks = [], [], []
    calls = {'workbench': [], 'coach': []}
    mode = {'openai': False, 'model_error': False, 'coach_error': False, 'coach_unavailable': False, 'withheld': False, 'unanchored': False, 'truncated': False}
    try:
        for _ in range(100):
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
            def status_route(route):
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'detector': {'available': True}, 'coaching': {'local': {'available': True, 'model': 'local/fixture'}, 'openai': {'available': mode['openai'], 'model': 'cloud/fixture'}}}))
            def model_route(route):
                payload = route.request.post_data_json
                calls['workbench'].append(payload)
                if mode['model_error']:
                    route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': 'Local detector unavailable for this test.'}))
                else:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps(model_fixture(payload, truncated=mode['truncated'])))
            def coach_route(route):
                payload = route.request.post_data_json
                calls['coach'].append(payload)
                if mode['coach_unavailable']:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps({'request_id': payload['request_id'], 'provider': payload['provider'], 'status': 'unavailable', 'reason': 'Local model files are missing. Finish the local coach setup first.'}))
                elif mode['coach_error']:
                    route.fulfill(status=422, content_type='application/json', body=json.dumps({'detail': 'The passage is too long for this coach. Shorten it and analyze again.'}))
                else:
                    result = coach_fixture(payload)
                    if mode['withheld']:
                        result['suggestions'][0].update(rewrite='', rewrite_withheld=True)
                    if mode['unanchored']:
                        result['suggestions'][0]['quote'] = 'This fabricated quote is not in the passage.'
                    route.fulfill(status=200, content_type='application/json', body=json.dumps(result))
            page.route('**/api/workbench/status', status_route)
            page.route('**/api/workbench/analyze', model_route)
            page.route('**/api/coach/review', coach_route)
            page.goto(base, wait_until='networkidle')
            assert page.locator('#coach-provider').input_value() == 'local'
            assert page.locator('#coach-provider option[value="openai"]').count() == 0
            assert page.locator('#research-analyze').count() == 0
            assert not calls['workbench'] and not calls['coach']
            page.screenshot(path=str(output/'workspace.png'), full_page=True)
            page.locator('#example').click()
            generated = page.locator('#passage').input_value()
            assert 'generated by an AI assistant' in page.locator('#notice').inner_text()
            assert not calls['workbench'] and not calls['coach']
            checks.append('One primary action, local default, no automatic submissions, and honestly labeled generated sample.')

            multiline = 'First paragraph includes an emoji 🧪 and careful observations.\n\nSecond paragraph remains part of the same submitted text.\n<img src=x onerror="window.injected=1">'
            page.locator('#passage').fill(multiline)
            page.locator('#analyze').click()
            expect(page.locator('#coach-status')).to_have_text('Local coach')
            expect(page.locator('#analyze')).to_be_enabled()
            assert calls['workbench'][-1]['text'] == multiline == calls['coach'][-1]['text']
            assert calls['coach'][-1]['provider'] == 'local'
            assert page.locator('#annotated-text').inner_text() == multiline
            assert page.locator('#annotated-text mark.lean-inconclusive').count() == 1
            assert page.locator('#annotated-text img').count() == 0
            assert page.evaluate('window.injected || null') is None
            assert page.locator('#assessment-label').inner_text() == 'Inconclusive'
            assert 'First local model' in page.locator('#model-signals').inner_text()
            assert 'Human-leaning model signal' in page.locator('#model-signals').inner_text()
            assert 'Second local model' in page.locator('#model-signals').inner_text()
            assert 'AI-leaning model signal' in page.locator('#model-signals').inner_text()
            assert '%' not in page.locator('#model-signals').inner_text()
            assert page.locator('#coach-assessment').inner_text() == 'AI-leaning opinion'
            assert 'Review facts and any [placeholders]' in page.locator('#revision-review-note').inner_text()
            page.locator('#annotated-text mark').click()
            assert 'Disagreement remains inconclusive' in page.locator('#block-reason').inner_text()
            assert not page.locator('#source-section').get_attribute('open')
            page.locator('#model-diagnostics summary').click()
            assert page.locator('.raw-score').first.inner_text() == 'Raw AI score: 0.000000000'
            assert '0.9999876543' in page.locator('.raw-score').last.inner_text()
            page.locator('#model-diagnostics summary').click()
            checks.append('Full multiline/Unicode input is preserved, context blocks explain disagreement, and coach opinion stays separate from precise model scores.')

            with page.expect_download() as download_event:
                page.locator('#export').click()
            exported = json.loads(Path(download_event.value.path()).read_text(encoding='utf-8'))
            assert exported['text'] == multiline
            assert all(exported[name] for name in ('workbench', 'coaching', 'source'))
            assert all(value == 'complete' for value in exported['component_status'].values())
            assert page.evaluate('localStorage.length + sessionStorage.length') == 0
            checks.append('Explicit export contains all components; the app does not persist input in browser storage.')

            before = page.locator('#passage').input_value()
            page.get_by_role('button', name='Use this revision', exact=True).click()
            assert page.locator('#passage').input_value() == 'A clearer opening supported by the evidence.' + before[40:]
            assert page.locator('#results').is_hidden()
            assert 'Revision added' in page.locator('#notice').inner_text()
            checks.append('A verified quote can be replaced by a suggested revision; applying it invalidates the old report.')

            page.locator('#passage').fill(generated)
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            page.locator('#source-section summary').first.click()
            page.locator('#source-example').click()
            expect(page.locator('#notice')).to_contain_text('source library')
            reference = page.locator('#passage').input_value()
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('#source-cards .source-card').count() >= 1
            assert page.locator('#source-annotated-text').inner_text() == reference
            assert page.locator('#source-annotated-text mark').count() >= 1
            assert page.locator('#component-warning').is_hidden()
            page.screenshot(path=str(output/'source-report.png'), full_page=True)
            checks.append('Optional real reference example retains exact source matching, citations, and original-text offsets.')

            request = urllib.request.Request(base + '/api/analyze', data=json.dumps({'text': reference}).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response:
                partial = json.load(response)
            partial['source_matching'].update(status='partial', warnings=['Only part of the reference library was checked.'])
            page.route('**/api/analyze', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps(partial)))
            mode.update(model_error=True, coach_error=False)
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('#detector-error').is_visible()
            assert page.locator('#revision-cards .revision-card').count() == 1
            assert 'only part' in page.locator('#component-warning').inner_text().lower()
            page.unroute('**/api/analyze')
            mode.update(model_error=False, coach_error=True, truncated=True)
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('#assessment-label').inner_text() == 'Inconclusive'
            assert 'too long' in page.locator('#coach-error').inner_text()
            assert page.locator('#coverage-note').is_visible()
            assert page.locator('#revision-cards .revision-card').count() == 0
            checks.append('Detector/coach failures are isolated; partial source coverage and detector truncation stay visible.')
            mode.update(coach_error=False, truncated=False)
            mode['coach_unavailable'] = True
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert 'Finish the local coach setup first' in page.locator('#coach-error').inner_text()
            assert page.locator('#revision-review-note').is_hidden()
            mode['coach_unavailable'] = False
            checks.append('Unavailable coaching preserves the backend setup reason without hiding detector results.')
            mode['withheld'] = True
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('#revision-cards .revision-card').count() == 1
            assert 'Readers need a clear connection' in page.locator('#revision-cards').inner_text()
            assert 'Rewrite withheld; review the suggested change.' in page.locator('#revision-cards').inner_text()
            assert page.locator('#revision-cards .rewrite').count() == 0
            assert page.get_by_role('button', name='Use this revision', exact=True).count() == 0
            mode.update(withheld=False, unanchored=True)
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('#revision-cards .revision-card').count() == 0
            mode['unanchored'] = False
            checks.append('Withheld rewrites retain anchored advice without apply controls; fabricated quote anchors are never rendered as revisions.')

            # Held promises ignore abort to model an inference job that cannot be
            # cancelled. The UI must stage GPU work and independently reject stale results.
            page.locator('#passage').fill(multiline)
            fixtures = {'workbench': model_fixture({'text': multiline, 'request_id': 'placeholder'}), 'coach': coach_fixture({'text': multiline, 'request_id': 'placeholder', 'provider': 'local'})}
            page.evaluate('''fixtures => {
                window.originalWorkbenchFetch = window.fetch; window.coachStarted = false; window.modelFetchCount = 0;
                window.fetch = (url, options) => {
                    if (!['/api/workbench/analyze','/api/coach/review'].includes(url)) return window.originalWorkbenchFetch(url, options);
                    const body = JSON.parse(options.body); const key = url.includes('/coach/') ? 'coach' : 'workbench';
                    if (key === 'coach') window.coachStarted = true; else window.modelFetchCount++;
                    return new Promise(resolve => { window[key === 'coach' ? 'finishCoach' : 'finishWorkbench'] = () => resolve(new Response(JSON.stringify({...fixtures[key], request_id: body.request_id}), {status:200,headers:{'Content-Type':'application/json'}})); });
                };
            }''', fixtures)
            page.locator('#analyze').click()
            page.locator('#analyze').dispatch_event('click')
            assert page.evaluate('window.modelFetchCount') == 1
            assert page.evaluate('window.coachStarted') is False
            page.evaluate('window.finishWorkbench()')
            expect(page.locator('#assessment-label')).to_have_text('Inconclusive')
            expect(page.locator('#coach-status')).to_have_text('Generating')
            assert page.evaluate('window.coachStarted') is True
            page.locator('#passage').fill('A new edited passage replaces all previous input before the coach finishes.')
            page.evaluate('async () => { window.finishCoach(); await new Promise(resolve => setTimeout(resolve,75)); window.fetch=window.originalWorkbenchFetch; }')
            assert page.locator('#results').is_hidden()
            assert page.locator('#revision-cards .revision-card').count() == 0
            assert page.locator('#analyze').is_enabled()
            checks.append('One detector request runs; ML appears before coaching, and late coach responses cannot overwrite edited input.')

            mode['openai'] = True
            page.reload(wait_until='networkidle')
            count_before = len(calls['coach'])
            assert page.locator('#coach-provider').input_value() == 'local'
            page.locator('#passage').fill(multiline)
            page.locator('#coach-provider').select_option('openai')
            assert 'full passage will be sent to OpenAI' in page.locator('#privacy-note').inner_text()
            assert len(calls['coach']) == count_before
            page.locator('#analyze').click()
            expect(page.locator('#coach-status')).to_have_text('OpenAI coach')
            expect(page.locator('#analyze')).to_be_enabled()
            assert calls['coach'][-1]['provider'] == 'openai'
            assert calls['coach'][-1]['text'] == multiline
            checks.append('OpenAI is opt-in and available-only, clearly disclosed before a click; tests make no actual cloud request.')

            page.locator('#coach-provider').select_option('local')
            page.locator('#example').click()
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            page.screenshot(path=str(output/'writing-workbench.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(output/'mobile.png'), full_page=True)
            assert not errors, errors
            assert not external, external
            checks.append('Desktop/mobile workbench renders without overflow, script errors, or external page requests.')
            browser.close()
        return {'status': 'passed', 'summary': f'{len(checks)} browser integration checks passed.', 'evidence': [{'checks': checks, 'screenshots': 'outputs/browser/'}]}
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
        report = {'status': 'failed', 'summary': f'{type(exc).__name__}: {exc}'}
    print(json.dumps(report))
    sys.exit(0 if report['status'] == 'passed' else 1)
