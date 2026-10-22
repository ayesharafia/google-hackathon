# CLAUDE.md : Project Context for All AI Agents

## What this repo is
A multi-physics simulation platform. Current domains:
- Drone aerodynamics (turbulence, rotor flow)
- Thermal (conduction, convection, conjugate heat transfer)
- Data center cooling (airflow + heat, large domains)
- Battery (electrochemistry + thermal)

## Who is on the team (read this carefully)
- **Lead (B):** developer and project lead. NO physics background. Decides scope, priorities, and ships.
- **Scientist:** the only person who knows the physics. His time is scarce. Use him ONLY to approve physics specs and review failed validations. Never ask him to write code.
- **AI agents (you):** do the physics reasoning, implementation, testing, and explanation.

## The one rule that overrides everything
**Code that has not passed a validation case does not exist.**
A simulation that "runs" and "looks reasonable" proves nothing. Every physics feature must be checked against a known answer (analytical solution, published benchmark, or trusted reference code) BEFORE it is considered done.

## How every feature moves (the loop)
1. **SPEC** : Write `specs/<feature>.md` from `templates/PHYSICS_SPEC.md`. Equations, assumptions, units, boundary conditions, valid range, and which validation cases prove it works.
2. **SIGN-OFF** : Scientist reviews the spec (target: under 20 minutes). He edits assumptions, he does not write code.
3. **TESTS FIRST** : Write the validation tests from the spec before the solver code. Tests must fail initially.
4. **BUILD** : Implement until tests pass. Do not loosen tolerances to make tests pass. If you think a tolerance is wrong, stop and flag it.
5. **VERIFY** : Run the verification ladder in `VALIDATION.md` (conservation, convergence, benchmark).
6. **EXPLAIN** : Write `reports/<feature>.md` using `templates/EXPLAIN_REPORT.md`. Plain language. The lead must understand it without physics knowledge.
7. **DECIDE** : Lead approves, or sends it back.

## Rules for agents
- Always state units. Use SI internally. Convert only at UI boundaries.
- Every physical constant and model coefficient lives in one config file with its source cited (paper, textbook, standard).
- Never invent a coefficient, correlation, or benchmark value. If you are not sure of a number, say so and mark it `UNVERIFIED` in the spec.
- Never silently change an equation, a boundary condition, or a tolerance. Changes go through the spec.
- If a result disagrees with a benchmark, report the gap honestly. Do not tune parameters until it matches; that hides bugs.
- Prefer validated open-source references for comparison (OpenFOAM, PyBaMM, FEniCS, published datasets) rather than trusting your own memory.
- Explain to the lead in simple terms, using analogies, with one sentence on "why this matters for the product".

## Agent roster (.claude/agents/)
physics-architect (plans), spec-writer (specs), validation-engineer (writes tests, owns tolerances), solver-builder (writes code, cannot touch validation/), physics-auditor (independent check), explainer (reports for B). The one who writes the exam never takes it. See PLAYBOOK.md for the weekly rhythm and commands.

## Autonomous mode
If B says anything vague ("develop further", "keep going", "next", "work on something"), do not ask what to do. Use the orchestrator agent and follow AUTONOMY.md: pick the next task yourself with its priority rules, respect the green/yellow/red decision zones, park blocked items in INBOX_FOR_B.md or INBOX_FOR_SCIENTIST.md, and finish with the DIGEST in JOURNAL.md. If B gives direction, it overrides the priority rules.

## Where things live
- `AUTONOMY.md` : decision rights, the autonomous cycle, priority rules
- `BACKLOG.md` : ready tasks; `JOURNAL.md` : what was done and why, digests at top
- `INBOX_FOR_B.md`, `INBOX_FOR_SCIENTIST.md` : questions waiting on humans
- `specs/` : approved physics specs (source of truth)
- `validation/` : benchmark cases, reference data, test scripts
- `reports/` : plain-language explain reports
- `ROADMAP.md` : phase plan and current status
- `DECISIONS.md` : log of every assumption/decision and who approved it
