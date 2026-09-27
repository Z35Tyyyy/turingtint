# Candidate iteration: MAGE margin and primary-model policy

The new experimental policy uses MAGE's saved logit margin in double precision
and keeps TF-IDF as a separate diagnostic. It removes a major coverage problem
and recovers decisions lost by rounding, but increases false AI flags on the
external student set. No detector weights were retrained, no frozen predictions
were changed, and no new inference was used for these results.

Reproduce with:

```powershell
.\.venv\Scripts\python.exe -m detector_eval.candidate freeze
.\.venv\Scripts\python.exe -m detector_eval.candidate diagnose
```

The first command records calibration selection before the second evaluates
test/external policies. Re-running requires the same selection digest:
`3078a7ad126af7ee9474a27da1663713f6061816c10df439ae633be3a839f62a`.
Results and source hashes are in `evaluation/results/candidate-diagnostic.json`.

## What was wrong

The mandatory-agreement policy lets a weak secondary detector suppress a useful
primary opinion. On HC3 calibration, requiring agreement answered only 151/293
excerpts, versus 198/293 for the existing MAGE policy. On the previously observed
AIDE diagnostic, the HC3-trained baseline answers only 186/1378 excerpts, and
requiring its agreement reduces the ensemble to 108/1378. The two models are not
independent authorities whose agreement certifies authorship.

The score representation also matters. The old adapter converts two logits to a
float32 softmax close to 1.0. Only 139 distinct calibration scores survive that
rounding, while the saved logit margin retains 150. A cluster near the AI cutoff
contains both human and AI records; rounded ties force the calibrated threshold
to exclude additional AI examples. Applying a stable Python float64 sigmoid to
`raw_logits[0] - raw_logits[1]` preserves more ordering. The largest difference
from the old softmax over all 2,842 saved predictions is only `8.61e-8`, yet these
small differences change threshold decisions. This is score computation, not a
calibrated probability or an increase in model knowledge.

The two assistant-written examples remain diagnostic failures to inspect. The
797-character urban-green-space sample had MAGE score `0.9999829530715942` and
TF-IDF score `0.43704189440074476`, both inside their old uncertainty intervals,
with full input coverage. The earlier 1,132-character assistant sample's reported
MAGE score was `0.9999871253967285`, also below the old AI cutoff. Mandatory
agreement was not the sole cause of those abstentions. They were not used to
choose thresholds; this repair must not be described as making every known AI
example detectable. The original urban challenge is retained for live retesting.

## Calibration-only selection

Three MAGE representations were compared on the existing HC3 calibration split:
126 human and 167 AI excerpts. For each, the existing selection routine applies
separate empirical 1% caps for human-to-AI and AI-to-human errors. These caps are
not confidence guarantees. The predeclared ranking is highest AI recall, then
coverage, with deterministic ties preferring margin, class-0 logit, then rounded
softmax. Only the MAGE score representation is selected here; TF-IDF is retained
for comparison, not as a candidate primary model.

| Calibration representation | AI caught /167 | Human false AI /126 | AI false human /167 | Answered /293 |
|---|---:|---:|---:|---:|
| Existing float32 softmax | 105 | 1 | 1 | 198 |
| AI-class logit, monotone sigmoid | 110 | 1 | 1 | 203 |
| Logit margin, float64 sigmoid **selected** | 122 | 1 | 1 | 215 |

Frozen native-margin cutoffs are `human_max = 9.19921875` and
`ai_min = 11.2890625`, inclusive. Their float64 sigmoid equivalents are
`0.9998988918541782` and `0.9999874911605668`. Between them, the primary result is
inconclusive. The runtime loader verifies source prediction/model/frozen-record
hashes, the score recipe, and the complete recalculated calibration selection.

The choice of a pretrained primary detector with a non-veto secondary diagnostic
also uses the already known target-domain weakness of the HC3-only baseline.
That engineering choice is exploratory development; it is not a fresh blind
model-selection experiment. Test and external outcomes were not used to change
the newly frozen MAGE representation or cutoffs.

## Retrospective outcomes after the freeze

| HC3 test, 123 human +166 AI | AI caught | Human false AI | AI false human | Coverage |
|---|---:|---:|---:|---:|
| Old mandatory agreement | 97/166 (58.4%) | 0/123 | 2/166 | 164/289 (56.7%) |
| Original MAGE only | 113/166 (68.1%) | 1/123 | 3/166 | 204/289 (70.6%) |
| TF-IDF only | 124/166 (74.7%) | 0/123 | 2/166 | 217/289 (75.1%) |
| Frozen margin-primary policy | 124/166 (74.7%) | 1/123 | 3/166 | 215/289 (74.4%) |

| AIDE, 1,375 human +3 AI | Human false AI | Human false-AI rate | Answered-human false-AI rate | Coverage |
|---|---:|---:|---:|---:|
| Old mandatory agreement | 3/1375 | 0.22% | 2.78% | 108/1378 (7.8%) |
| Original MAGE only | 27/1375 | 1.96% | 2.45% | 1106/1378 (80.3%) |
| TF-IDF only | 67/1375 | 4.87% | 36.02% | 186/1378 (13.5%) |
| Frozen margin-primary policy | 38/1375 | 2.76% | 3.41% | 1117/1378 (81.1%) |

The new margin policy catches 1/3 AIDE AI examples, calls 1 human, and abstains on
1; three cases cannot establish student-domain AI recall. The increased human
false flags are an explicit regression against the original MAGE-only policy.
All artifacts were already observed, HC3 may overlap MAGE pretraining, and AIDE
does not establish independent author groups. These results do not satisfy the
existing scientific release gates.

The runtime policy uses MAGE for block decisions and keeps the secondary opinion
visible without veto or fallback. Missing/uncertain/truncated MAGE output remains
inconclusive. Short blocks and unscored remainders retain their limits, and a
whole-passage leaning still requires consistent, complete primary block results.
Cross-model disagreement and changing block results never imply a mixed class.

## Upstream recipe and the next controlled experiment

The immutable upstream README recommends preprocessing; deployment removes line
breaks, normalizes punctuation/Unicode, strips URLs/emails/phone numbers, and
restricts characters. Its published decision rule thresholds **AI-class logit
greater than 3.08583984375**, not two-class softmax at 0.5. Our existing artifacts
use raw text, a 512-token cap, and their separately frozen calibration thresholds.
See the pinned [deployment recipe](https://raw.githubusercontent.com/yafuly/MAGE/6d11f851184b9f04166f952ddc1f47727f36710f/deployment/utils.py)
and [model instructions](https://raw.githubusercontent.com/yafuly/MAGE/6d11f851184b9f04166f952ddc1f47727f36710f/README.md).

Blindly applying that upstream raw-logit cutoff to our raw-text predictions is
unsuitable: it flags 56/126 calibration humans, 48/123 test humans, and 479/1375
AIDE humans. Cleaning and cutoff cannot be assumed interchangeable.

The next stronger route is a **separate versioned preprocessing experiment**:
install and pin the documented cleaning dependencies, port/review the immutable
recipe, score only the 293 calibration excerpts first with raw and cleaned text,
and freeze a selection before evaluating reserved outcomes. Preserve original
text and offsets in the UI; cleaned detector text is a derived model input with
its own hash. Only after that controlled comparison should an untouched modern
student/academic human-plus-AI set be used to assess generalization. This report
does not claim cleaning already improves results. Any GPU run must be scheduled
with the live coaching server; no such run was launched for this iteration.
