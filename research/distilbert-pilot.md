# DistilBERT continuation pilot

The first pilot uses the public HC3 English Wikipedia CS/AI subset and continues
training the pinned `rasbt/ai-text-detector-distilbert` checkpoint. It produces a
separate model and comparison report; it does not replace the app's detector.

Kaggle supplies a weekly free GPU quota. Check the account's remaining allowance
before starting. Hugging Face Jobs use a separate compute-credit balance; a Hub
token does not grant Kaggle hours. This notebook needs no token because it only
downloads public artifacts and saves its checkpoint in private notebook outputs.

The source acquisition preserves revision, checksum, attribution and license
receipts. Only `wiki_csai` is admitted. One 80–250-word excerpt is taken per
usable answer. Related questions, duplicate documents and linked excerpts stay
together. Existing 60/20/20 train/calibration/test family assignments are retained;
one sixth of training families becomes validation, giving approximately
50/10/20/20. Test results do not select checkpoints, temperatures or thresholds.

The initial local freeze contains 760 training, 122 validation, 293 calibration
and 289 test excerpts. Of 1,613 admitted answers, 149 were too short for the
existing paragraph policy. Actual training uses at most 512 tokens per excerpt.

Parameters: two epochs, AdamW, learning rate `2e-5`, batch size 8, gradient
accumulation 4, weight decay `.01`, warmup `.06`, gradient norm limit 1, seed 42.
The best validation loss selects the exported checkpoint. GPU mixed precision
uses BF16 when supported, otherwise FP16. The training loop has a 900-second
deadline; the notebook command also has a 1,200-second subprocess timeout.

The report compares the original checkpoint with its published temperature,
the original recalibrated on this subset, and the tuned checkpoint recalibrated
on this subset. It includes accuracy, precision, recall, F1, human false-positive
rate, and separate abstaining-threshold metrics. The latter must report coverage.
Exported safetensors are reloaded and their predictions checked before completion.

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements-training.txt
.venv/Scripts/python.exe -m authorship_data.hc3 --output data/authorship/hc3-wiki-pilot-v1
.venv/Scripts/python.exe -m detector_eval.finetune freeze --source data/authorship/hc3-wiki-pilot-v1 --output outputs/training/hc3-distilbert-v1-frozen
```

Use fresh directories for each experiment; existing frozen data and runs cannot
be overwritten. `scripts/build_training_notebook.py` creates an importable Kaggle
notebook pinned to a full repository commit and the frozen-record checksum:

```powershell
.venv/Scripts/python.exe scripts/build_training_notebook.py --revision <full-commit> --frozen-manifest outputs/training/hc3-distilbert-v1-frozen/manifest.json --output outputs/training/distilbert-hc3-pilot.ipynb
```

On Kaggle, enable Internet and a T4 accelerator and run the notebook. Keep the
notebook private. Saved outputs include the checkpoint, report, predictions,
source attribution/receipts, and frozen split. The bootstrap installs compatible
training libraries while retaining the runtime's CUDA-enabled PyTorch.

This is a small engineering experiment on older ChatGPT answers, not independent
evidence of current-generator, sentence-level, mixed-authorship or essay accuracy.
Overlap with the original detector's training data is unverified. A better HC3
score is insufficient to deploy the tuned checkpoint or adjust the hybrid weights.

Sources: [HC3](https://huggingface.co/datasets/Hello-SimpleAI/HC3),
[Kaggle GPU quota](https://www.kaggle.com/docs/efficient-gpu-usage),
[Hugging Face Jobs pricing](https://huggingface.co/docs/hub/jobs-pricing).
