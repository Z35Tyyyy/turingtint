'use strict';
const $ = id => document.getElementById(id);
const passage = $('passage');
let revision = 0;
let sequence = 0;
let capabilities = null;
const SAMPLE = 'Due to the fact that the weather was rainy, the event was postponed until a later date in the future. The organizers contacted everyone who had registered and offered a choice of two new dates. This gave participants time to adjust their plans.';

function node(tag, value, className) {
  const element = document.createElement(tag);
  if (value !== undefined && value !== null) element.textContent = String(value);
  if (className) element.className = className;
  return element;
}
function message(id, value) { $(id).textContent = value || ''; $(id).hidden = !value; }
function strings(values) { return Array.isArray(values) ? values.filter(item => typeof item === 'string') : []; }
function rawScore(value) { return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1 ? String(value) : 'Unavailable'; }
function validRange(value, text, field = 'text') { return value && Number.isInteger(value.start) && Number.isInteger(value.end) && value.start >= 0 && value.end > value.start && value.end <= text.length && typeof value[field] === 'string' && text.slice(value.start, value.end) === value[field]; }
function textCounts(text) { return {characters: Array.from(text).length, words: text.trim() ? text.trim().split(/\s+/u).length : 0}; }
function updateInput(options = {}) {
  revision++;
  const {words, characters} = textCounts(passage.value);
  $('word-count').textContent = `${words.toLocaleString()} words · ${characters.toLocaleString()} characters`;
  $('copy-status').textContent = ''; $('copy-text').textContent = 'Copy text';
  message('notice', ''); reviewInputChanged(options);
}
async function loadCapabilities() {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch('/api/workbench/status', {signal: controller.signal});
    if (!response.ok) throw new Error('Status unavailable');
    capabilities = await response.json();
  } catch (_) { capabilities = null; }
  finally { clearTimeout(timer); refreshReviewControls(); }
}
passage.addEventListener('input', updateInput);
