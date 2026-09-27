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
let examples = [];
let selectedExample = null;
let comparisonOriginal = null;
let comparisonCandidate = null;
let selectedRevision = null;
const CASE_KINDS = {documented_human: 'Documented human reference', documented_ai: 'Documented AI reference', synthetic_mixed: 'Constructed mixed reference', writing_fixture: 'Writing practice fixture'};

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
function rawScore(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1) return 'Unavailable';
  const display = value.toPrecision(10);
  return Number(display) === value ? display : String(value);
}
function validRange(value, text, field = 'text') { return value && Number.isInteger(value.start) && Number.isInteger(value.end) && value.start >= 0 && value.end > value.start && value.end <= text.length && typeof value[field] === 'string' && text.slice(value.start, value.end) === value[field]; }
function textCounts(text) { return {characters: Array.from(text).length, words: text.trim() ? text.trim().split(/\s+/u).length : 0}; }
function modelLabel(model) { return !model || model.status === 'unavailable' ? 'Unavailable' : label(model.label); }
function comparableModels(previous, current, originalResult, revisedResult) {
  return previous && current && ['ok', 'complete'].includes(previous.status) && ['ok', 'complete'].includes(current.status)
    && previous.leaning_supported === true && current.leaning_supported === true
    && originalResult.input?.context_lengths_supported !== false && revisedResult.input?.context_lengths_supported !== false
    && typeof previous.score_kind === 'string' && previous.score_kind === current.score_kind
    && typeof originalResult.decision_policy === 'string' && originalResult.decision_policy === revisedResult.decision_policy
    && previous.model_revision === current.model_revision;
}
function lengthExplanation(result, version = 'This') {
  const input = result?.input;
  if (input?.context_lengths_supported !== false) return '';
  const words = Number(input.words), minimum = Number(input.minimum_context_words);
  if (!Number.isFinite(minimum) || minimum <= 0) return `${version} passage includes a context outside the supported length range for leaning labels.`;
  return Number.isFinite(words) && words < minimum
    ? `${version} passage has ${words.toLocaleString()} words; leaning labels require at least ${minimum.toLocaleString()} words per context block.`
    : `${version} passage includes a context block below the ${minimum.toLocaleString()}-word minimum for leaning labels.`;
}

function refreshCase() {
  $('case-info').hidden = !selectedExample;
  if (!selectedExample) return;
  const edited = passage.value !== selectedExample.text;
  $('case-kind').textContent = edited ? 'Modified text · reference provenance applies to the original only' : CASE_KINDS[selectedExample.provenance.kind];
  $('case-title').textContent = selectedExample.title;
  $('case-purpose').textContent = selectedExample.purpose || '';
  $('case-description').textContent = `${edited ? 'Original reference: ' : ''}${selectedExample.provenance.description || ''}`;
  $('case-expectation').textContent = selectedExample.expected_behavior || '';
  $('case-source').replaceChildren();
  const url = safeLink(selectedExample.provenance.url);
  if (url) { const link = node('a', 'Reference source ↗'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; $('case-source').append(link); }
  const licenseURL = safeLink(selectedExample.provenance.license_url);
  if (licenseURL) { const link = node('a', selectedExample.provenance.license || 'Reference license'); link.href = licenseURL; link.target = '_blank'; link.rel = 'noopener noreferrer'; $('case-source').append(link); }
  else if (selectedExample.provenance.license) $('case-source').append(node('p', selectedExample.provenance.license));
  if (selectedExample.provenance.attribution) $('case-source').append(node('p', selectedExample.provenance.attribution));
}
async function loadExamples() {
  try {
    const response = await fetch('/api/examples'); if (!response.ok) throw new Error('Cases unavailable');
    const result = await response.json();
    examples = (Array.isArray(result.examples) ? result.examples : []).filter(item => typeof item.id === 'string' && typeof item.title === 'string' && typeof item.text === 'string' && item.text.trim() && item.text.length <= passage.maxLength && CASE_KINDS[item.provenance?.kind]);
    if (!examples.length) throw new Error('Cases unavailable');
  } catch (_) {
    examples = [{id: 'assistant-demo', title: 'AI-generated academic paragraph', text: SAMPLE, provenance: {kind: 'documented_ai', description: 'Generated by an AI assistant for this demo.'}, purpose: 'Explore signals for a paragraph with a known construction history.', expected_behavior: 'Its known origin does not guarantee a particular detector result.'}];
  }
  $('example-case').replaceChildren(...examples.map(item => { const option = node('option', item.title); option.value = item.id; return option; }));
  const preferred = examples.find(item => item.text === SAMPLE);
  if (preferred) $('example-case').value = preferred.id;
  $('example-case').disabled = false; $('example').disabled = false;
}
function clearComparison() {
  comparisonOriginal = null; comparisonCandidate = null;
  $('comparison').hidden = true; $('comparison-signals').replaceChildren();
  $('comparison-original-text').textContent = ''; $('comparison-revised-text').textContent = '';
  if (lastReport) lastReport.comparison = null;
}
function renderComparison(result = null, run = null) {
  if (!comparisonOriginal || comparisonCandidate !== passage.value) { $('comparison').hidden = true; return; }
  const original = textCounts(comparisonOriginal.text), revised = textCounts(passage.value);
  $('comparison').hidden = false;
  $('comparison-original-characters').textContent = original.characters.toLocaleString(); $('comparison-revised-characters').textContent = revised.characters.toLocaleString();
  $('comparison-original-words').textContent = original.words.toLocaleString(); $('comparison-revised-words').textContent = revised.words.toLocaleString();
  $('comparison-original-text').textContent = comparisonOriginal.text; $('comparison-revised-text').textContent = passage.value;
  $('comparison-status').textContent = result ? 'Both versions have model results. A changed signal is not evidence that writing became more human.' : 'Revision added. Analyze the revised writing to compare model signals.';
  if (result) {
    const lengthNotes = [lengthExplanation(comparisonOriginal.workbench, 'The original'), lengthExplanation(result, 'The revised')].filter(Boolean);
    if (lengthNotes.length) $('comparison-status').textContent = `${lengthNotes.join(' ')} These versions are not comparable as authorship signals.`;
  }
  $('comparison-signals').replaceChildren();
  if (result) {
    const table = node('table', undefined, 'comparison-models'), head = node('thead'), headings = node('tr');
    ['Model signal', 'Original', 'Revised', 'Change'].forEach(value => headings.append(node('th', value))); head.append(headings); table.append(head);
    const body = node('tbody');
    const before = Array.isArray(comparisonOriginal.workbench.models) ? comparisonOriginal.workbench.models : [];
    const after = Array.isArray(result.models) ? result.models : [];
    const ids = [...new Set([...before, ...after].map(model => model.id).filter(id => typeof id === 'string'))];
    ids.forEach(id => {
      const previous = before.find(model => model.id === id), current = after.find(model => model.id === id);
      const comparable = comparableModels(previous, current, comparisonOriginal.workbench, result);
      const row = node('tr'); row.append(node('th', current?.name || previous?.name || id), node('td', modelLabel(previous)), node('td', modelLabel(current)), node('td', !comparable ? 'Not comparable' : modelLabel(previous) === modelLabel(current) ? 'Same signal' : 'Signal changed'));
      body.append(row);
    });
    table.append(body); $('comparison-signals').append(table);
    if (run) run.report.comparison = {original: comparisonOriginal, revised: {text: run.text, input: revised, assessment: result.assessment, models: result.models}, note: 'Experimental model signals; no authorship or quality guarantee.'};
  }
}

function refreshPrivacy() {
  const feedback = $('include-feedback').checked;
  const cloud = feedback && $('coach-provider').value === 'openai';
  $('coach-provider').disabled = !feedback;
  $('feedback-mode').textContent = feedback ? 'Detector, sources, and explained revisions' : 'Fast mode · detector and sources only';
  $('privacy-note').textContent = cloud ? 'The full passage will be sent to OpenAI for coaching when you analyze. Detector and source checks stay local.' : 'Your writing stays on this machine.';
  $('privacy-badge').replaceChildren(node('i'), document.createTextNode(cloud ? 'OpenAI coaching selected' : 'Local by default'));
  const availability = capabilities?.coaching?.[cloud ? 'openai' : 'local'];
  $('coach-availability').textContent = !feedback ? 'Skipped in fast mode' : availability?.available ? 'Available' : capabilities ? 'Coach is not ready yet' : 'Checking availability…';
}
function updateInput(options = {}) {
  revision++;
  staleNotice = staleNotice || Boolean(currentRun || lastReport);
  if (currentRun) Object.values(currentRun.controllers).forEach(controller => controller.abort());
  currentRun = null; lastReport = null;
  selectedRevision = null; $('revision-preview').hidden = true;
  if (!options.preserveComparison && comparisonCandidate !== passage.value) clearComparison();
  $('results').hidden = true;
  $('annotated-text').replaceChildren(); $('revision-cards').replaceChildren(); $('model-cards').replaceChildren(); $('model-signals').replaceChildren();
  const {words, characters} = textCounts(passage.value);
  $('word-count').textContent = `${words.toLocaleString()} words · ${characters.toLocaleString()} characters`;
  $('analyze').disabled = !words;
  $('analyze').replaceChildren(document.createTextNode('Analyze writing '), node('span', '↗'));
  $('workspace').setAttribute('aria-busy', 'false');
  message('notice', staleNotice ? 'The input changed. Analyze again to refresh the assessment and revisions.' : '');
  refreshCase(); renderComparison();
}
passage.addEventListener('input', updateInput);
$('coach-provider').addEventListener('change', () => { updateInput(); refreshPrivacy(); });
$('include-feedback').addEventListener('change', () => { updateInput(); refreshPrivacy(); });
$('reset-comparison').addEventListener('click', clearComparison);

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
  renderComparison();
  if (comparisonOriginal && comparisonCandidate === run.text) $('comparison-status').textContent = 'Analyzing the revised writing. The original model results are preserved for comparison.';
  $('coach-panel').hidden = !run.includeFeedback;
  document.querySelector('.analysis-layout').classList.toggle('feedback-off', !run.includeFeedback);
  $('assessment-label').textContent = 'Checking your writing…'; $('assessment-label').className = '';
  $('assessment-summary').textContent = 'Local detector signals will appear here first.';
  $('detector-status').textContent = 'Analyzing'; $('coach-status').textContent = 'Waiting';
  $('coach-progress').textContent = 'The coach starts after the detector, then suggestions appear here.';
  $('source-status').textContent = 'Checking local library…'; $('match-count').textContent = '—';
  $('annotated-text').textContent = run.text; $('source-annotated-text').textContent = run.text;
  $('block-count').textContent = ''; $('block-detail').hidden = true;
  $('coach-details').hidden = true; $('revision-review-note').hidden = true; $('coach-summary').textContent = '';
  $('revision-preview').hidden = true; selectedRevision = null;
  $('model-cards').replaceChildren(); $('model-signals').replaceChildren(); $('revision-cards').replaceChildren(); $('source-cards').replaceChildren(); $('source-suggestions').replaceChildren();
  $('input-details').textContent = ''; $('detector-limitations').replaceChildren();
  $('report-summary').textContent = 'This comparison covers the installed reference library.';
  ['detector-error', 'coach-error', 'source-error', 'component-warning', 'coverage-note', 'length-note'].forEach(id => message(id, ''));
}
function appendPassage(target, text, start, end, selection) {
  if (!selection || selection.end <= start || selection.start >= end) { target.append(document.createTextNode(text.slice(start, end))); return; }
  const selectedStart = Math.max(start, selection.start), selectedEnd = Math.min(end, selection.end);
  target.append(document.createTextNode(text.slice(start, selectedStart)), node('span', text.slice(selectedStart, selectedEnd), 'revision-quote'), document.createTextNode(text.slice(selectedEnd, end)));
}
function renderBlocks(text, segments, selection = null) {
  const view = $('annotated-text'); view.replaceChildren();
  const valid = (Array.isArray(segments) ? segments : []).filter(segment => validRange(segment, text)).sort((a, b) => a.start - b.start || a.end - b.end);
  let cursor = 0, count = 0;
  for (const segment of valid) {
    if (segment.start < cursor) continue;
    appendPassage(view, text, cursor, segment.start, selection);
    const value = LABELS[segment.label] ? segment.label : 'inconclusive';
    const mark = node('mark', undefined, CLASS_NAMES[value]); appendPassage(mark, text, segment.start, segment.end, selection);
    mark.tabIndex = 0; mark.setAttribute('role', 'button'); mark.setAttribute('aria-label', `${label(value)} for this context block. Show explanation.`);
    const show = () => { $('block-detail').hidden = false; $('block-label').textContent = label(value); $('block-reason').textContent = segment.reason || 'This is an experimental signal for the context block, not a claim about individual sentences.'; };
    mark.addEventListener('click', show); mark.addEventListener('keydown', event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); show(); } });
    view.append(mark); cursor = segment.end; count++;
  }
  appendPassage(view, text, cursor, text.length, selection);
  $('block-count').textContent = count ? `${count} block${count === 1 ? '' : 's'}` : 'No block signal available';
}
function renderWorkbench(result, run) {
  if (result.request_id !== run.id || result.status !== 'experimental' || result.product_approved !== false || result.validated !== false || result.offset_encoding !== 'utf-16'
      || result.input?.characters !== Array.from(run.text).length || !LABELS[result.assessment?.label]) throw new Error('The detector result did not match this passage. Please analyze again.');
  $('detector-status').textContent = 'Experimental result';
  $('assessment-label').textContent = label(result.assessment.label); $('assessment-label').className = CLASS_NAMES[result.assessment.label];
  $('assessment-summary').textContent = result.assessment.summary || '';
  message('length-note', lengthExplanation(result));
  renderBlocks(run.text, result.segments);
  const models = Array.isArray(result.models) ? result.models : [];
  for (const model of models) {
    const signal = node('div', undefined, 'model-signal');
    const modelLabel = model.status === 'unavailable' ? 'Unavailable' : label(model.label);
    const name = node('span', model.name || model.id || 'Local detector', 'model-signal-name');
    if (model.role === 'primary' || model.id === result.primary_model) name.append(node('small', 'Primary signal', 'model-role'));
    else if (model.role === 'secondary_diagnostic') name.append(node('small', 'Secondary comparison', 'model-role'));
    signal.append(name, node('span', modelLabel, `model-lean ${CLASS_NAMES[model.label] || 'lean-inconclusive'}`));
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
  $('input-details').textContent = `${Number(details.characters).toLocaleString()} characters · ${Number(details.words || 0).toLocaleString()} words · ${Number(details.analyzed_characters || 0).toLocaleString()} characters covered by ${details.coverage_basis === 'complete_primary_mage_contexts' ? 'the primary MAGE model' : 'the analysis'}`;
  message('coverage-note', details.truncated ? 'Some context blocks could not be fully scored and remain inconclusive. Inspect the model details for coverage.' : '');
  list('detector-limitations', result.limitations);
  renderComparison(result, run);
}
function showRevision(suggestion, run) {
  if (!isCurrent(run) || !validRange(suggestion, passage.value, 'quote')) return;
  selectedRevision = {suggestion, run};
  $('revision-preview').hidden = false;
  $('preview-original').textContent = suggestion.quote;
  const available = suggestion.rewrite_withheld !== true && typeof suggestion.rewrite === 'string' && Boolean(suggestion.rewrite.trim());
  $('preview-proposed').textContent = available ? suggestion.rewrite : 'Rewrite withheld; review the suggested change.';
  $('preview-reason').textContent = [suggestion.why, suggestion.suggestion].filter(value => typeof value === 'string').join(' ');
  $('apply-revision').hidden = !available;
  renderBlocks(run.text, run.report.workbench?.segments, suggestion);
  passage.setSelectionRange(suggestion.start, suggestion.end);
  $('revision-preview').scrollIntoView({behavior: 'smooth', block: 'nearest'});
}
$('close-preview').addEventListener('click', () => {
  const selected = selectedRevision; selectedRevision = null; $('revision-preview').hidden = true;
  if (selected && isCurrent(selected.run)) renderBlocks(selected.run.text, selected.run.report.workbench?.segments);
});
$('apply-revision').addEventListener('click', () => {
  if (!selectedRevision) return;
  const {suggestion, run} = selectedRevision;
  if (!isCurrent(run) || !validRange(suggestion, passage.value, 'quote') || suggestion.rewrite_withheld === true || typeof suggestion.rewrite !== 'string' || !suggestion.rewrite.trim()) return;
  const rewritten = passage.value.slice(0, suggestion.start) + suggestion.rewrite + passage.value.slice(suggestion.end);
  if (rewritten.length > passage.maxLength) { message('notice', 'This revision would exceed the editor limit. Shorten the passage before applying it.'); return; }
  if (!comparisonOriginal && run.report.component_status.workbench === 'complete') comparisonOriginal = {text: run.text, input: textCounts(run.text), workbench: JSON.parse(JSON.stringify(run.report.workbench))};
  comparisonCandidate = comparisonOriginal ? rewritten : null;
  passage.value = rewritten; updateInput({preserveComparison: true});
  message('notice', 'Revision added to your editor. Check its facts and meaning, then analyze the updated writing.'); passage.focus();
});
function renderCoach(result, run) {
  if (result.request_id !== run.id || result.provider !== run.provider) throw new Error('The coaching result did not match this request. Please analyze again.');
  if (result.status !== 'complete') throw new Error(result.reason || result.summary || 'The writing coach is unavailable. Detector and source results remain available.');
  $('coach-status').textContent = result.provider === 'openai' ? 'OpenAI coach' : 'Local coach'; $('coach-progress').textContent = '';
  $('coach-summary').textContent = result.summary || '';
  const suggestions = (Array.isArray(result.suggestions) ? result.suggestions : []).filter(suggestion => validRange(suggestion, run.text, 'quote'));
  $('revision-review-note').hidden = !suggestions.length;
  $('revision-review-note').textContent = result.explanations_source === 'fixed_issue_guidance'
    ? 'The model selects issues and wording; explanations use standard editorial guidance. Review facts and any [placeholders] before applying a revision.'
    : 'Review facts and any [placeholders] before applying a revision.';
  suggestions.forEach((suggestion, index) => {
    const card = node('article', undefined, 'revision-card'); card.append(node('span', `REVISION ${String(index + 1).padStart(2, '0')}`, 'source-number'));
    card.append(node('h4', suggestion.issue || 'Suggested improvement'));
    const quote = node('button', suggestion.quote, 'quote-anchor'); quote.type = 'button'; quote.setAttribute('aria-label', `Show original quote for revision ${index + 1}`); quote.addEventListener('click', () => showRevision(suggestion, run)); card.append(quote);
    if (suggestion.why) { const reason = node('p'); reason.append(node('strong', 'Why: '), document.createTextNode(String(suggestion.why))); card.append(reason); }
    if (suggestion.suggestion) card.append(node('p', suggestion.suggestion));
    if (suggestion.rewrite_withheld === true) card.append(node('p', 'Rewrite withheld; review the suggested change.', 'withheld-note'));
    if (suggestion.rewrite_withheld !== true && typeof suggestion.rewrite === 'string' && suggestion.rewrite.trim()) {
      const rewrite = node('div', undefined, 'rewrite'); rewrite.append(node('span', 'Suggested wording', 'tiny-label'), node('p', suggestion.rewrite)); card.append(rewrite);
      if (validRange(suggestion, run.text, 'quote')) {
        const preview = node('button', 'Review this change', 'secondary-button'); preview.type = 'button'; preview.addEventListener('click', () => showRevision(suggestion, run)); card.append(preview);
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
    if (name === 'workbench') { $('detector-status').textContent = 'Unavailable'; $('assessment-label').textContent = 'No detector assessment'; $('assessment-summary').textContent = 'The coach and source check can still provide their own results.'; message('detector-error', detail); if (comparisonOriginal && comparisonCandidate === run.text) $('comparison-status').textContent = 'The revised detector check could not finish. Original results are preserved; analyze again to complete the comparison.'; }
    else if (name === 'coaching') { $('coach-status').textContent = 'Unavailable'; $('coach-progress').textContent = ''; message('coach-error', detail); }
    else { $('source-status').textContent = 'Unavailable'; message('source-error', detail); }
  } finally { clearTimeout(timeout); delete run.controllers[name]; }
}
$('analyze').addEventListener('click', async () => {
  if (!passage.value.trim() || (currentRun && currentRun.running)) return;
  const provider = $('coach-provider').value;
  const includeFeedback = $('include-feedback').checked;
  if (includeFeedback && provider === 'openai' && capabilities?.coaching?.openai?.available !== true) { message('notice', 'OpenAI coaching is not configured. Select the local coach.'); return; }
  const run = {id: `writing-${Date.now()}-${++sequence}`, revision, text: passage.value, provider, includeFeedback, controllers: {}, running: true};
  run.report = {request_id: run.id, created_at: new Date().toISOString(), text: run.text, include_writing_feedback: includeFeedback, coaching_provider: includeFeedback ? provider : null, experimental: true, product_approved: false,
    reference_case: selectedExample ? {id: selectedExample.id, title: selectedExample.title, provenance: selectedExample.provenance, modified: selectedExample.text !== run.text} : null,
    workbench: null, coaching: null, source: null, comparison: null, errors: {}, component_status: {workbench: 'queued', coaching: includeFeedback ? 'queued' : 'skipped', source: 'queued'}};
  currentRun = run; lastReport = run.report; staleNotice = false;
  $('analyze').disabled = true; $('analyze').textContent = 'Analyzing writing…'; $('workspace').setAttribute('aria-busy', 'true'); message('notice', ''); prepareResults(run);
  const source = component(run, 'source', '/api/analyze', 60000, renderSource);
  const modelsThenCoach = (async () => {
    await component(run, 'workbench', '/api/workbench/analyze', 120000, renderWorkbench);
    if (!isCurrent(run) || !includeFeedback) return;
    $('coach-status').textContent = 'Generating'; $('coach-progress').textContent = provider === 'openai' ? 'OpenAI is reviewing the submitted passage…' : 'The local coach is preparing explained revisions. This may take a little longer…';
    await component(run, 'coaching', '/api/coach/review', 180000, renderCoach, {provider});
  })();
  await Promise.allSettled([source, modelsThenCoach]);
  if (isCurrent(run)) { run.running = false; $('analyze').disabled = false; $('analyze').replaceChildren(document.createTextNode('Analyze writing '), node('span', '↗')); $('workspace').setAttribute('aria-busy', 'false'); }
});
$('example').addEventListener('click', () => {
  const example = examples.find(item => item.id === $('example-case').value); if (!example) return;
  clearComparison(); selectedExample = example; passage.value = example.text; updateInput();
  message('notice', 'Reference case loaded. Its provenance describes the original text; analyze to see independent model signals.'); passage.focus(); passage.setSelectionRange(0, 0); passage.scrollTop = 0;
});
$('new-writing').addEventListener('click', () => {
  clearComparison(); selectedExample = null; passage.value = ''; updateInput(); staleNotice = false; message('notice', ''); passage.focus();
});
$('source-example').addEventListener('click', async () => {
  const previous = revision; $('source-example').disabled = true;
  try { const response = await fetch('/api/example'); if (!response.ok) throw new Error('No reference example is available.'); const example = await response.json();
    if (previous !== revision) return; if (!example.text) throw new Error('No reference example is available.');
    clearComparison(); selectedExample = null; passage.value = example.text; updateInput(); message('notice', 'This optional example comes from the source library. It demonstrates source overlap, not known AI authorship.'); passage.focus(); passage.setSelectionRange(0, 0); passage.scrollTop = 0;
  } catch (error) { if (previous === revision) message('notice', error.message); } finally { $('source-example').disabled = false; }
});
$('export').addEventListener('click', () => {
  if (!lastReport) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(lastReport, null, 2)], {type: 'application/json'}));
  const link = node('a'); link.href = url; link.download = 'turingtint-writing-report.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
loadCapabilities(); loadCorpus(); loadExamples(); updateInput();
