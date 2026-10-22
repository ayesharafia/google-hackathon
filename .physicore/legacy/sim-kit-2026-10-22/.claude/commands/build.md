---
description: Tests first, then solver, then independent audit
argument-hint: <feature>
---
Feature: $ARGUMENTS
1. Check specs/$ARGUMENTS.md is Status: APPROVED. If not, stop and tell B.
2. validation-engineer: write reference data and failing tests. Confirm they fail.
3. solver-builder: implement until tests pass. No edits to validation/.
4. physics-auditor: independent check.
5. If any item FAILs, loop back to step 3 at most 3 times, then stop and summarize for B and the scientist.
6. Update ROADMAP.md with the ladder level reached.
