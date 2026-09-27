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


def model_fixture(payload, *, truncated=False, revised=False):
    text = payload['text']
    return {
        'request_id': payload['request_id'], 'status': 'experimental', 'product_approved': False,
        'validated': False, 'decision_policy': 'fixture_v1', 'assessment': {'label': 'inconclusive', 'summary': 'The two local model signals disagree.'},
        'models': [
            {'id': 'first', 'name': 'First local model', 'status': 'complete', 'label': 'ai_leaning' if revised else 'human_leaning', 'score_ai': 0.0, 'score_kind': 'uncalibrated', 'reason': 'A fixture model output.', 'leaning_supported': True},
            {'id': 'second', 'name': 'Second local model', 'status': 'complete', 'label': 'ai_leaning', 'score_ai': 0.999987654321, 'score_kind': 'uncalibrated', 'reason': 'An AI-leaning model output.', 'leaning_supported': True},
        ] + ([{'id': 'third', 'name': 'Additional model', 'status': 'complete', 'label': 'inconclusive', 'score_ai': 0.5, 'leaning_supported': True}] if revised else []),
        'segments': [{'start': 0, 'end': utf16(text), 'text': text, 'label': 'inconclusive', 'reason': 'Disagreement remains inconclusive, not mixed authorship.', 'models': []}],
        'offset_encoding': 'utf-16', 'input': {'characters': len(text), 'words': len(text.split()), 'analyzed_characters': len(text), 'truncated': truncated, 'context_lengths_supported': True, 'minimum_context_words': 80},
        'limitations': ['Experimental signals, not established authorship.'], 'elapsed_ms': 125,
    }


def coach_fixture(payload):
    quote = payload['text'][:40]
    return {
        'request_id': payload['request_id'], 'status': 'complete', 'provider': payload.get('provider', 'local'), 'model': 'local/fixture',
        'assessment': None, 'authorship_opinion': 'not_provided',
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
    mode = {'openai': False, 'model_error': False, 'coach_error': False, 'coach_unavailable': False, 'withheld': False, 'unanchored': False, 'truncated': False, 'revised': False, 'primary': False, 'comparison_variant': None, 'fixed_guidance': False, 'short_comparison': False, 'same_length_rewrite': False}
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
                    result = model_fixture(payload, truncated=mode['truncated'], revised=mode['revised'])
                    if mode['comparison_variant'] == 'unavailable':
                        result['models'][0].update(status='unavailable', label='inconclusive', score_ai=None)
                    elif mode['comparison_variant'] == 'score_kind':
                        result['models'][0]['score_kind'] = 'different_recipe'
                    elif mode['comparison_variant'] == 'policy':
                        result['decision_policy'] = 'different_policy'
                    elif mode['comparison_variant'] == 'eligibility':
                        result['models'][0]['leaning_supported'] = False
                    elif mode['comparison_variant'] == 'eligibility_missing':
                        result['models'][0].pop('leaning_supported')
                    if mode['short_comparison']:
                        supported = len(payload['text'].split()) >= 80
                        result['input'].update(context_lengths_supported=supported, minimum_context_words=80)
                        result['assessment']['label'] = 'human_leaning' if supported else 'inconclusive'
                        result['models'][0]['label'] = result['assessment']['label']
                    if mode['primary']:
                        result.update(primary_model='first', decision_policy='primary_fixture')
                        result['assessment'] = {'label': 'human_leaning', 'summary': 'The primary model provides the passage signal; the secondary model remains a separate diagnostic.'}
                        result['models'][0]['role'] = 'primary'
                        result['models'][1].update(role='secondary_diagnostic', score_ai=0.9999999999999999)
                        result['segments'][0]['label'] = 'human_leaning'
                        result['input']['coverage_basis'] = 'complete_primary_mage_contexts'
                    route.fulfill(status=200, content_type='application/json', body=json.dumps(result))
            def coach_route(route):
                payload = route.request.post_data_json
                calls['coach'].append(payload)
                if mode['coach_unavailable']:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps({'request_id': payload['request_id'], 'provider': payload['provider'], 'status': 'unavailable', 'reason': 'Local model files are missing. Finish the local coach setup first.'}))
                elif mode['coach_error']:
                    route.fulfill(status=422, content_type='application/json', body=json.dumps({'detail': 'The passage is too long for this coach. Shorten it and analyze again.'}))
                else:
                    result = coach_fixture(payload)
                    if mode['same_length_rewrite']:
                        result['suggestions'][0]['rewrite'] = 'A focused opening.'.ljust(len(result['suggestions'][0]['quote']))
                    if mode['short_comparison']:
                        quote = payload['text'].split('. ')[0] + '.'
                        result['suggestions'][0].update(quote=quote, start=0, end=utf16(quote), rewrite='Students should plan ahead before starting to study.')
                    if mode['fixed_guidance']:
                        result['explanations_source'] = 'fixed_issue_guidance'
                        for suggestion in result['suggestions']:
                            suggestion['explanations_source'] = 'fixed_issue_guidance'
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
            assert page.locator('#include-feedback').is_checked()
            assert page.locator('#example-case option').count() == 6
            assert not calls['workbench'] and not calls['coach']
            page.screenshot(path=str(output/'workspace.png'), full_page=True)
            page.locator('#example-case').select_option('hc3-human')
            assert page.locator('#passage').input_value() == ''
            page.locator('#example').click()
            assert page.locator('#case-kind').inner_text() == 'Documented human reference'
            assert 'HC3' in page.locator('#case-description').text_content()
            assert 'CC-BY-SA-4.0' in page.locator('#case-source').text_content()
            assert page.locator('#results').is_hidden()
            assert not calls['workbench'] and not calls['coach']
            page.locator('#include-feedback').uncheck()
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('#assessment-label').inner_text() == 'Inconclusive'
            assert page.locator('#coach-panel').is_hidden()
            assert not calls['coach']
            assert set(calls['workbench'][-1]) == {'text', 'request_id'}
            with page.expect_download() as download_event:
                page.locator('#export').click()
            fast_report = json.loads(Path(download_event.value.path()).read_text(encoding='utf-8'))
            assert fast_report['component_status']['coaching'] == 'skipped'
            assert fast_report['coaching'] is None and fast_report['coaching_provider'] is None
            assert fast_report['reference_case']['provenance']['kind'] == 'documented_human'
            assert not fast_report['reference_case']['modified']
            checks.append('Six reference cases require explicit loading; known origin never determines model output or enters detector payloads. Fast mode skips coaching and exports that status.')
            page.locator('#include-feedback').check()
            page.locator('#example-case').select_option('assistant-challenge')
            page.locator('#example').click()
            generated = page.locator('#passage').input_value()
            assert page.locator('#case-kind').inner_text() == 'Documented AI reference'
            assert page.locator('#results').is_hidden()
            checks.append('One primary analysis action, local default, no automatic submissions, and separate reference provenance.')

            multiline = 'First paragraph includes an emoji 🧪 and careful observations.\n\nSecond paragraph remains part of the same submitted text.\n<img src=x onerror="window.injected=1">'
            page.locator('#passage').fill(multiline)
            assert 'Modified text' in page.locator('#case-kind').inner_text()
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
            assert page.locator('#coach-assessment').count() == 0
            assert 'AI-leaning opinion' not in page.locator('#coach-panel').inner_text()
            assert 'Review facts and any [placeholders]' in page.locator('#revision-review-note').inner_text()
            page.locator('#annotated-text mark').click()
            assert 'Disagreement remains inconclusive' in page.locator('#block-reason').inner_text()
            assert not page.locator('#source-section').get_attribute('open')
            page.locator('#model-diagnostics summary').click()
            assert page.locator('.raw-score').first.inner_text() == 'Raw AI score: 0.000000000'
            assert '0.9999876543' in page.locator('.raw-score').last.inner_text()
            page.locator('#model-diagnostics summary').click()
            checks.append('Full multiline/Unicode input is preserved, context blocks explain model signals, and the writing coach makes no authorship claim.')

            assert 'standard editorial guidance' not in page.locator('#revision-review-note').inner_text()
            mode['fixed_guidance'] = True
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('#revision-review-note').is_visible()
            assert 'The model selects issues and wording; explanations use standard editorial guidance.' in page.locator('#revision-review-note').inner_text()
            assert 'Review facts' in page.locator('#revision-review-note').inner_text()
            mode['fixed_guidance'] = False
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert 'standard editorial guidance' not in page.locator('#revision-review-note').inner_text()
            checks.append('Fixed editorial explanations are visibly attributed only when the API declares that source; later legacy responses do not inherit that attribution.')

            with page.expect_download() as download_event:
                page.locator('#export').click()
            exported = json.loads(Path(download_event.value.path()).read_text(encoding='utf-8'))
            assert exported['text'] == multiline
            assert all(exported[name] for name in ('workbench', 'coaching', 'source'))
            assert all(value == 'complete' for value in exported['component_status'].values())
            assert page.evaluate('localStorage.length + sessionStorage.length') == 0
            checks.append('Explicit export contains all components; the app does not persist input in browser storage.')

            before = page.locator('#passage').input_value()
            page.get_by_role('button', name='Review this change', exact=True).click()
            assert page.locator('#preview-original').inner_text() == before[:40]
            assert ''.join(page.locator('#annotated-text .revision-quote').all_text_contents()) == before[:40]
            assert page.locator('#annotated-text').inner_text() == before
            assert page.locator('#passage').input_value() == before
            page.get_by_role('button', name='Use this revision', exact=True).click()
            revised = 'A clearer opening supported by the evidence.' + before[40:]
            assert page.locator('#passage').input_value() == revised
            assert page.locator('#results').is_hidden()
            assert 'Revision added' in page.locator('#notice').inner_text()
            assert page.locator('#comparison').is_visible()
            assert 'Analyze the revised writing' in page.locator('#comparison-status').inner_text()
            assert page.locator('#comparison-original-characters').inner_text() == str(len(before))
            assert page.locator('#comparison-revised-characters').inner_text() == str(len(revised))
            assert page.locator('#comparison-original-words').inner_text() == str(len(before.split()))
            assert page.locator('#comparison-revised-words').inner_text() == str(len(revised.split()))
            mode['revised'] = True
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('.comparison-models tbody tr').count() == 3
            assert 'Human-leaning model signal' in page.locator('.comparison-models tbody tr').first.inner_text()
            assert 'AI-leaning model signal' in page.locator('.comparison-models tbody tr').first.inner_text()
            assert 'Signal changed' in page.locator('.comparison-models tbody tr').first.inner_text()
            assert 'Not comparable' in page.locator('.comparison-models tbody tr').last.inner_text()
            assert '%' not in page.locator('#comparison').inner_text()
            with page.expect_download() as download_event:
                page.locator('#export').click()
            compared = json.loads(Path(download_event.value.path()).read_text(encoding='utf-8'))
            assert compared['comparison']['original']['text'] == before
            assert compared['comparison']['revised']['text'] == revised
            assert page.evaluate('localStorage.length + sessionStorage.length') == 0
            page.screenshot(path=str(output/'revision-comparison.png'), full_page=True)
            for variant in ('unavailable', 'score_kind', 'policy', 'eligibility', 'eligibility_missing'):
                mode['comparison_variant'] = variant
                page.locator('#analyze').click()
                expect(page.locator('#analyze')).to_be_enabled()
                assert 'Not comparable' in page.locator('.comparison-models tbody tr').first.inner_text()
                assert 'Signal changed' not in page.locator('.comparison-models tbody tr').first.inner_text()
                if variant == 'unavailable':
                    assert 'Unavailable' in page.locator('.comparison-models tbody tr').first.inner_text()
                if variant == 'policy':
                    assert 'Not comparable' in page.locator('.comparison-models tbody tr').nth(1).inner_text()
            mode['comparison_variant'] = None
            checks.append('An unavailable or ineligible model, changed score recipe, or changed decision policy is Not comparable rather than a revision-driven signal change.')
            mode['model_error'] = True
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('.comparison-models').count() == 0
            assert 'could not finish' in page.locator('#comparison-status').inner_text()
            mode['model_error'] = False
            page.get_by_role('button', name='Review this change', exact=True).click()
            page.get_by_role('button', name='Use this revision', exact=True).click()
            assert page.locator('#comparison-original-text').text_content() == before
            page.locator('#example-case').select_option('hc3-ai')
            page.locator('#example').click()
            assert page.locator('#comparison').is_hidden()
            assert page.locator('#comparison-original-text').text_content() == ''
            assert page.locator('#case-kind').inner_text() == 'Documented AI reference'
            mode['revised'] = False
            checks.append('Anchored preview highlights the exact original quote before apply. Reanalysis compares dynamic model lists and exact Unicode/word counts; repeated edits retain the original, and another case clears it.')

            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            page.get_by_role('button', name='Review this change', exact=True).click()
            page.get_by_role('button', name='Use this revision', exact=True).click()
            reset_text = page.locator('#passage').input_value()
            page.locator('#reset-comparison').click()
            assert page.locator('#comparison').is_hidden()
            assert page.locator('#passage').input_value() == reset_text
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            page.get_by_role('button', name='Review this change', exact=True).click()
            page.get_by_role('button', name='Use this revision', exact=True).click()
            page.locator('#passage').fill('Unrelated replacement text must not inherit a prior comparison.')
            assert page.locator('#comparison').is_hidden()
            assert page.locator('#comparison-original-text').text_content() == ''
            page.locator('#new-writing').click()
            assert page.locator('#passage').input_value() == ''
            assert page.locator('#case-info').is_hidden()
            checks.append('Clear comparison preserves the edited text; unrelated manual input and New writing discard the prior comparison and stale provenance display.')

            mode['short_comparison'] = True
            page.locator('#example-case').select_option('revision-practice')
            page.locator('#example').click()
            assert len(page.locator('#passage').input_value().split()) == 88
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('#length-note').is_hidden()
            page.get_by_role('button', name='Review this change', exact=True).click()
            page.get_by_role('button', name='Use this revision', exact=True).click()
            assert len(page.locator('#passage').input_value().split()) == 79
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('#length-note').is_visible()
            assert '79 words' in page.locator('#length-note').inner_text()
            assert 'at least 80 words' in page.locator('#length-note').inner_text()
            assert '79 words' in page.locator('#comparison-status').inner_text()
            assert 'not comparable' in page.locator('#comparison-status').inner_text()
            assert 'Signal changed' not in page.locator('#comparison-signals').inner_text()
            assert all('Not comparable' in row for row in page.locator('.comparison-models tbody tr').all_text_contents())
            mode['short_comparison'] = False
            checks.append('An actual 88-to-79-word edit crosses the declared minimum: its reason is prominent and both model rows become Not comparable, without implying a revision-driven authorship change.')

            page.locator('#new-writing').click()
            page.locator('#passage').fill(multiline)
            mode['same_length_rewrite'] = True
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            page.get_by_role('button', name='Review this change', exact=True).click()
            page.get_by_role('button', name='Use this revision', exact=True).click()
            assert len(page.locator('#passage').input_value()) == len(multiline)
            for variant in ('eligibility', 'eligibility_missing'):
                mode['comparison_variant'] = variant
                page.locator('#analyze').click()
                expect(page.locator('#analyze')).to_be_enabled()
                assert 'Not comparable' in page.locator('.comparison-models tbody tr').first.inner_text()
                assert 'Signal changed' not in page.locator('.comparison-models tbody tr').first.inner_text()
            mode.update(same_length_rewrite=False, comparison_variant=None)
            checks.append('Even for equal character counts, false or missing leaning eligibility prevents comparison; fully verified metadata is required on both versions.')

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
            page.get_by_role('button', name='Show original quote for revision 1', exact=True).click()
            assert page.locator('#revision-preview').is_visible()
            assert page.locator('#apply-revision').is_hidden()
            assert 'Rewrite withheld' in page.locator('#preview-proposed').inner_text()
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
            page.locator('#include-feedback').uncheck()
            assert page.locator('#coach-provider').is_disabled()
            assert 'stays on this machine' in page.locator('#privacy-note').inner_text()
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert len(calls['coach']) == count_before
            assert page.locator('#coach-panel').is_hidden()
            page.locator('#include-feedback').check()
            page.locator('#analyze').click()
            expect(page.locator('#coach-status')).to_have_text('OpenAI coach')
            expect(page.locator('#analyze')).to_be_enabled()
            assert calls['coach'][-1]['provider'] == 'openai'
            assert calls['coach'][-1]['text'] == multiline
            checks.append('OpenAI is opt-in and available-only; fast mode skips even an explicitly selected cloud coach. Tests make no actual cloud request.')

            page.locator('#coach-provider').select_option('local')
            mode['primary'] = True
            page.locator('#example-case').select_option('assistant-challenge')
            page.locator('#example').click()
            page.locator('#analyze').click()
            expect(page.locator('#analyze')).to_be_enabled()
            assert page.locator('#assessment-label').inner_text() == 'Human-leaning model signal'
            assert 'Primary signal' in page.locator('#model-signals').inner_text()
            assert 'Secondary comparison' in page.locator('#model-signals').inner_text()
            assert 'AI-leaning model signal' in page.locator('#model-signals').inner_text()
            assert 'the primary MAGE model' in page.locator('#input-details').text_content()
            assert '0.9999999999999999' in page.locator('.raw-score').last.text_content()
            assert 'disagreement is inconclusive' not in page.locator('.experiment-note').inner_text().lower()
            checks.append('Primary and secondary roles stay visible; the UI preserves the backend decision despite secondary disagreement and never rounds a near-one raw score to one.')
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
