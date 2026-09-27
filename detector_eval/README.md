# Local detector experiment

This phase compares a trained text-feature baseline and a pinned MAGE checkpoint.
It is an engineering experiment, not validation of English student detection.
The web application continues returning unavailable authorship scores.

## Reproduce on a fresh checkout

Python 3.12 was used. The optional research dependencies are separate from the
web app. Install the PyTorch wheel for your hardware first; this run used
PyTorch 2.6.0+cu124 on a 6 GB RTX 3050 Laptop GPU.

```powershell
.venv/Scripts/python.exe -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
.venv/Scripts/python.exe -m pip install -r requirements-ml.txt
.venv/Scripts/python.exe -m authorship_data
.venv/Scripts/python.exe -m authorship_data.hc3
.venv/Scripts/python.exe -m detector_eval.experiment freeze --input data/authorship/hc3-wiki --output data/authorship/experiments/hc3-v1
.venv/Scripts/python.exe -m detector_eval.experiment freeze --input data/authorship/aide --output data/authorship/experiments/aide-v1 --external
.venv/Scripts/python.exe -m detector_eval.experiment baseline --frozen data/authorship/experiments/hc3-v1 --external data/authorship/experiments/aide-v1 --output outputs/experiments/tfidf-v1
.venv/Scripts/python.exe -m detector_models download
.venv/Scripts/python.exe -m detector_models predict --input data/authorship/experiments/hc3-v1/records.jsonl --output outputs/experiments/mage-hc3-v1/predictions.jsonl --device cuda --max-tokens 512 --batch-size 1
.venv/Scripts/python.exe -m detector_models predict --input data/authorship/experiments/aide-v1/records.jsonl --output outputs/experiments/mage-aide-v1/predictions.jsonl --device cuda --max-tokens 512 --batch-size 1
.venv/Scripts/python.exe -m detector_eval.reports
.venv/Scripts/python.exe evaluation/check_authorship.py
```

Freeze and prediction commands refuse to overwrite completed experiments. Use
new versioned directories for a new experiment; changing paths also requires a
reviewed report/protocol update. Acquisition records its actual fetched revision;
compare acquisition and frozen-record hashes to the committed result before
claiming an exact reproduction. Raw texts and checkpoint files stay out of Git.
The report contains aggregate counts, metrics and hashes, not essay text.

## Method fixed before scores

HC3 `wiki_csai` alone has documented Wikipedia source licensing. Exactly one
80–250-word excerpt is selected per usable answer. Prefer the first natural
paragraph in that range; otherwise keep a short whole answer or the first 250
words, explicitly marking that it can end mid-sentence. Shorter answers are
excluded. This is not a sentence-localization benchmark.

Keep shared questions, document families and exact normalized text together.
Union the original cross-question duplicate relations, including removed bridge
nodes, before assigning stable-hash components to 60% train, 20% calibration and
20% test. Realized counts are 882/293/289. The entire AIDE set stays external.
Unknown author identity remains unknown; unique essay IDs do not prove authors
are independent. Near-duplicate independence is not established.

The baseline learns word 1–2-grams and character 3–5-grams on training text only,
with fixed feature limits and balanced logistic regression (C=1). No source
questions, IDs, labels or corpus metadata become features. No parameter search
uses test results. MAGE is a separately downloaded pretrained checkpoint; its
possible training overlap prevents interpreting its HC3 result as independent.

Scores use the AI-positive orientation. Select two decision thresholds using
calibration data only, limiting empirical false-AI and false-human family rates
to 1%. Scores between the boundaries are uncertain. Also report the predeclared
0.5 score rule as a diagnostic. It is not MAGE's upstream logit decision rule.
Neither method turns softmax/logistic outputs into calibrated probabilities.

## Evidence and conservative gates

Report false-AI rate over **all human examples**, AI recall with abstentions as
misses, class-specific coverage, precision, Brier score, AUROC, length subgroups
and source-family counts. Also report false-AI rate among answered humans so
abstention cannot conceal poor conclusive decisions. Wilson bounds are
separately one-sided 95% bounds and assume independent source families; they
are not evidence that this dataset satisfies that assumption.

The metric library requires verified independent families, sufficient support,
a low upper false-positive bound, recall/coverage, and support/recall for **each**
unseen generator before approving its narrow configured claim. The experiment
adds an unconditional product block: HC3 is outside the target population,
AIDE contains only three AI essays, and target contemporary-generator evidence
is absent. It cannot establish mixed authorship, sentence boundaries or plagiarism.

`check_authorship.py` recomputes metrics from original frozen inputs and saved
predictions. It verifies text binding, pinned model files and artifact receipts;
it does not trust a previously written `product_approved` flag. Changed or missing
artifacts fail the check. Valid but insufficient evidence returns `blocked`.
