# Experimental UI independent audit

Reviewer: `iteration_framework`, independent of the new backend and frontend
implementation. Decision: **approve the scoped experimental-input workflow**.
No detector-accuracy or product-authorship approval is given. This review covers
the new local research endpoint, full multiline input, concurrency, privacy,
result presentation, and browser integration. It does not independently re-audit
the metrics library that I implemented.

Final verification: 2026-09-27T15:06:06.981588+00:00.

## Evidence

- Eight research API regression tests passed independently. They verify lazy
  loading/model reuse, unchanged multiline input, no paragraph persistence or
  returned text, validation before loading, explicit truncation, finite scores,
  generic failures, lock release, concurrent-request rejection, and inherited
  origin/host/body protections.
- An additional synthetic regression used a first line of exactly 128 characters,
  followed by CRLF blank lines, a second paragraph with Unicode, and a final line
  with trailing spaces. All **231 characters** reached the fake model unchanged;
  counts matched the entire input. The response contained no submitted paragraph
  and sent `Cache-Control: no-store`. This directly exercises the earlier
  one-line-input failure without storing or reusing the user's paragraph.
- The repository browser suite passed **10 checks** under the project virtual
  environment. It exercises complete multiline/emoji JSON submissions, a valid
  zero score, precise near-one scores, visible truncation, busy errors, duplicate
  submission prevention, stale-response rejection even when the mock ignores
  cancellation, safe rendering, mobile layout, and existing source analysis.
- I submitted one real synthetic passage through the running interface at
  `http://127.0.0.1:8765`. It contained multiple paragraphs, blank lines, an
  accented word, and an emoji. The request carried the exact editor value:
  **602 characters, 80 words, and 97 tokens**. CUDA analyzed all 97 tokens without
  truncation and returned finite raw output `0.032436151057481766`, displayed as
  `0.03243615106`. Both `product_approved` and `calibrated` were false.
- That real browser check recorded **zero external browser requests and zero
  JavaScript errors**. Editing afterward cleared the research result and score.
  The main validated-authorship panel remained unavailable. Screenshot:
  `outputs/browser/experimental-real.png`, containing only synthetic audit text.
  I visually inspected the screenshot; the experimental label, counts, raw-value
  explanation, and separation from validated authorship are visible.

These are behavior checks, not empirical evidence that the classifier identifies
human or AI writing correctly. The single synthetic score has no accuracy or
authorship interpretation.

## Code review findings

No material defect was found in the final implementation.

`ResearchDetector` acquires a nonblocking lock before both lazy model loading and
inference. One request can load or use the model at a time; another receives 409.
The lock is released in `finally`, including load and inference failures. The
FastAPI handler is synchronous and runs outside the event loop; health and source
analysis remain separate from the inference lock. The concurrency fixture checks
that a pending inference does not prevent health responses.

The lazy loader calls the existing pinned local MAGE implementation, which uses
local model files; the request path adds no download or cloud API call. Loading
and inference failures become generic 503 responses without filesystem paths or
submitted text. The handler returns selected model metadata and input counts,
not the paragraph or prediction text hash, and adds no persistence operation.
This is code review and application-level testing, not a packet-capture audit of
the operating system or a claim that model tensors never exist in process memory.

The endpoint reuses strict input validation and request middleware. Blank, invalid
Unicode, null-byte, oversize, wrong-schema, cross-origin, and untrusted-host inputs
are rejected before loading. Line breaks and whitespace are otherwise retained.

The browser sends the textarea's complete value and binds the response to a
unique request ID and the current editor revision. Character-count validation
uses Unicode code points, matching Python counts for emoji. Edits abort the
browser request and invalidate its result; late responses cannot replace new
text. An aborted HTTP request does not forcibly interrupt an already-running GPU
operation. The UI timeout message correctly allows for the model still running.

The research panel renders a numeric raw score with ten significant digits and
does not label it as a percentage or verified authorship probability. It shows
character/word/token counts and clearly warns when only an initial token window
was analyzed. It does not add human/AI/mixed labels, authorship highlights, or
plagiarism conclusions. The existing validated-authorship response remains null
and unavailable.

## Prior evaluation scope and final binding

The inspected hashes of `detector_eval/experiment.py`, `detector_eval/reports.py`,
and `evaluation/check_authorship.py` are unchanged from
`phase2-experiment-audit.md`. That earlier scoped evaluation/report review remains
applicable. Its scientific limitations and blocked authorship, mixed-span, and
retrieval requirements are not changed by exposing an experimental test panel.

Completed run `20260927T150425-4d46ffc541c2` records passing software, reference
corpus, and browser checks, with the authorship experiment intentionally blocked.
The parent reported 102 passing software tests; I independently ran the focused
eight API tests and ten browser checks described above and checked the completed
run's statuses.

I recomputed the current protocol/implementation/input fingerprint and verified
that it matches the completed run:

`92fb4c60695086b17e82f493fa6acceab6d272863ce3a11b6312a256a45e9509`

Final inspected files:

| File | SHA-256 |
|---|---|
| turingtint/app.py | 9ce4ef2c98a6c3af1e27497b602851c4440dd30bd2de8994ea50a333625686dc |
| turingtint/research.py | cc75b9e1b5e1a656a94811b43c0c8d7a5f4bb8d7e7aaca3d5ae45985035e2611 |
| tests/test_research_api.py | 5e10b09c85746e70ea9a310ef638dd6335fea3399be4b77e2fb37519342ff1fe |
| web/index.html | 28a2f7bb60f05020021206f4f62972cf22319a2c6850494f79eb97ccffcabfec |
| web/app.js | 7683e013cd2cc5f445a0a3c97a4d681a570b3a92ccdd98075389f6d5085f654a |
| web/styles.css | 26a80f6bdff9b06882698826ca0c114a002866b478be79e15a92c399d8aafa3f |
| evaluation/check_browser.py | 4dd33f403b6c87c9ff9432ec9a083aff0907f54987b96323b1da6c9a49558127 |

The accompanying review JSON approves only this engineering scope and the
unchanged prior experiment scope. A separate reviewer covers model/metrics
evidence. Review approval does not override the blocked scientific gates.
