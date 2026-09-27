'use strict';
const $ = id => document.getElementById(id);
const passage = $('passage');
const LABELS = {ai_leaning: 'AI-leaning model signal', human_leaning: 'Human-leaning model signal', inconclusive: 'Inconclusive'};
const CLASS_NAMES = {ai_leaning: 'lean-ai', human_leaning: 'lean-human', inconclusive: 'lean-inconclusive'};
const SAMPLE = 'Urban green spaces can contribute to student wellbeing by providing accessible places for exercise, social interaction, and quiet reflection. Trees and vegetation may also reduce local heat and improve the comfort of outdoor study areas. However, the benefits of a new park depend on its location, maintenance, and accessibility. A space that is difficult to reach or feels unsafe may be used less often, even if its design is attractive. Universities should therefore combine environmental planning with consultation among students and nearby residents. Evaluating patterns of use before and after a change would help determine whether the space meets the needs of its community. These observations should be supported with local evidence rather than assumed to apply equally across all campuses.';
let revision = 0;
let sequence = 0;
let currentRun = null;
let lastReport = null;
let staleNotice = false;
let capabilities = null;

function node(tag, value, className) {
  const element = document.createElement(tag);
  if (value !== undefined && value !== null) element.textContent = String(value);
  if (className) element.className = className;
  return element;
}
function message(id, value) { $(id).textContent = value || ''; $(id).hidden = !value; }
function label(value) { return LABELS[value] || LABELS.inconclusive; }
function strings(values) { return Array.isArray(values) ? values.filter(item => typeof item === 'string') : []; }
function list(id, values) { $(id).replaceChildren(...strings(values).map(value => node('li', value))); }
function isCurrent(run) { return currentRun === run && revision === run.revision && passage.value === run.text; }
function safeLink(value) { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; } catch (_) { return null; } }
function rawScore(value) { return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1 ? value.toPrecision(10) : 'Unavailable'; }
function validRange(value, text, field = 'text') { return value && Number.isInteger(value.start) && Number.isInteger(value.end) && value.start >= 0 && value.end > value.start && value.end <= text.length && typeof value[field] === 'string' && text.slice(value.start, value.end) === value[field]; }

function refreshPrivacy() {
  const cloud = $('coach-provider').value === 'openai';
  $('privacy-note').textContent = cloud ? 'The full passage will be sent to OpenAI for coaching when you analyze. Detector and source checks stay local.' : 'Your writing stays on this machine.';
  $('privacy-badge').replaceChildren(node('i'), document.createTextNode(cloud ? 'OpenAI coaching selected' : 'Local by default'));
  const availability = capabilities?.coaching?.[cloud ? 'openai' : 'local'];
  $('coach-availability').textContent = availability?.available ? 'Available' : capabilities ? 'Coach is not ready yet' : 'Checking availability…';
}
function updateInput() {
  revision++;
  staleNotice = staleNotice || Boolean(currentRun || lastReport);
  if (currentRun) Object.values(currentRun.controllers).forEach(controller => controller.abort());
  currentRun = null; lastReport = null;
  $('results').hidden = true;
  $('annotated-text').replaceChildren(); $('revision-cards').replaceChildren(); $('model-cards').replaceChildren(); $('model-signals').replaceChildren();
  const words = passage.value.trim() ? passage.value.trim().split(/\s+/u).length : 0;
  $('word-count').textContent = `${words.toLocaleString()} words · ${Array.from(passage.value).length.toLocaleString()} characters`;
  $('analyze').disabled = !words;
  $('analyze').replaceChildren(document.createTextNode('Analyze writing '), node('span', '↗'));
  $('workspace').setAttribute('aria-busy', 'false');
  message('notice', staleNotice ? 'The input changed. Analyze again to refresh the assessment and revisions.' : '');
}
passage.addEventListener('input', updateInput);
$('coach-provider').addEventListener('change', () => { updateInput(); refreshPrivacy(); });

async function loadCapabilities() {
  try {
    const response = await fetch('/api/workbench/status');
    if (!response.ok) throw new Error('Status unavailable');
    capabilities = await response.json();
    $('detector-ready').textContent = capabilities.detector?.available ? 'Local models available' : 'Detector unavailable';
    if (capabilities.coaching?.openai?.available === true) {
      const option = node('option', 'OpenAI · sends passage to OpenAI'); option.value = 'openai'; $('coach-provider').append(option);
    }
  } catch (_) { $('detector-ready').textContent = 'Availability unknown'; }
  refreshPrivacy();
}
async function loadCorpus() {
  try {
    const response = await fetch('/api/corpus'); if (!response.ok) throw new Error('Library unavailable');
    const corpus = await response.json(); const count = Number(corpus.document_count || 0);
    $('corpus-count').textContent = `${count.toLocaleString()} local sources`;
    $('source-example').disabled = !count;
  } catch (_) { $('corpus-count').textContent = 'Library unavailable'; $('source-example').disabled = true; }
}

function prepareResults(run) {
  $('results').hidden = false;
  $('assessment-label').textContent = 'Checking your writing…'; $('assessment-label').className = '';
  $('assessment-summary').textContent = 'Local detector signals will appear here first.';
  $('detector-status').textContent = 'Analyzing'; $('coach-status').textContent = 'Waiting';
  $('coach-progress').textContent = 'The coach starts after the detector, then suggestions appear here.';
  $('source-status').textContent = 'Checking local library…'; $('match-count').textContent = '—';
  $('annotated-text').textContent = run.text; $('source-annotated-text').textContent = run.text;
  $('block-count').textContent = ''; $('block-detail').hidden = true;
  $('coach-opinion').hidden = true; $('coach-details').hidden = true; $('revision-review-note').hidden = true; $('coach-summary').textContent = '';
  $('model-cards').replaceChildren(); $('model-signals').replaceChildren(); $('revision-cards').replaceChildren(); $('source-cards').replaceChildren(); $('source-suggestions').replaceChildren();
  $('input-details').textContent = ''; $('detector-limitations').replaceChildren();
  $('report-summary').textContent = 'This comparison covers the installed reference library.';
  ['detector-error', 'coach-error', 'source-error', 'component-warning', 'coverage-note'].forEach(id => message(id, ''));
}
function renderBlocks(text, segments) {
  const view = $('annotated-text'); view.replaceChildren();
  const valid = (Array.isArray(segments) ? segments : []).filter(segment => validRange(segment, text)).sort((a, b) => a.start - b.start || a.end - b.end);
  let cursor = 0, count = 0;
  for (const segment of valid) {
    if (segment.start < cursor) continue;
    view.append(document.createTextNode(text.slice(cursor, segment.start)));
    const value = LABELS[segment.label] ? segment.label : 'inconclusive';
    const mark = node('mark', text.slice(segment.start, segment.end), CLASS_NAMES[value]);
    mark.tabIndex = 0; mark.setAttribute('role', 'button'); mark.setAttribute('aria-label', `${label(value)} for this context block. Show explanation.`);
    const show = () => { $('block-detail').hidden = false; $('block-label').textContent = label(value); $('block-reason').textContent = segment.reason || 'This is an experimental signal for the context block, not a claim about individual sentences.'; };
    mark.addEventListener('click', show); mark.addEventListener('keydown', event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); show(); } });
    view.append(mark); cursor = segment.end; count++;
  }
  view.append(document.createTextNode(text.slice(cursor)));
  $('block-count').textContent = count ? `${count} block${count === 1 ? '' : 's'}` : 'No block signal available';
}
function renderWorkbench(result, run) {
  if (result.request_id !== run.id || result.status !== 'experimental' || result.product_approved !== false || result.validated !== false || result.offset_encoding !== 'utf-16'
      || result.input?.characters !== Array.from(run.text).length || !LABELS[result.assessment?.label]) throw new Error('The detector result did not match this passage. Please analyze again.');
  $('detector-status').textContent = 'Experimental result';
  $('assessment-label').textContent = label(result.assessment.label); $('assessment-label').className = CLASS_NAMES[result.assessment.label];
  $('assessment-summary').textContent = result.assessment.summary || '';
  renderBlocks(run.text, result.segments);
  const models = Array.isArray(result.models) ? result.models : [];
  for (const model of models) {
    const signal = node('div', undefined, 'model-signal');
    const modelLabel = model.status === 'unavailable' ? 'Unavailable' : label(model.label);
    signal.append(node('span', model.name || model.id || 'Local detector', 'model-signal-name'), node('span', modelLabel, `model-lean ${CLASS_NAMES[model.label] || 'lean-inconclusive'}`));
    if (typeof model.reason === 'string') signal.title = model.reason;
    $('model-signals').append(signal);
    const card = node('article', undefined, 'model-card');
    card.append(node('h4', model.name || model.id || 'Local detector'), node('p', `${label(model.label)} · ${model.status || 'status unknown'}`));
    card.append(node('p', `Raw AI score: ${rawScore(model.score_ai)}`, 'raw-score'));
    if (model.score_kind) card.append(node('p', model.score_kind, 'model-meta'));
    if (model.reason) card.append(node('p', model.reason));
    $('model-cards').append(card);
  }
  const details = result.input || {};
  $('input-details').textContent = `${Number(details.characters).toLocaleString()} characters · ${Number(details.words || 0).toLocaleString()} words · ${Number(details.analyzed_characters || 0).toLocaleString()} characters covered by the analysis`;
  message('coverage-note', details.truncated ? 'Some context blocks could not be fully scored and remain inconclusive. Inspect the model details for coverage.' : '');
  list('detector-limitations', result.limitations);
}
function renderCoach(result, run) {
  if (result.request_id !== run.id || result.provider !== run.provider) throw new Error('The coaching result did not match this request. Please analyze again.');
  if (result.status !== 'complete') throw new Error(result.reason || result.summary || 'The writing coach is unavailable. Detector and source results remain available.');
  $('coach-status').textContent = result.provider === 'openai' ? 'OpenAI coach' : 'Local coach'; $('coach-progress').textContent = '';
  $('coach-summary').textContent = result.summary || '';
  if (result.assessment && LABELS[result.assessment.label]) {
    $('coach-opinion').hidden = false;
    $('coach-assessment').textContent = result.assessment.label === 'ai_leaning' ? 'AI-leaning opinion' : result.assessment.label === 'human_leaning' ? 'Human-leaning opinion' : 'Inconclusive opinion';
    $('coach-reason').textContent = result.assessment.reason || '';
  }
  const suggestions = (Array.isArray(result.suggestions) ? result.suggestions : []).filter(suggestion => validRange(suggestion, run.text, 'quote'));
  $('revision-review-note').hidden = !suggestions.length;
  suggestions.forEach((suggestion, index) => {
    const card = node('article', undefined, 'revision-card'); card.append(node('span', `REVISION ${String(index + 1).padStart(2, '0')}`, 'source-number'));
    card.append(node('h4', suggestion.issue || 'Suggested improvement'));
    if (suggestion.quote) card.append(node('blockquote', suggestion.quote));
    if (suggestion.why) { const reason = node('p'); reason.append(node('strong', 'Why: '), document.createTextNode(String(suggestion.why))); card.append(reason); }
    if (suggestion.suggestion) card.append(node('p', suggestion.suggestion));
    if (suggestion.rewrite_withheld === true) card.append(node('p', 'Rewrite withheld; review the suggested change.', 'withheld-note'));
    if (suggestion.rewrite_withheld !== true && typeof suggestion.rewrite === 'string' && suggestion.rewrite.trim()) {
      const rewrite = node('div', undefined, 'rewrite'); rewrite.append(node('span', 'Suggested wording', 'tiny-label'), node('p', suggestion.rewrite)); card.append(rewrite);
      if (validRange(suggestion, run.text, 'quote')) {
        const apply = node('button', 'Use this revision', 'secondary-button'); apply.type = 'button';
        apply.addEventListener('click', () => {
          if (!isCurrent(run) || !validRange(suggestion, passage.value, 'quote')) return;
          passage.value = passage.value.slice(0, suggestion.start) + suggestion.rewrite + passage.value.slice(suggestion.end);
          updateInput(); message('notice', 'Revision added to your editor. Check its facts and meaning, then analyze the updated writing.'); passage.focus();
        }); card.append(apply);
      }
    }
    $('revision-cards').append(card);
  });
  if (!suggestions.length) $('revision-cards').append(node('p', 'The coach returned no revisions anchored to this passage.', 'muted-copy'));
  $('coach-details').hidden = false; $('coach-model').textContent = `${result.model || 'Writing model'} · ${result.provider === 'openai' ? 'OpenAI' : 'Runs locally'}`;
  list('coach-limitations', result.limitations);
}
function renderSource(report, run) {
  if (report.text !== run.text || report.offset_encoding !== 'utf-16') throw new Error('The source report did not match the submitted passage.');
  const component = report.source_matching || {}; const matches = Array.isArray(component.matches) ? component.matches : [];
  const incomplete = component.status !== 'complete';
  $('source-status').textContent = incomplete ? 'Incomplete comparison' : `${matches.length} local match${matches.length === 1 ? '' : 'es'}`;
  $('match-count').textContent = String(matches.length);
  message('component-warning', [incomplete ? 'Source matching is incomplete; absence of a match is inconclusive.' : '', ...strings(component.warnings)].filter(Boolean).join(' '));
  $('report-summary').textContent = component.summary || 'Shared wording is not by itself a plagiarism verdict.';
  const valid = matches.filter(match => Number.isInteger(match.query_start) && Number.isInteger(match.query_end) && match.query_start >= 0 && match.query_end <= run.text.length && match.query_end > match.query_start);
  const boundaries = [...new Set([0, run.text.length, ...valid.flatMap(match => [match.query_start, match.query_end])])].sort((a, b) => a - b);
  const view = $('source-annotated-text'); view.replaceChildren();
  for (let index = 0; index < boundaries.length - 1; index++) {
    const start = boundaries[index], end = boundaries[index + 1]; const content = run.text.slice(start, end);
    const match = valid.find(item => item.query_start <= start && item.query_end >= end);
    if (!match) { view.append(document.createTextNode(content)); continue; }
    const mark = node('mark', content, 'source-mark'); mark.tabIndex = 0; mark.setAttribute('role', 'button'); mark.setAttribute('aria-label', 'Shared wording. Show source evidence.');
    const show = () => { const target = document.getElementById(`source-${matches.indexOf(match)}`); if (target) { target.focus(); target.scrollIntoView({behavior: 'smooth', block: 'nearest'}); } };
    mark.addEventListener('click', show); mark.addEventListener('keydown', event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); show(); } }); view.append(mark);
  }
  matches.forEach((match, index) => {
    const source = match.source || {}; const card = node('article', undefined, 'source-card'); card.id = `source-${index}`; card.tabIndex = -1;
    card.append(node('span', `${String(index + 1).padStart(2, '0')} / ${match.kind === 'near_exact_text_overlap' ? 'CLOSE WORDING' : 'TEXT OVERLAP'}`, 'source-number'), node('h4', source.title || 'Reference document'));
    const url = safeLink(source.url);
    if (url) { const link = node('a', 'Open source ↗'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; card.append(link); }
    card.append(node('blockquote', match.source_text || ''));
    const licenseURL = safeLink(source.license_url);
    if (licenseURL) { const link = node('a', source.license_id || 'Source license'); link.href = licenseURL; link.target = '_blank'; link.rel = 'noopener noreferrer'; card.append(link); }
    else card.append(node('span', source.license_id || 'License recorded in corpus', 'model-meta'));
    if (source.attribution) { const details = node('details'); details.append(node('summary', 'Attribution'), node('p', source.attribution)); card.append(details); }
    $('source-cards').append(card);
  });
  if (!matches.length) $('source-cards').append(node('p', incomplete ? 'No complete source comparison is available.' : 'No source match found in this local library. Sources outside it were not searched.', 'muted-copy'));
  (Array.isArray(report.suggestions) ? report.suggestions : []).forEach(suggestion => {
    const card = node('article', undefined, 'attribution-suggestion'); card.append(node('h4', suggestion.title), node('p', suggestion.reason), node('p', suggestion.action)); $('source-suggestions').append(card);
  });
}

async function component(run, name, path, timeoutMs, render, extra = {}) {
  if (!isCurrent(run)) return;
  const controller = new AbortController(); run.controllers[name] = controller;
  const timeout = setTimeout(() => controller.abort(), timeoutMs); run.report.component_status[name] = 'running';
  try {
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: run.text, request_id: run.id, ...extra}), signal: controller.signal});
    if (!response.ok) {
      let detail = `${name} could not complete this request.`;
      try { const error = await response.json(); if (typeof error.detail === 'string') detail = error.detail; else if (Array.isArray(error.detail)) detail = error.detail.map(item => item.msg).filter(Boolean).join(' '); } catch (_) {}
      throw new Error(detail);
    }
    const result = await response.json(); if (!isCurrent(run)) return;
    run.report[name] = result; render(result, run); run.report.component_status[name] = 'complete';
  } catch (error) {
    if (!isCurrent(run)) return;
    const detail = error.name === 'AbortError' ? `${name === 'coaching' ? 'The writing coach' : name === 'workbench' ? 'The detector' : 'Source matching'} timed out. Other results remain available.` : error.message;
    run.report.errors[name] = detail; run.report.component_status[name] = 'error';
    if (name === 'workbench') { $('detector-status').textContent = 'Unavailable'; $('assessment-label').textContent = 'No detector assessment'; $('assessment-summary').textContent = 'The coach and source check can still provide their own results.'; message('detector-error', detail); }
    else if (name === 'coaching') { $('coach-status').textContent = 'Unavailable'; $('coach-progress').textContent = ''; message('coach-error', detail); }
    else { $('source-status').textContent = 'Unavailable'; message('source-error', detail); }
  } finally { clearTimeout(timeout); delete run.controllers[name]; }
}
$('analyze').addEventListener('click', async () => {
  if (!passage.value.trim() || (currentRun && currentRun.running)) return;
  const provider = $('coach-provider').value;
  if (provider === 'openai' && capabilities?.coaching?.openai?.available !== true) { message('notice', 'OpenAI coaching is not configured. Select the local coach.'); return; }
  const run = {id: `writing-${Date.now()}-${++sequence}`, revision, text: passage.value, provider, controllers: {}, running: true};
  run.report = {request_id: run.id, created_at: new Date().toISOString(), text: run.text, coaching_provider: provider, experimental: true, product_approved: false,
    workbench: null, coaching: null, source: null, errors: {}, component_status: {workbench: 'queued', coaching: 'queued', source: 'queued'}};
  currentRun = run; lastReport = run.report; staleNotice = false;
  $('analyze').disabled = true; $('analyze').textContent = 'Analyzing writing…'; $('workspace').setAttribute('aria-busy', 'true'); message('notice', ''); prepareResults(run);
  const source = component(run, 'source', '/api/analyze', 60000, renderSource);
  const modelsThenCoach = (async () => {
    await component(run, 'workbench', '/api/workbench/analyze', 120000, renderWorkbench);
    if (!isCurrent(run)) return;
    $('coach-status').textContent = 'Generating'; $('coach-progress').textContent = provider === 'openai' ? 'OpenAI is reviewing the submitted passage…' : 'The local coach is preparing explained revisions. This may take a little longer…';
    await component(run, 'coaching', '/api/coach/review', 180000, renderCoach, {provider});
  })();
  await Promise.allSettled([source, modelsThenCoach]);
  if (isCurrent(run)) { run.running = false; $('analyze').disabled = false; $('analyze').replaceChildren(document.createTextNode('Analyze writing '), node('span', '↗')); $('workspace').setAttribute('aria-busy', 'false'); }
});
$('example').addEventListener('click', () => {
  passage.value = SAMPLE; updateInput(); message('notice', 'This sample was generated by an AI assistant for this demo. Its known origin does not guarantee a particular detector result.'); passage.focus(); passage.setSelectionRange(0, 0); passage.scrollTop = 0;
});
$('source-example').addEventListener('click', async () => {
  const previous = revision; $('source-example').disabled = true;
  try { const response = await fetch('/api/example'); if (!response.ok) throw new Error('No reference example is available.'); const example = await response.json();
    if (previous !== revision) return; if (!example.text) throw new Error('No reference example is available.');
    passage.value = example.text; updateInput(); message('notice', 'This optional example comes from the source library. It demonstrates source overlap, not known AI authorship.'); passage.focus(); passage.setSelectionRange(0, 0); passage.scrollTop = 0;
  } catch (error) { if (previous === revision) message('notice', error.message); } finally { $('source-example').disabled = false; }
});
$('export').addEventListener('click', () => {
  if (!lastReport) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(lastReport, null, 2)], {type: 'application/json'}));
  const link = node('a'); link.href = url; link.download = 'turingtint-writing-report.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
loadCapabilities(); loadCorpus(); updateInput();
