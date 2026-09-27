'use strict';
const $ = (id) => document.getElementById(id);
let revision = 0;
let activeRequest = null;
let lastReport = null;
let researchRequest = null;
let researchSequence = 0;
let hasResearchResult = false;
let researchNeedsRetest = false;
const text = $('passage');

function node(tag, value, className) {
  const element = document.createElement(tag);
  if (value !== undefined) element.textContent = value;
  if (className) element.className = className;
  return element;
}
function notice(message) { $('notice').textContent = message; $('notice').hidden = !message; }
function researchNotice(message) { $('research-notice').textContent = message; $('research-notice').hidden = !message; }
function updateInput() {
  revision++;
  if (activeRequest) { activeRequest.abort(); activeRequest = null; }
  const invalidateResearch = Boolean(researchRequest) || hasResearchResult;
  researchNeedsRetest = researchNeedsRetest || invalidateResearch;
  if (researchRequest) { researchRequest.abort(); researchRequest = null; }
  hasResearchResult = false;
  $('research-result').hidden = true;
  $('research-score').textContent = '';
  const words = text.value.trim() ? text.value.trim().split(/\s+/u).length : 0;
  $('word-count').textContent = `${words.toLocaleString()} words`;
  $('analyze').disabled = !words;
  $('research-analyze').disabled = !words;
  $('research-analyze').textContent = 'Test experimental detector';
  $('research').setAttribute('aria-busy', 'false');
  researchNotice(researchNeedsRetest ? 'The passage changed. Test again to inspect the updated text.' : '');
  $('analyze').replaceChildren(document.createTextNode('Analyze passage '), node('span', '↗'));
  if (lastReport) { lastReport = null; $('results').hidden = true; notice('The passage changed. Analyze again for an updated report.'); }
}
text.addEventListener('input', updateInput);

function renderResearch(result, submitted, requestId) {
  const countFields = ['input_characters', 'input_words', 'original_tokens', 'input_tokens', 'max_tokens'];
  const valid = result.request_id === requestId && result.status === 'experimental' && result.product_approved === false
    && result.score_kind === 'uncalibrated_softmax_class_0'
    && typeof result.score_ai === 'number' && Number.isFinite(result.score_ai) && result.score_ai >= 0 && result.score_ai <= 1
    && countFields.every(field => Number.isInteger(result[field]) && result[field] >= 0)
    && result.input_characters === Array.from(submitted).length
    && result.input_tokens <= result.original_tokens && result.input_tokens <= result.max_tokens
    && typeof result.truncated === 'boolean';
  if (!valid) throw new Error('The experimental result did not match the submitted passage. Please test again.');
  $('research-score').textContent = result.score_ai.toPrecision(10);
  $('research-characters').textContent = result.input_characters.toLocaleString();
  $('research-words').textContent = result.input_words.toLocaleString();
  $('research-original-tokens').textContent = result.original_tokens.toLocaleString();
  $('research-input-tokens').textContent = `${result.input_tokens.toLocaleString()} / ${result.max_tokens.toLocaleString()} maximum`;
  $('research-truncation').hidden = !result.truncated;
  $('research-truncation').textContent = result.truncated
    ? `Only the first ${result.input_tokens.toLocaleString()} of ${result.original_tokens.toLocaleString()} tokens were analyzed. The score does not cover the remaining text.` : '';
  const elapsed = Number.isFinite(result.elapsed_ms) ? `${(result.elapsed_ms / 1000).toFixed(2)} seconds` : 'Time unavailable';
  $('research-runtime').textContent = `Analyzed on this machine · ${elapsed}`;
  $('research-model').textContent = `${result.model_id || 'Local model'} · revision ${result.model_revision || 'unavailable'} · ${result.device || 'local device'}`;
  const limitations = $('research-limitations'); limitations.replaceChildren();
  if (Array.isArray(result.limitations)) result.limitations.filter(item => typeof item === 'string').forEach(item => limitations.append(node('li', item)));
  hasResearchResult = true;
  $('research-result').hidden = false;
  $('research-result').scrollIntoView({behavior: 'smooth', block: 'nearest'});
}

$('research-analyze').addEventListener('click', async () => {
  if (!text.value.trim() || researchRequest) return;
  const current = revision;
  const submitted = text.value;
  const requestId = `research-${Date.now()}-${++researchSequence}`;
  const controller = new AbortController(); researchRequest = controller;
  researchNeedsRetest = false;
  hasResearchResult = false; $('research-result').hidden = true;
  $('research-analyze').disabled = true; $('research-analyze').textContent = 'Testing locally…';
  $('research').setAttribute('aria-busy', 'true');
  researchNotice('Running the experimental local model. The first test may take a few seconds to load.');
  const timeout = setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch('/api/research/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: submitted, request_id: requestId}), signal: controller.signal});
    if (!response.ok) {
      let detail = 'The experimental detector could not complete this test.';
      try { const error = await response.json(); if (typeof error.detail === 'string') detail = error.detail;
        else if (Array.isArray(error.detail)) detail = error.detail.map(item => item.msg).filter(Boolean).join(' '); } catch (_) {}
      throw new Error(detail);
    }
    const result = await response.json();
    if (current !== revision || researchRequest !== controller) return;
    renderResearch(result, submitted, requestId);
    researchNotice('');
  } catch (error) {
    if (current === revision && researchRequest === controller) {
      researchNotice(error.name === 'AbortError' ? 'The experimental test timed out. No score was produced; the local model may still be running.' : error.message);
    }
  } finally {
    clearTimeout(timeout);
    if (current === revision && researchRequest === controller) {
      researchRequest = null;
      $('research-analyze').disabled = !text.value.trim();
      $('research-analyze').textContent = 'Test experimental detector';
      $('research').setAttribute('aria-busy', 'false');
    }
  }
});

async function loadCorpus() {
  try {
    const response = await fetch('/api/corpus');
    if (!response.ok) throw new Error('Library unavailable');
    const corpus = await response.json();
    const count = Number(corpus.document_count || 0);
    $('corpus-count').textContent = `${count.toLocaleString()} source${count === 1 ? '' : 's'}`;
    $('corpus-detail').textContent = count ? 'Installed on this machine' : 'No reference documents installed';
    $('source-state').textContent = count ? 'Available locally' : 'Library is empty';
    $('example').disabled = !count;
  } catch (_) {
    $('corpus-count').textContent = 'Unavailable';
    $('corpus-detail').textContent = 'Could not read the local library';
    $('source-state').textContent = 'Unavailable';
    $('example').disabled = true;
  }
}

function safeSourceLink(url) {
  try { const parsed = new URL(url); return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : null; }
  catch (_) { return null; }
}

function renderAnnotated(passage, matches) {
  const view = $('annotated-text'); view.replaceChildren();
  const valid = matches.filter(m => Number.isInteger(m.query_start) && Number.isInteger(m.query_end) && m.query_start >= 0 && m.query_end <= passage.length && m.query_end > m.query_start);
  const boundaries = [...new Set([0, passage.length, ...valid.flatMap(m => [m.query_start, m.query_end])])].sort((a,b) => a-b);
  for (let i=0; i<boundaries.length-1; i++) {
    const start = boundaries[i], end = boundaries[i+1];
    const covering = valid.filter(m => m.query_start <= start && m.query_end >= end);
    const content = passage.slice(start,end);
    if (!covering.length) { view.append(document.createTextNode(content)); continue; }
    const mark = node('mark', content); mark.tabIndex = 0; mark.setAttribute('role','button');
    mark.setAttribute('aria-label', `Matched passage; ${covering.length} source match${covering.length === 1 ? '' : 'es'}. Show evidence.`);
    const activate = () => { const card = document.getElementById(`source-${matches.indexOf(covering[0])}`); if(card){card.focus();card.scrollIntoView({behavior:'smooth',block:'nearest'});} };
    mark.addEventListener('click', activate);
    mark.addEventListener('keydown', e => { if(['Enter',' '].includes(e.key)){e.preventDefault();activate();} });
    view.append(mark);
  }
}

function renderReport(report) {
  lastReport = report;
  const component = report.source_matching || {};
  const matches = component.matches || [];
  const warnings = Array.isArray(component.warnings) ? component.warnings.filter(w => typeof w === 'string') : [];
  const incomplete = component.status !== 'complete';
  $('component-warning').hidden = !incomplete && !warnings.length;
  $('component-warning').textContent = [incomplete ? 'Source analysis is incomplete. Matches below cover only the portion successfully checked.' : '', ...warnings].filter(Boolean).join(' ');
  renderAnnotated(report.text, matches);
  $('match-count').textContent = String(matches.length);
  const cards = $('source-cards'); cards.replaceChildren();
  matches.forEach((match,index) => {
    const source = match.source || {};
    const card = node('article', undefined, 'source-card'); card.id = `source-${index}`; card.tabIndex = -1;
    card.append(node('span', `${String(index+1).padStart(2,'0')} / ${match.kind === 'near_exact_text_overlap' ? 'CLOSE WORDING' : 'TEXT OVERLAP'}`, 'source-number'));
    card.append(node('h4',source.title || 'Reference document'));
    const url = safeSourceLink(source.url);
    if(url) { const a = node('a','Open source ↗'); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; card.append(a); }
    card.append(node('blockquote',match.source_text || ''));
    const licenseURL = safeSourceLink(source.license_url);
    if (licenseURL) { const a = node('a', source.license_id || 'Source license', 'license'); a.href=licenseURL; a.target='_blank'; a.rel='noopener noreferrer'; card.append(a); }
    else card.append(node('span',source.license_id || 'License recorded in corpus', 'license'));
    if(source.attribution) { const details=node('details'); details.append(node('summary','Attribution'),node('p',source.attribution)); card.append(details); }
    cards.append(card);
  });
  if(!matches.length) cards.append(node('p', component.status === 'complete' ? 'No source match found in the local corpus. Sources outside this library were not searched.' : 'Source analysis is incomplete or unavailable. This is not a zero-overlap result.', 'empty-evidence'));
  $('report-summary').textContent = typeof component.summary === 'string' ? component.summary : 'These matches identify shared wording in the local corpus. Check quotations and attribution before drawing conclusions.';
  const suggestions = report.suggestions || [];
  const list = $('suggestions'); list.replaceChildren();
  suggestions.forEach(s => { const card=node('article',undefined,'suggestion'); card.append(node('h4',s.title),node('p',s.reason),node('p',s.action)); list.append(card); });
  $('suggestions-panel').hidden = !suggestions.length;
  $('results').hidden = false;
  $('results').scrollIntoView({behavior:'smooth',block:'start'});
}

$('analyze').addEventListener('click', async () => {
  if(!text.value.trim()) return;
  const current = revision;
  const controller = new AbortController(); activeRequest = controller;
  const submitted = text.value;
  $('analyze').disabled = true; $('analyze').textContent = 'Analyzing…'; notice('');
  const timeout = setTimeout(() => controller.abort(), 60000);
  try {
    const response = await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:submitted}),signal:controller.signal});
    if(!response.ok) {
      let detail='Analysis failed. Please try again.';
      try { const error=await response.json(); if(typeof error.detail==='string') detail=error.detail; else if(Array.isArray(error.detail)) detail=error.detail.map(item=>item.msg).filter(Boolean).join(' '); } catch (_) {}
      throw new Error(detail);
    }
    const report = await response.json();
    if(current !== revision) return;
    if(report.text !== submitted || report.offset_encoding !== 'utf-16') throw new Error('The report did not match the submitted passage. Please analyze again.');
    renderReport(report);
  } catch(error) {
    if(current === revision) notice(error.name === 'AbortError' ? 'Analysis timed out. No conclusion was produced.' : error.message);
  } finally {
    clearTimeout(timeout);
    if(current === revision) { activeRequest=null; $('analyze').disabled = !text.value.trim(); $('analyze').replaceChildren(document.createTextNode('Analyze passage '),node('span','↗')); }
  }
});

$('example').addEventListener('click',async()=>{
  const current = revision; $('example').disabled = true;
  try {
    const response=await fetch('/api/example'); if(!response.ok) throw new Error('No reference example is available yet.');
    const example=await response.json();
    if(current !== revision) return;
    if(!example.text) throw new Error('No reference example is available yet.');
    text.value=example.text; updateInput(); notice('This passage comes from the installed reference library. It demonstrates source matching; it is not an AI-detection test.'); text.focus();
  } catch(error){notice(error.message);} finally{$('example').disabled=false;}
});
$('export').addEventListener('click',()=>{
  if(!lastReport) return;
  const blob = new Blob([JSON.stringify(lastReport,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob), link=document.createElement('a');link.href=url;link.download='turingtint-report.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
loadCorpus();
