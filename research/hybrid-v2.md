# Hybrid v2: pretrained inference only

This branch adds an independent local hybrid path to the existing workbench.
It does not need the deleted Em Dash worktree, TF-IDF training outputs, MAGE
weights, a writing coach, an API key, or any additional training.

## Fresh setup

From the repository root on Windows, with Python 3.12 installed:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-hybrid.ps1
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Open http://127.0.0.1:8765, enter text and click **Review text**.
The separate `/static/legacy.html` research page retains **Analyze writing**, which
uses the historical MAGE/TF-IDF workflow and needs its own model artifacts. The new hybrid panel works
without those artifacts or a source corpus.

Setup installs pinned dependencies and downloads approximately 571 MB of
DistilBERT/ModernBERT artifacts. Inference is CPU by default and runs offline.
The first request verifies hashes and loads both models; later requests reuse
them. Submitted web text is neither saved nor sent to an external model service.

## Optional local writing coach

`scripts/setup-coach-cpu.ps1` installs the pinned Qwen3-0.6B compact profile
(about 1.52 GB of artifacts) and its guided-decoding dependencies. Restart with
`scripts/start.ps1`; it selects the installed compact profile unless an explicit
`TURINGTINT_COACH_PROFILE` is already set. On other launch paths, set
`TURINGTINT_COACH_PROFILE=compact` before starting the server.

**Review text** runs the hybrid check first, then the installed local coach.
It produces up to two anchored suggestions. Select a sentence in **Highlights**
or open a suggestion to see its signal, original wording and proposed edit
together. **Apply suggestion** changes that exact quote; **Undo change** restores
the previous text until a manual edit. Proposed wording is never applied
automatically. The model selects issue types and rewrites; explanation text
comes from fixed editorial guidance. Edited input clears stale feedback and
offers **Review changes**. Late responses cannot attach to an edited passage.
Writing suggestions can be switched off beside **Review text**. Missing coaching or a
failed review component does not hide the other component's results. A failed
coach request can be retried without rerunning detection.
The existing input, generation-time, numeric-protection and output-validation
limits still apply. A small local model can make poor suggestions, so this is
editing assistance, not fact verification or an authorship assessment.

Run `evaluation/check_coach_browser.py` after installation to test actual local
coach inference and its browser controls with synthetic wording. No paid API,
new training, or external submission of the input is required.

Verified on 2026-10-21: 181 unit/integration tests, 18 existing browser checks,
and the real hybrid browser smoke passed. The real compact-coach browser smoke
also passed: it returned a shorter rewrite retaining the synthetic fixture's
rain cause and postponement outcome, selected the quoted sentence, preserved
the editor text and cleared feedback after edits. The request took about 49
seconds on this CPU. Earlier prompt attempts misclassified the sentence or
dropped its cause; the final compact prompt includes a causal editing example.
This is a targeted smoke check, not an independent evaluation of editing quality.

The unified workspace was also checked with both actual model services in
Chromium, including Apply/Undo. `evaluation/check_review_browser.py` covers fifteen
deterministic browser scenarios: sequential results, exact Unicode offsets,
safe edits, late responses, isolated failures/retry, missing coaching, the visible
feedback toggle, copying/fallback, clear/restore, sample loading, keyboard sentence
navigation and a 320px layout without nested scrolling. All 18 historical browser
checks (on the separate research page) and the real hybrid
browser smoke passed. Desktop/mobile screenshots and receipts are stored under
ignored `outputs/hybrid/`. No model training or accuracy claims changed.

## Models and policy

| Member | Context limit | Output recipe |
|---|---:|---|
| `rasbt/ai-text-detector-distilbert` | 512 tokens | Published temperature, then class-1 softmax |
| `rasbt/ai-text-detector-modernbert` | 8,192 tokens | Published temperature, then class-1 softmax |
| `desklib/ai-text-detector-v1.01` (optional CLI) | 768 tokens | Masked mean pooling, linear head, sigmoid |

Revisions, file sizes and upstream Git-blob/LFS hashes are checked into
`detector_models/pretrained-pins.json`. Weights use safetensors, local-only loads,
and no remote Python code. ModernBERT's newer tokenizer metadata names
`TokenizersBackend`; the adapter reads its exact tokenizer JSON through the
installed Transformers 4 fast-tokenizer class, checks special token IDs and
maps the checkpoint's rotary bases into the older configuration fields.

Every selected member must succeed. The equal-weight mean is an experimental
index, not calibrated authorship probability. Spread of at least 0.25 flags
disagreement; this threshold is descriptive and unvalidated. The UI shows each
member's score and coverage. Different tokenizers and context limits mean that
long-text scores can cover different prefixes. No mixed-author or sentence-level
claim is produced.

DistilBERT and ModernBERT share training data; agreement is not independent
evidence. No improvement over individual detectors has been established.
The existing authorship capability remains unavailable.

## Sentence highlighting in the web checker

The web result also scores sentences/newline-separated passages independently.
Select a pastel highlight (or focus it and press Enter) to see each model's score.
Peach means both scores are at least 0.65; mint means both are at most 0.35.
Lavender indicates a spread of at least 0.25 or scores on opposite sides of 0.5.
Other scored sentences are pale yellow. These are unvalidated display thresholds,
not calibrated authorship decisions. The document score is still computed on the
whole input; sentence results do not alter it.

Fewer than 8 words remain unscored; fewer than 40 words receive a limited-context
warning. The checker processes at most 24 segments, each at most 1,200 characters,
and stops starting new sentence predictions after 25 seconds. An in-progress
prediction may finish after that budget. Failed or truncated sentences and the
unprocessed remainder stay neutral. Sentence boundaries are approximate; browser
line wrapping is not a stable linguistic unit. UTF-16 offsets preserve whitespace
and emoji in the original display. No mixed-authorship localization accuracy has
been established.

## CLI and optional Desklib

Input is JSONL with `id` and `text`; outputs omit the text. Existing output and
partial files are preserved. Use a new filename for each run:

```powershell
.venv/Scripts/python.exe -m detector_models.hybrid predict --input samples.jsonl --output outputs/hybrid/run-1.jsonl --limit 10
.venv/Scripts/python.exe -m detector_models.hybrid download --models desklib
.venv/Scripts/python.exe -m detector_models.hybrid predict --models distilbert modernbert desklib --input samples.jsonl --output outputs/hybrid/run-2.jsonl --limit 10
```

Desklib adds about 1.75 GB of artifacts plus runtime memory. Its custom head is
implemented locally; it is optional rather than silently downloaded by a request.
`--device cuda` is available when compatible CUDA PyTorch is installed.

## Checks and next work

```powershell
.venv/Scripts/python.exe -m unittest tests.test_hybrid -v
.venv/Scripts/python.exe evaluation/check_hybrid_smoke.py
.venv/Scripts/python.exe evaluation/check_hybrid_browser.py
```

The smoke uses synthetic short/long text and blocks socket connections during
real model loading and inference. It checks software behavior, not accuracy.
The historical full protocol needs separate corpora/models that are absent in a
fresh checkout; missing artifacts must not be interpreted as passing evidence.

Next: freeze independent student-writing and modern-generator evaluation data;
audit training overlap; compare all members and the fixed hybrid on the same
records using false-positive rate, precision, recall, F1, latency and coverage.
Do not choose weights or thresholds using the final test set.

### Verified in the rebuilt checkout (2026-10-20)

- Full unit/integration suite: 174 tests passed, zero skips. Test environment also
  installed the historical optional `lm-format-enforcer==0.11.3` dependency.
- Existing browser regression script: all 18 checks passed after acquiring the
  licensed 12-document reference seed. This corpus is not required by hybrid.
- Real default-pair CPU smoke passed with socket connections blocked. The long
  fixture used 512/1,277 DistilBERT tokens and 1,108/1,108 ModernBERT tokens;
  loading plus both short/long predictions took about 11 seconds on this machine.
- Actual Chromium + local server + real hybrid inference passed; rendered both
  scores, disabled concurrent analysis, cleared edited-text results and displayed
  a mocked 503 error. No external browser requests or JavaScript errors.
- Historical evaluation protocol exited 2: missing `data/authorship/aide`.
  The deleted research artifacts were not recreated or treated as passing gates.
- Desklib's adapter is included, but its optional full checkpoint was not downloaded
  or executed in this verification. Detection accuracy remains unmeasured.

Machine-readable smoke/browser receipts and the preserved initial DistilBERT
compatibility failure are under ignored `outputs/hybrid/` locally. The original
tokenizer emitted unsupported `token_type_ids`; the adapter now explicitly
disables them and a regression test checks this together with temperature scaling.

Upstream model cards: [DistilBERT](https://huggingface.co/rasbt/ai-text-detector-distilbert),
[ModernBERT](https://huggingface.co/rasbt/ai-text-detector-modernbert),
[Desklib](https://huggingface.co/desklib/ai-text-detector-v1.01).
