# Experimental UI model-wrapper audit

Reviewer: plagiarism_research. Timestamp: 2026-09-27T15:02:07.738996+00:00

Decision: approve inspected wrapper and model-claim scope; no blocking findings. This is not approval of authorship accuracy or scientific validation.

Independently ran all 8 tests in tests/test_research_api.py: passed. Read the local research wrapper, route integration and frontend claim rendering/request lifecycle. An explicit research request lazily loads the unchanged pinned local MAGE adapter at 512 tokens, permits one inference at a time, returns bounded raw model output without submitted text, and sanitizes failures. The main source-analysis route still supplies no authorship score. No new persistence or network submission path was found. Existing origin/host/body/input guards apply.

The UI displays an experimental/unvalidated raw 0-to-1 score, explicitly disclaims a percentage or verified authorship probability, displays submitted-character/word and tokenizer counts, and visibly warns on truncation. It does not assign human/AI/mixed spans or plagiarism labels. Editor changes invalidate pending/result displays; request identity and revision guards reject stale completions. DOM writes use textContent/text nodes. Detailed model limitations are available separately. A browser abort does not cancel underlying local inference; the timeout notice acknowledges that the model may still be running.

Verified 47 unchanged recorded artifacts against the phase-2 run: all 37 data/model/prediction input files plus the recorded detector_models, detector_eval and requirements-ml files. This preserves previous model/metrics audit scope and findings resolution P2-001/P2-002. Parent and the other independent reviewer own broader UI input integration/browser verification. No full GPU accuracy experiment was rerun or inferred from these wrapper tests. Research, source independence, target-population and mixed-span gates remain blocked.

Inspected file hashes:

| Path | SHA-256 |
|---|---|
| turingtint/research.py | cc75b9e1b5e1a656a94811b43c0c8d7a5f4bb8d7e7aaca3d5ae45985035e2611 |
| turingtint/app.py | 9ce4ef2c98a6c3af1e27497b602851c4440dd30bd2de8994ea50a333625686dc |
| tests/test_research_api.py | 5e10b09c85746e70ea9a310ef638dd6335fea3399be4b77e2fb37519342ff1fe |
| web/app.js | 572d278fc0cb9ab67f67f00fc60a8adbe8cdc622e51d5236091dce4f3f16c394 |
| web/index.html | eb43eaaf6b95fff241d2c84b18ed551c46e901551032dc252a7971fc315c697f |
| detector_models/mage.py | 0527504e6fb0c525592fbaa995201979e904533d238d917124b5e78a439efea7 |
| detector_eval/metrics.py | e49acef73e99c5440b98ad4a41c0b0efc894c4fce6acc53dc96965fc06592d11 |
| evaluation/protocol.json | 2fe8396927af53d5a5fa2dbf25bff45438d5f4318f691e4d3ab43bf115604dd5 |
| evaluation/check_authorship.py | 4f474f8f8b5bcf2a7215494a6f0776ae94febbb962cb2feea07351d9983a86f6 |
| detector_eval/reports.py | 65f993562b9dc6cd625b045646996a2da57379fd3b742842a701fb96006d67db |


## Final snapshot refresh

2026-09-27T15:05:37.255831+00:00

Rechecked final frontend claim wording and invalidation state. Introduction now distinguishes submitting the full passage from analyzing a truncated prefix. Retest notice persists across successive edits; request revision/identity guards remain intact. Read updated model documentation. No new findings. Verified every implementation/input artifact hash against completed run 20260927T150425-4d46ffc541c2 and subject 92fb4c60695086b17e82f493fa6acceab6d272863ce3a11b6312a256a45e9509. Scientific validation remains blocked. Full protocol and actual GPU browser smoke are separate reviewer evidence, not independently rerun in this focused refresh.

| Path | SHA-256 |
|---|---|
| turingtint/research.py | cc75b9e1b5e1a656a94811b43c0c8d7a5f4bb8d7e7aaca3d5ae45985035e2611 |
| turingtint/app.py | 9ce4ef2c98a6c3af1e27497b602851c4440dd30bd2de8994ea50a333625686dc |
| tests/test_research_api.py | 5e10b09c85746e70ea9a310ef638dd6335fea3399be4b77e2fb37519342ff1fe |
| web/app.js | 7683e013cd2cc5f445a0a3c97a4d681a570b3a92ccdd98075389f6d5085f654a |
| web/index.html | 28a2f7bb60f05020021206f4f62972cf22319a2c6850494f79eb97ccffcabfec |
| detector_models/README.md | 5432813534183df91f0e6f410a27190a34a8f1471ba66a097681fe00015d7570 |
| detector_models/mage.py | 0527504e6fb0c525592fbaa995201979e904533d238d917124b5e78a439efea7 |
| detector_eval/metrics.py | e49acef73e99c5440b98ad4a41c0b0efc894c4fce6acc53dc96965fc06592d11 |
| evaluation/protocol.json | 2fe8396927af53d5a5fa2dbf25bff45438d5f4318f691e4d3ab43bf115604dd5 |
| evaluation/check_authorship.py | 4f474f8f8b5bcf2a7215494a6f0776ae94febbb962cb2feea07351d9983a86f6 |
| detector_eval/reports.py | 65f993562b9dc6cd625b045646996a2da57379fd3b742842a701fb96006d67db |
