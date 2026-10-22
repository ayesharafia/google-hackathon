---
description: First-time intake and audit of one project domain
argument-hint: <drone|thermal|datacenter|battery>
---
Project domain: $ARGUMENTS

Use the physics-architect agent. Steps:
1. Ask B these intake questions first (wait for answers): Who is the customer and what decision will they make with this simulation? What outputs do they need (numbers, plots, maps)? What accuracy would they accept? What exists today (files, scripts, solver)? What does the scientist consider the biggest weakness?
2. Audit the existing code for this domain. For each piece, the ladder level it has PROVEN (evidence in repo, else L0).
3. Fill this domain's table in ROADMAP.md, following the phase order in PLAYBOOK.md.
4. Give B: current true state in 5 lines, top 3 risks, and the first 3 features to spec.
