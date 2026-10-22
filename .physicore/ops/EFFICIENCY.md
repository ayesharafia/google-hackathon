# Usage and development efficiency experiments (no fabricated percentages)

## Low-usage default
- One an available Codex model appropriate to the task primary run; no permanent 7-agent team.
- A single real outcome and short acceptance criteria per run.
- Read current state + affected code only, not the entire repository every time.
- Use small deterministic Python tooling for scoring and bookkeeping, not model calls.
- Run relevant tests; full suite for high-risk/release-affecting changes only.
- Research external market/standards when it changes priority or major physics decisions, not daily.
- Save a short STATE.md and actual commits/PRs for cross-session continuation.

## Experiment to establish whether extra agents pay off
Conduct an A/B study after the first code audit, on matched tasks (preferably >= 8 tasks per arm or rotated crossover tasks of similar difficulty). Compare:
- A: One available primary Codex model agent performing the whole approved workflow.
- B: One available primary Codex model agent with an independent specialist reviewer only for testable high-risk tasks.
- Hold constant task definition, repo commit, environment, model reasoning level, tool access and acceptance criteria as far as possible.
- Record start/end wall-clock time, human intervention, Codex usage dashboard snapshot (if visible), total retries, tests passed, escaped defects, benchmark error and accepted deliverables.
- Primary business measure: **independently accepted, reproducible improvements per hour / per usage unit**, not number of agents or commits.
- If exact token counts are unavailable on the Plus UI, write `NOT AVAILABLE`; don't infer token statistics from message count.
- Keep the simpler setup unless B makes a repeatable, measured difference in acceptance quality or developer throughput.

This kit's 14 passing tests cover only the deterministic queue tool, NOT the application or physics simulation. No measured token savings are claimed.
