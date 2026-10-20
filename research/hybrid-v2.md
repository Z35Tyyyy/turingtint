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

Open http://127.0.0.1:8765, enter text and click **Check text**.
Under **More tools & sample texts**, **Analyze writing** still uses the historical MAGE/TF-IDF
workflow and needs its separate model artifacts. The new hybrid panel works
without those artifacts or a source corpus.

Setup installs pinned dependencies and downloads approximately 571 MB of
DistilBERT/ModernBERT artifacts. Inference is CPU by default and runs offline.
The first request verifies hashes and loads both models; later requests reuse
them. Submitted web text is neither saved nor sent to an external model service.

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
