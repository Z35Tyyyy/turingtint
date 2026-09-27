# Local LLM writing review

The optional reviewer uses Qwen/Qwen3-1.7B at immutable revision
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, loaded from `.cache/coaching-model`.
The [official Qwen card](https://huggingface.co/Qwen/Qwen3-1.7B)
documents Transformers support and disabling thinking through the chat template.
The application disables thinking, uses safetensors and refuses remote code or
runtime model downloads. Setup writes a complete file-hash manifest; files are
checked before first model load. This manifest is local provenance bookkeeping,
not a signed independent artifact attestation.

Review is limited to 8,000 characters and 3,072 complete prompt tokens. Overlong
inputs are rejected, never silently truncated. Generation allows at most 900 new
tokens and a 90-second generation time budget. The schema caps suggestions at two,
ordinary fields at 240 characters and quotes/rewrites at 320 characters to reduce
token-budget exhaustion. Transformers checks its time bound
between decoding steps, not as a hard process deadline. A shared nonblocking GPU
lock prevents overlapping local model tasks. No review text or result is written
to disk by this module.

Local generation uses a fresh JSON-schema parser from pinned
`lm-format-enforcer==0.11.3` with the Transformers prefix-allowed-token hook;
see the [upstream integration example](https://github.com/noamgat/lm-format-enforcer).
It constrains JSON syntax and structure, not factual accuracy. Local output must
still parse and pass the strict review schema. Suggestions are attached only
to exact unique input substrings with independently calculated UTF-16 offsets;
invented or ambiguous quotes are discarded. Rewrites introducing numbers absent
from the source (outside explicit brackets) are withheld while preserving grounded
review comments. This narrow guard does not verify semantic factuality or catch
all invented details; there is no general vocabulary whitelist. There is no heuristic fallback after
invalid output, timeout or refusal. Grounded quotation does not verify the truth
of explanations or rewrites. Prompt instructions ask for preserved facts and
questions/placeholders for missing details. Prompt injection remains a model
quality concern; passage text has no tool or execution authority.

An explicitly selected OpenAI provider requires server environment variables
`OPENAI_API_KEY` and `TURINGTINT_OPENAI_MODEL`. It sends the passage to the fixed
official Responses endpoint, requests `store:false` and strict JSON schema via
`text.format`, refuses redirects and bounds response size/time. It never falls
back from local processing to the API. `store:false` is not a promise of zero
provider retention. No paid API call was made during implementation.
See [official structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

The assessment is an unvalidated LLM opinion, not an authorship probability,
human ground truth, plagiarism decision or mixed-span classifier. Revisions aim
to improve specificity, clarity and attribution, without promises to lower a
detector score. Existing scientific validation gates must remain blocked.

## Actual development findings

Initial CUDA checks produced exact anchored suggestions but also unsupported added details (including unspecified covariates) and a malformed JSON response. These original outputs are retained under outputs/reviews/llm-coach-smoke.json and llm-coach-public-raw.txt. A prompt revision changed a known assistant-generated education sample from ai_leaning to human_leaning. This instability is evidence against treating the LLM opinion as accurate authorship detection. It was not corrected by forcing a known answer. Guided JSON addresses syntax only; bracketed author questions and the numeric guard address a narrow part of revision risk. Human review of every proposed edit remains necessary.

Final bounded guided CUDA smoke completed on both the public reference excerpt and the actual default UI sample: one and two retained exact-quote suggestions respectively, in39.6s cold and27.6s warm. Retained rewrites used source wording plus bracketed evidence questions, without invented covariates in these inspected cases. The public sample discarded an illustrative-example quote absent from the source. Detailed prior failures, final outputs and limitations are retained in outputs/reviews/coaching-smoke-summary.md and llm-coach-bounded-smoke.json. These are functional checks, not evidence of detection accuracy or guaranteed factual preservation.
