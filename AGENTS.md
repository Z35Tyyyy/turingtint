# Training decision log

The user requested a Desktop text log updated by a background process every five
minutes. For this training project, append a JSON object to
`training/decisions.jsonl` after each meaningful decision, action, or result.
Use `timestamp` (actual ISO-8601 time), `decision`, `rationale` (brief public
explanation), and `status`. Log concise decision summaries, not private internal
reasoning. Never include tokens, credentials, or other secrets.

The Windows logger reads this journal and appends to
`C:/Users/Asus/Desktop/training logs.txt` every 300 seconds while its process runs.
Its helper files and process state are under
`C:/Users/Asus/AppData/Local/TuringTint/training-log-writer`.
The journal is the source of truth; the background process cannot infer decisions
from the assistant's conversation. Keep the journal current during future work.

# Detector implementation loop

The active project is a free/local English academic/student detector and source
matching application. The user monitors; agents perform implementation and
automated evaluation. Parallel agents are authorized for bounded independent
work, with explicit file ownership to prevent conflicting edits.

For each meaningful iteration:
1. Inspect the latest report and open issues using `python -m iteration status`
   and `python -m iteration open-issues` (see `iteration/README.md` for paths).
2. Select a concrete gap and record the hypothesis, intended change and check.
3. Implement the change; ask a separate agent to audit material changes when
   available. Reviews must identify what was actually inspected and tested.
4. Run `python -m iteration run --protocol evaluation/protocol.json` using the
   project virtual environment. Preserve failures and newly discovered issues.
5. Fix regressions and repeat only when a change or new evidence warrants it.
6. Record the result in the decision journal and update the next-work list.

Do not turn missing metrics into passing gates, remove blockers to obtain a green
report, or label synthetic/AI-reviewed data as human evidence. Software checks,
source retrieval evaluation and detector accuracy are separate gates. Failed or
unknown authorship capability stays unavailable in the UI. No paid services,
unbounded generation/training or external submission of user text by default.

The runner records/checks evidence; it does not autonomously edit source code.
Bounded agent iterations happen during active work. Background check processes
do not imply that an assistant continues reasoning while the session is inactive.
