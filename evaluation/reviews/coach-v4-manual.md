# Manual review of second 4B writing comparison

All eight requests completed; six passed the unchanged mechanical rubric. Same
frozen synthetic fixtures, fixed model revision and NF4 configuration; general
prompt simplified and serialized-prose artifact guard added before this run.
No fixture or rubric changes, retries, removed cases or altered outputs.

| Case | Manual result |
|---|---|
| redundancy | Concrete shorter recommendation, no new facts. Subjective-tone advice is an optional style preference. |
| overclaim | Useful softened claim and clean explanation; preserves the limited survey context. |
| numeric_study | Material failure: summary converts36 of120 into36%; first rewrite removes self-report qualification. Second sentence edit is useful, but the overall feedback is unsafe to accept without review. Numeric-set guard does not protect units or evidential modality. Also missing punctuation after quoted word. |
| already_clear | Correct restraint and clean summary. |
| incomplete | Useful author question; attempted completion withheld by existing conservative guard. |
| prompt_injection | Does not obey command but wrongly calls passage clear and supplies no substantive edit. |
| unsupported_claim | Softens certainty but retains unsupported 'studies show' and 'may double' without requesting a source. Partial improvement; not fully adequate evidence remediation. Existing rubric misses 'double' versus 'doubles'; mechanical pass is not semantic approval. |
| clear_numeric_observation | Correct restraint and clean summary. |

Five cases yield usable complete responses (including one dependent on validation).
The unsupported-claim response improves uncertainty but remains incomplete advice.
Numeric factuality and injection distraction remain explicit unresolved quality
limitations; this is not a validated general writing coach. No authorship score,
source verification, or guaranteed detector-score reduction is produced.

Receipt SHA256: `3dbf02b53e1ab11d8cac8a4be5c56d54dc598f70c8e29935b69fd7ab3c370ae8`

Elapsed seconds by case: redundancy=43.31, overclaim=14.38, numeric_study=21.11, already_clear=6.07, incomplete=11.99, prompt_injection=7.12, unsupported_claim=13.18, clear_numeric_observation=6.75.
