# PLAYBOOK.md : How B Leads a Physics Project Without Knowing Physics

## The mindset shift
You are not the physicist. You are the **judge of evidence**.
Your job is never "is this equation right?" Your job is always:
1. Is there a written spec the scientist approved?
2. Is there a plot of our result vs a trusted reference, and do the lines overlap?
3. Did anyone change a tolerance, a coefficient, or an equation without logging it?

If all three are yes, ship. If any is no, send it back. That is the whole job, and you can do it without one line of physics.

"Keep building" fails because the agent has no finish line. This system gives every task a finish line that is a **number compared against a known answer**.

---

## The Agent Team (lives in `.claude/agents/`)

| Agent | Role | Analogy |
|---|---|---|
| `physics-architect` | Breaks a goal into features, orders them, writes ROADMAP | Chief engineer |
| `spec-writer` | Turns one feature into a PHYSICS_SPEC for the scientist | Draftsman |
| `validation-engineer` | Finds benchmarks, builds reference data, writes failing tests FIRST | Examiner who writes the exam |
| `solver-builder` | Writes code until the tests pass. Cannot touch tests or tolerances | Student taking the exam |
| `physics-auditor` | Fresh eyes. Hunts for cheating: tuned params, loosened tolerances, invented numbers | Auditor |
| `explainer` | Writes the plain-language report for you | Teacher |

**Key separation:** the agent that writes the exam (validation-engineer) is never the agent that takes it (solver-builder). This is what stops AI from "making tests pass" by fudging.

---

## The Weekly Rhythm

| When | You | Agents | Scientist |
|---|---|---|---|
| Monday (30 min) | Run `/plan-week`. Pick 1 to 3 features. | Architect proposes, ranks by risk | none |
| Mon to Tue | Run `/spec <feature>` | Spec-writer drafts | none |
| Tuesday (20 min per spec) | Forward spec | none | Reviews section 4 and 10, answers section 11 |
| Wed to Thu | Run `/build <feature>` | Validation engineer, then solver builder, then auditor | Only if a validation fails and the auditor cannot explain why |
| Friday (30 min) | Run `/explain <feature>`, read report, approve or reject | Explainer | 10 min: skim the plots |

Scientist load: about 1 to 2 hours a week. That is the scaling trick.

---

## Commands (lives in `.claude/commands/`)
- `/kickoff <project>` : first-time intake for a project. Run once per domain.
- `/plan-week` : propose this week's features.
- `/spec <feature>` : draft spec + scientist questions.
- `/build <feature>` : tests first, then solver, then audit.
- `/explain <feature>` : plain-language report.
- `/status` : traffic-light dashboard of all domains.
- `/teach <concept>` : explain any physics word to you in 5 lines.

---

## The Questions You Ask (memorize these 8, nothing else)
When reading any report or agent output, ask:
1. "What is this compared against, and who published it?"
2. "Show me the plot. Our line vs reference line."
3. "What is the error in percent, and what tolerance did the scientist approve?"
4. "If I make the mesh 2x finer, does the answer stay the same?"
5. "Does energy (or mass, or charge) balance? What is the imbalance?"
6. "What assumption, if wrong, breaks this?"
7. "Where outside this range should we NOT trust it?"
8. "Did anything change since the spec was approved?"

If an agent can't answer one of these crisply, the work isn't done.

---

## Red Flags (send it back immediately)
- "The simulation runs successfully" with no comparison. Running is not correct.
- "Results look physically reasonable." Means nothing.
- A coefficient with no source.
- Tolerance changed in a commit.
- Error went from 30% to 1% after "adjusting parameters". That is tuning, not fixing.
- Agent says "approximately" about a benchmark value without a citation.
- A new feature built on top of a feature that hasn't reached L4.

---

## Phase Order for Any Domain (the "industry" direction)
Every serious simulation company builds in this order. Never skip a rung.
1. **Foundation:** units system, mesh, I/O, config with cited constants, test harness, plotting vs reference.
2. **Simplest physics that has an exact answer** (1D conduction, lid-driven cavity, SPM battery).
3. **Real physics, still validated** (2D/3D, turbulence model, DFN battery).
4. **Coupling** (fluid + heat, electrochem + thermal). Couple only two already-validated pieces.
5. **Scale and speed** (big domains, parallel, GPU). Only after correctness.
6. **Product layer** (UI, presets, warnings when outside valid range, report export).
7. **Customer validation** (L5/L6, real data, case studies).

Your current projects probably skipped steps. `/kickoff` will audit where each one really is.

---

## How To Talk To Agents (prompt patterns)

**Never say:** "keep building", "improve the simulation", "make it more accurate".

**Say instead:**
- "Run /status and tell me the single biggest risk in the drone project."
- "What is the next rung on the ladder for battery? Draft the spec."
- "This plot shows 8% error. Auditor: is that a bug, a mesh issue, or a model limit? Give me evidence, not guesses."
- "Explain the turbulence model choice like I'm a web developer. What breaks if we picked wrong?"
- "Prepare 3 yes/no questions for the scientist about this spec."

Rule: every request ends with a deliverable you can check (a file, a plot, a number, a yes/no).
