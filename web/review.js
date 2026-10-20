'use strict';

// The current review owns one exact text revision. Model responses never edit it.
let reviewRun = null;
let undoEdit = null;
let reviewOutdated = false;
let selectedSentence = null;
const SIGNAL_LABELS = {stronger: 'Stronger AI signal', weaker: 'Weaker AI signal', disagree: 'Models disagree', uncertain: 'Uncertain signal', unscored: 'Not enough signal'};

function signalScore(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1) throw new Error('Invalid model score.');
  if (value > 0 && value < 0.001) return '<0.001';
  if (value < 1 && value > 0.999) return '>0.999';
  return value.toFixed(3);
}
function currentReview(run = reviewRun) { return run && run === reviewRun && run.revision === revision && run.text === passage.value; }
function reviewBusy() { return Boolean(reviewRun?.running || currentRun?.running); }
function setPassageView(highlights, focus = false) {
  highlights = highlights && currentReview() && Boolean(reviewRun.segments?.length);
  passage.hidden = Boolean(highlights);
  $('passage-preview').hidden = !highlights;
  $('edit-view').setAttribute('aria-pressed', String(!highlights));
  $('highlight-view').setAttribute('aria-pressed', String(Boolean(highlights)));
  if (focus && !highlights) passage.focus();
}
function refreshReviewControls() {
  const busy = reviewBusy(), hasText = Boolean(passage.value.trim());
  $('hybrid-run').disabled = !hasText || busy;
  $('hybrid-run').textContent = busy ? 'Reviewing…' : reviewOutdated ? 'Review changes' : 'Review text';
  $('analyze').disabled = !hasText || busy || capabilities?.detector?.available !== true;
  $('highlight-view').disabled = !currentReview() || !reviewRun.segments?.length;
  $('undo-edit').hidden = !undoEdit || undoEdit.after !== passage.value;
  const available = capabilities?.coaching?.local?.available === true;
  $('coach-run').disabled = !available || !hasText || busy || !currentReview();
  $('review-model-status').textContent = !capabilities ? 'Writing model availability unknown.' : available
    ? 'Local writing model ready. Text stays on this computer.' : 'The local writing model is unavailable. Signal checks still work.';
}
function reviewInputChanged(options = {}) {
  if (!options.preserveUndo) undoEdit = null;
  if (!passage.value && !reviewRun?.running) reviewRun = null;
  if (reviewRun) reviewOutdated = true;
  if (!passage.value) reviewOutdated = false;
  selectedSentence = null;
  $('passage-preview').replaceChildren();
  $('hybrid-results').replaceChildren();
  $('sentence-feedback').replaceChildren();
  $('simple-coach-results').replaceChildren();
  $('coach-run').hidden = true;
  setPassageView(false);
  $('hybrid-heading').textContent = reviewOutdated ? 'Your text has changed.' : 'Ready when you are.';
  $('hybrid-status').textContent = reviewOutdated ? 'Previous signals are outdated. Review changes to check this version.' : 'Paste a passage and choose Review text. Signals appear first, followed by writing suggestions.';
  $('simple-coach-status').textContent = reviewOutdated ? 'Review this version for fresh suggestions.' : 'Select a sentence after reviewing your text.';
  $('review-progress').hidden = !reviewRun?.running;
  if (reviewRun?.running) $('review-progress-copy').textContent = 'Finishing the previous request. You can keep editing; its results will not replace your changes.';
  refreshReviewControls();
}
function stage(run, kind, state, copy) {
  if (!currentReview(run)) return;
  run[`${kind}State`] = state;
  const element = $(kind === 'signals' ? 'signal-stage' : 'writing-stage');
  element.dataset.state = state;
  const labels = {signals: {waiting: '1. Signals queued', running: '1. Checking signals', done: '1. Signals ready', error: '1. Signals unavailable'},
    writing: {waiting: '2. Wording queued', running: '2. Reviewing wording', done: '2. Wording ready', error: '2. Wording unavailable', skipped: '2. Wording skipped'}};
  element.textContent = labels[kind][state];
  if (copy) $('review-progress-copy').textContent = copy;
}
function validSegments(data, text) {
  if (!data) return [{start: 0, end: text.length, label: 'unscored', scores: [], reason: 'Sentence signals are unavailable for this review.'}];
  if (data.offset_encoding !== 'utf-16' || !Array.isArray(data.segments) || !data.segments.length) throw new Error('Invalid sentence offsets.');
  let previous = 0;
  for (const segment of data.segments) {
    if (!Number.isInteger(segment.start) || !Number.isInteger(segment.end) || segment.start < previous || segment.end <= segment.start || segment.end > text.length || !SIGNAL_LABELS[segment.label]) throw new Error('Invalid sentence coverage.');
    if (segment.scores) segment.scores.forEach(score => signalScore(score.score_ai));
    previous = segment.end;
  }
  return data.segments;
}
function renderPassage(run) {
  const target = $('passage-preview'); target.replaceChildren();
  const legend = node('div', undefined, 'sentence-legend');
  legend.setAttribute('aria-label', 'Signal color legend');
  for (const [key, value] of Object.entries(SIGNAL_LABELS)) legend.append(node('span', value, `sentence-${key}`));
  const excerpt = node('div', undefined, 'sentence-excerpt');
  excerpt.setAttribute('aria-label', 'Reviewed passage. Select a sentence for feedback.');
  let cursor = 0;
  run.segments.forEach((segment, index) => {
    excerpt.append(document.createTextNode(run.text.slice(cursor, segment.start)));
    const mark = node('span', run.text.slice(segment.start, segment.end), `sentence-mark sentence-${segment.label}`);
    mark.tabIndex = 0; mark.setAttribute('role', 'button'); mark.setAttribute('aria-pressed', 'false');
    mark.setAttribute('aria-controls', 'sentence-feedback'); mark.dataset.sentence = index;
    mark.setAttribute('aria-label', `Sentence ${index + 1}. ${SIGNAL_LABELS[segment.label]}. ${segment.low_context ? 'Limited context. ' : ''}${mark.textContent}`);
    const select = () => selectSentence(run, index, window.matchMedia('(max-width:760px)').matches);
    mark.addEventListener('click', select);
    mark.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectSentence(run, index, true); } });
    excerpt.append(mark); cursor = segment.end;
  });
  excerpt.append(document.createTextNode(run.text.slice(cursor)));
  target.append(legend, excerpt, node('p', 'Select a sentence to see its signal and writing feedback. Short passages can produce unstable scores.', 'score-explanation'));
  refreshReviewControls();
}
function selectSentence(run, index, focus = false) {
  if (!currentReview(run)) return;
  selectedSentence = index;
  document.querySelectorAll('.sentence-mark').forEach(mark => mark.setAttribute('aria-pressed', String(Number(mark.dataset.sentence) === index)));
  renderSentenceFeedback(run);
  if (focus) { $('sentence-feedback').focus({preventScroll: true}); $('sentence-feedback').scrollIntoView({block: 'nearest', behavior: 'smooth'}); }
}
function renderSentenceFeedback(run) {
  if (!currentReview(run)) return;
  const target = $('sentence-feedback'); target.replaceChildren();
  if (selectedSentence === null) { target.append(node('p', 'Choose a sentence in Highlights, or open a suggestion below.', 'feedback-empty')); return; }
  const segment = run.segments[selectedSentence];
  const suggestions = (run.coach?.suggestions || []).filter(item => item.start < segment.end && item.end > segment.start);
  target.append(node('h3', `Sentence ${selectedSentence + 1}`));
  if (!suggestions.length) target.append(node('blockquote', run.text.slice(segment.start, segment.end), 'selected-quote'));
  const detail = node('div', undefined, 'sentence-detail');
  detail.append(node('strong', SIGNAL_LABELS[segment.label], `signal-label sentence-${segment.label}`));
  const explanations = {stronger: 'Both models found stronger AI-like patterns in this sentence.', weaker: 'Both models found weaker AI-like patterns in this sentence.', disagree: 'The models read this sentence differently. Treat its signal as inconclusive.', uncertain: 'The scores do not give a clear signal.', unscored: 'There is not enough usable model evidence to color this sentence.'};
  detail.append(node('p', explanations[segment.label]));
  if (segment.low_context) detail.append(node('p', 'Limited context: short sentence.', 'context-hint'));
  const scores = node('details', undefined, 'sentence-scores'); scores.append(node('summary', 'Signal details & model scores'));
  if (segment.reason) scores.append(node('p', segment.reason));
  (segment.scores || []).forEach(score => scores.append(node('p', `${score.model}: ${signalScore(score.score_ai)}`)));
  scores.append(node('p', 'Scores are model signals, not authorship probabilities. Short context can make them unstable.')); detail.append(scores);
  target.append(detail);
  if (!suggestions.length) target.append(node('p', run.coachState === 'running' || run.coachState === 'waiting' ? 'Writing feedback will appear here when it is ready.' : run.coachState === 'done' ? 'No writing suggestion for this sentence.' : 'Writing feedback is unavailable for this review.', 'feedback-empty'));
  suggestions.forEach(suggestion => {
    const card = node('article', undefined, 'revision-card');
    card.append(node('h3', suggestion.issue), node('p', suggestion.why));
    if (suggestion.rewrite) {
      card.append(node('h4', 'Original'), node('blockquote', suggestion.quote), node('h4', 'Suggested wording'), node('blockquote', suggestion.rewrite, 'suggested-wording'));
      const apply = node('button', 'Apply suggestion', 'primary-button'); apply.type = 'button';
      apply.addEventListener('click', () => applySuggestion(run, suggestion));
      card.append(apply);
    } else card.append(node('p', suggestion.suggestion));
    target.append(card);
  });
}
function applySuggestion(run, suggestion) {
  if (!currentReview(run) || !validRange(suggestion, passage.value, 'quote') || typeof suggestion.rewrite !== 'string' || !suggestion.rewrite.trim()) return;
  const before = passage.value, after = before.slice(0, suggestion.start) + suggestion.rewrite + before.slice(suggestion.end);
  if (after.length > passage.maxLength) { message('notice', 'This suggestion would exceed the text limit. Shorten the passage first.'); return; }
  undoEdit = {before, after}; passage.value = after;
  updateInput({preserveUndo: true});
  setPassageView(false, true); passage.setSelectionRange(suggestion.start, suggestion.start + suggestion.rewrite.length);
  message('notice', 'Suggestion applied. Undo is available above. Review changes for fresh signals.');
}
function renderCoachSuggestions(run) {
  const target = $('simple-coach-results'); target.replaceChildren();
  const suggestions = run.coach.suggestions;
  $('simple-coach-status').textContent = suggestions.length ? `${suggestions.length} ${suggestions.length === 1 ? 'suggestion' : 'suggestions'} to explore.` : 'No specific edits suggested.';
  suggestions.forEach((suggestion, index) => {
    const item = node('button', undefined, 'suggestion-link'); item.type = 'button';
    item.append(node('strong', `${index + 1}. ${suggestion.issue}`));
    item.addEventListener('click', () => {
      const sentence = run.segments.findIndex(segment => suggestion.start < segment.end && suggestion.end > segment.start);
      if (sentence >= 0) { setPassageView(true); selectSentence(run, sentence, true); }
    });
    target.append(item);
  });
  const details = node('details', undefined, 'score-details'); details.append(node('summary', 'About writing feedback'), node('p', run.coach.model));
  const limits = node('ul'); strings(run.coach.limitations).forEach(value => limits.append(node('li', value))); details.append(limits); target.append(details);
  renderSentenceFeedback(run);
}
function renderHybrid(result, run) {
  if (typeof result.disagreement !== 'boolean' || typeof result.coverage_complete !== 'boolean') throw new Error('Incomplete comparison.');
  signalScore(result.score_ai); signalScore(result.score_spread);
  result.components.forEach(component => signalScore(component.score_ai));
  const segments = validSegments(result.sentence_signals, run.text);
  $('hybrid-heading').textContent = result.disagreement ? 'The models disagree.' : 'The models give similar scores.';
  $('hybrid-status').textContent = result.disagreement ? 'Treat this check as inconclusive. Select a sentence to take a closer look.' : 'Agreement cannot confirm who wrote this text. Select a sentence to explore its signal.';
  const container = $('hybrid-results'); container.replaceChildren();
  container.append(node('p', result.coverage_complete ? 'Both models read your full text.' : 'At least one model read only the beginning. Some text is outside its coverage.', result.coverage_complete ? 'coverage-note complete' : 'coverage-note partial'));
  const details = node('details', undefined, 'score-details'); details.append(node('summary', 'Model scores & details'), node('p', 'Higher scores mean stronger AI-pattern signals. These are not authorship probabilities.'));
  const cards = node('div', undefined, 'simple-models');
  result.components.forEach(component => {
    const name = component.member === 'distilbert' ? 'DistilBERT' : component.member === 'modernbert' ? 'ModernBERT' : component.model_id;
    const card = node('article', undefined, 'simple-model');
    card.append(node('h3', name), node('strong', signalScore(component.score_ai), 'signal-score'), node('p', `${component.input_tokens} of ${component.original_tokens} tokens read.`));
    cards.append(card);
  });
  details.append(cards, node('p', `Experimental average: ${rawScore(result.score_ai)}. This is not a percentage of AI-written text.`));
  const limits = node('ul'); strings(result.limitations).forEach(value => limits.append(node('li', value))); details.append(limits); container.append(details);
  run.segments = segments; renderPassage(run); renderSentenceFeedback(run);
  // Leave the editor available if the user has started typing or explicitly chosen it.
  if (!run.keepEditing) setPassageView(true);
}
async function reviewRequest(path, body, timeoutMs) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), signal: controller.signal});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'This part of the review could not finish.');
    if (result.request_id !== body.request_id) throw new Error('The review response did not match this request.');
    return result;
  } finally { clearTimeout(timer); }
}
function reviewError(error) { return error.name === 'AbortError' ? 'This request timed out. The server may still be working; wait before retrying.' : error.message; }
async function runWritingReview(run) {
  if (!currentReview(run)) return;
  if (!run.includeCoach || capabilities?.coaching?.local?.available !== true) {
    run.coachState = 'skipped';
    stage(run, 'writing', 'skipped', 'Signal review finished. Writing feedback is skipped.');
    $('simple-coach-status').textContent = run.includeCoach ? 'Writing feedback is unavailable. See Settings for local model setup.' : 'Writing suggestions are off in Settings.';
    renderSentenceFeedback(run); return;
  }
  simpleCoachRunning = true; run.coachState = 'running';
  stage(run, 'writing', 'running', 'Reviewing wording locally. This took about 50 seconds in our CPU check. You can explore highlights or keep editing.');
  $('simple-coach-status').textContent = 'Reviewing wording. Suggestions will appear here.';
  $('coach-run').hidden = true;
  try {
    const result = await reviewRequest('/api/coach/review', {text: run.text, provider: 'local', request_id: `coach-${run.id}`}, 180000);
    if (!currentReview(run)) return;
    if (result.status !== 'complete') throw new Error(result.reason || 'Writing feedback could not finish.');
    if (!Array.isArray(result.suggestions) || result.authorship_opinion !== 'not_provided' || result.suggestions.some(s => !validRange(s, run.text, 'quote') || typeof s.rewrite !== 'string')) throw new Error('Invalid writing feedback.');
    run.coach = result; run.coachState = 'done';
    renderCoachSuggestions(run); stage(run, 'writing', 'done', run.signalsState === 'error' ? 'Writing review finished. Signal checks are unavailable; you can retry with Review text.' : 'Review finished. Select a sentence or suggestion to explore it.');
  } catch (error) {
    if (currentReview(run)) {
      run.coachState = 'error'; stage(run, 'writing', 'error', run.signalsState === 'done' ? 'Writing feedback could not finish. Your signal results are still available.' : 'The review could not finish. You can retry.');
      $('simple-coach-status').textContent = reviewError(error); $('coach-run').hidden = false; renderSentenceFeedback(run);
    }
  } finally { simpleCoachRunning = false; }
}
async function startReview() {
  if (reviewBusy() || !passage.value.trim()) return;
  const run = {id: `${Date.now()}-${++sequence}`, text: passage.value, revision, running: true, includeCoach: $('review-coaching').checked, coachState: 'waiting', segments: null, keepEditing: false};
  reviewRun = run; reviewOutdated = false; selectedSentence = null; hybridRunning = true;
  $('hybrid-results').replaceChildren(); $('passage-preview').replaceChildren(); $('sentence-feedback').replaceChildren(); $('simple-coach-results').replaceChildren();
  $('coach-run').hidden = true; setPassageView(false); refreshReviewControls(); message('notice', '');
  $('hybrid-heading').textContent = 'Checking your text…';
  $('hybrid-status').textContent = 'Checking the passage and its sentences with two local detectors. First use includes loading the models.';
  $('simple-coach-status').textContent = run.includeCoach ? 'Writing feedback follows the signal check.' : 'Writing suggestions are off in Settings.';
  $('review-progress').hidden = false;
  stage(run, 'signals', 'running', 'Checking signals locally. You can continue editing while you wait.'); stage(run, 'writing', 'waiting');
  try {
    try {
      const result = await reviewRequest('/api/research/hybrid', {text: run.text, request_id: `hybrid-${run.id}`}, 300000);
      if (!currentReview(run)) return;
      if (result.product_approved !== false || result.status !== 'experimental' || !Array.isArray(result.components) || result.components.length < 2) throw new Error('Unexpected hybrid result.');
      renderHybrid(result, run); stage(run, 'signals', 'done');
    } catch (error) {
      if (!currentReview(run)) return;
      $('hybrid-heading').textContent = 'Signals are unavailable.'; $('hybrid-status').textContent = reviewError(error);
      stage(run, 'signals', 'error'); run.segments = validSegments(null, run.text); renderPassage(run);
    }
    hybridRunning = false;
    await capabilitiesReady;
    if (currentReview(run)) await runWritingReview(run);
  } finally {
    run.running = false; hybridRunning = false; simpleCoachRunning = false;
    if (!currentReview(run)) { $('review-progress').hidden = true; }
    refreshReviewControls();
  }
}
$('hybrid-run').addEventListener('click', startReview);
$('edit-view').addEventListener('click', () => { if (reviewRun) reviewRun.keepEditing = true; setPassageView(false, true); });
$('highlight-view').addEventListener('click', () => setPassageView(true));
$('undo-edit').addEventListener('click', () => {
  if (!undoEdit || passage.value !== undoEdit.after) return;
  passage.value = undoEdit.before; undoEdit = null; updateInput(); setPassageView(false, true);
  message('notice', 'Change undone. Review changes to refresh the signals.');
});
$('coach-run').addEventListener('click', async () => {
  if (reviewBusy() || !currentReview()) return;
  const run = reviewRun; run.running = true; run.includeCoach = true; refreshReviewControls();
  try { await runWritingReview(run); } finally { run.running = false; refreshReviewControls(); }
});
$('open-settings').addEventListener('click', () => { $('advanced-tools').open = true; });
const capabilitiesReady = loadCapabilities();
loadCorpus(); loadExamples(); updateInput();
