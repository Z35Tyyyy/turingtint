# MAGE research baseline

This adapter evaluates a pinned public detector locally. It does not activate AI
labels in the web application and does not establish accuracy for student writing.

The official [MAGE checkpoint](https://huggingface.co/yaful/MAGE) declares Apache
2.0. The pinned model revision is `0d82ca0fdf6ebef5babb813cc11bd8eb2552c846`.
The [official deployment source](https://github.com/yafuly/MAGE/blob/6d11f851184b9f04166f952ddc1f47727f36710f/deployment/utils.py)
explicitly identifies class 0 as machine-generated and class 1 as human-written.

The upstream repository provides a roughly 595 MB PyTorch checkpoint without
safetensors. The acquisition command verifies its published SHA-256, requires
PyTorch 2.6 or newer, loads it with `weights_only=True` and converts the tensor
dictionary to safetensors. Subsequent inference accepts safetensors only, sets
`local_files_only=True` and `trust_remote_code=False`, and verifies artifact hashes.
Upstream Python source is stored as a `.txt` audit artifact and never imported.
Every required artifact has a hash pinned in the adapter independently of the
mutable manifest. Converted safetensors receive a canonical JSON header and an
independently pinned hash; an altered manifest cannot relabel arbitrary local
weights as the official checkpoint. Repeated conversion produced identical bytes.

The PyTorch version floor addresses the
[official weights-only loading advisory](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6).
Restricted loading reduces execution risks but should not be treated as proof
that arbitrary third-party files are harmless. This adapter accepts one pinned,
hash-checked official checkpoint only.

```powershell
.venv/Scripts/python.exe -m detector_models download
.venv/Scripts/python.exe -m detector_models predict --input data/authorship/aide/records.jsonl --ids outputs/run/ids.txt --output outputs/run/mage.jsonl --device cuda --max-tokens 1024
```

Input records need `id` and `text`; other fields are ignored. IDs can be a JSON
array or one ID per line. Selection and held-out evaluation protocols belong to
the evaluation runner, not this model adapter. Output records contain IDs and
predictions without copying essay text or using its labels. Existing outputs are
never silently overwritten.

`score_ai` is the **uncalibrated softmax output for class 0**, not an estimated
percentage of AI-written text. Raw logits, original token counts, truncation,
preprocessing, model revision, device and numeric dtype are recorded. The maximum
context is explicitly capped at 4,096 tokens; default runs use 1,024. CUDA uses
float16 and CPU uses float32. These choices must be held fixed within comparisons.

The initial `raw_text_v1` variant passes original text directly to the tokenizer.
It intentionally does **not** reproduce upstream's recommended aggressive text
cleaning, and it does not reuse upstream's logit threshold. Report it as a raw-text
MAGE variant. Compare preprocessing choices on development data before fixing a
final evaluation protocol. Do not tune these settings using final test outcomes.

Dependencies used for the initial GPU run: PyTorch 2.6.0+cu124, Transformers
4.56.2, safetensors 0.8.0. The weights occupy approximately 595 MB in each of
upstream and converted forms; the model download was 598,180,161 bytes.
