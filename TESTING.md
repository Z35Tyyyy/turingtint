# Test the local writing workbench

Open **http://127.0.0.1:8765**. If an older page is open, refresh with **Ctrl+F5**.

1. Choose a case beside **Load case**, then load it. The description identifies
   where the text came from; those labels are not sent to either model.
2. Uncheck **Include writing feedback** and click **Analyze writing** for a fast
   detector test. Inspect the overall leaning, highlighted context blocks and
   individual model results. MAGE determines the primary result; TF-IDF supplies
   a secondary diagnostic. Short, uncertain, truncated or unscored text has limits.
3. Load **Revision practice: clarity and evidence**, enable writing feedback, and
   analyze. The local language model suggests up to two edits with reasons.
   Click **Review this change** to see
   the exact original wording and proposed replacement before applying it.
4. Click **Use this revision**, disable feedback for a faster rerun, and analyze
   again. The
   comparison keeps the original and revised wording counts and model signals.
   A change in score is observable behavior; it does not establish authorship.

The six cases include a paired HC3 human/ChatGPT example, a student essay labeled
human by AIDE, a synthetic human-plus-AI concatenation, a known assistant-written
challenge, and a revision exercise. The first four have source and license
attribution in the interface. The synthetic combination is not a real human
editing workflow. A model error on any case remains visible. These examples
demonstrate behavior and were selected without choosing passages by model scores.

Try your own complete English paragraph of roughly 100–220 words after the examples.
Paste it directly in the page; there is no PowerShell input step. Longer writing is
scored in bounded context blocks, with analyzed and unscored coverage reported.

If the application is stopped, use this PowerShell command sequence:

```powershell
Set-Location -LiteralPath "C:\Users\Asus\emdash\worktrees\turingtint\emdash\model-training-w5xd0"
.\.venv\Scripts\python.exe -m turingtint --port 8765
```

Local inference requires no API key. The installed model stays on this machine.
The API provider remains an explicit optional choice and requires a separately
configured key and model.

Complete sentences containing digits are protected from automatic coach rewrites;
edit numerical claims yourself after checking the evidence. Coach status summaries
report the number of suggestions rather than retelling your results.

The local reference panel remains a separate wording
comparison against its small installed library.

Measured classifier outcomes and regressions are in
[the candidate report](research/candidate-diagnostic.md). Coach iteration results
and semantic failures are recorded in [the coach notes](research/llm-review.md).
The real-browser run is distinct from the browser tests that use mock predictions.
Neither is a population-level accuracy benchmark.

## Actual detector smoke results

These are the six fixed cases as observed through the local API on this machine.
They were selected before seeing these predictions. The test intentionally keeps
the failures; it is too small, and its provenance too limited, to measure accuracy.

| Case | Observed primary result |
|---|---|
| Published human explanation | Human-leaning |
| Documented ChatGPT explanation | AI-leaning |
| Human-labeled student writing | Human-leaning |
| Constructed human + AI passage | Inconclusive overall; three blocks human/human/AI-leaning |
| AI-generated challenge passage | Inconclusive; known AI missed |
| Synthetic revision practice | Human-leaning; false human signal |

First detector request took 3.96 seconds including initialization; subsequent
requests took 0.08–0.22 seconds. The coach runs separately and takes longer.
The full [API receipt](evaluation/reviews/live-detector-six-cases.json) includes
input hashes, block results and coverage metadata.

## Actual revision flow

The real browser run produced this useful opening edit:

> In my personal opinion, I think that students should plan ahead in advance before they begin studying.

became:

> Students should plan ahead before starting to study.

The full passage fell from 88 to 79 words, below the detector's 80-word minimum.
The comparison therefore displays **Not comparable** and explains the length
limit. That outcome is not evidence that the rewrite became more AI-like.

The coach also suggested softening a claim about online learning. That suggestion
still needs evidence: the supplied sleep survey does not establish online-learning
benefits. The preview lets you accept the useful opening edit without applying
the second suggestion. Model-selected issue types and rewritten meaning require
review; the accompanying explanations use openly identified fixed editorial guidance.

Six coach iterations are preserved under `evaluation/reviews/`. On the final
eight-case development suite all requests completed, with four fully appropriate
responses, one partial improvement, and three missed edits in manual review.
That is a measured limitation, not a general writing-quality accuracy score.
