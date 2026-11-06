# PhysiCore company Codex skills

These company-owned repository workflows complement existing `physicore-work`, `scientific-review` and `market-scout` skills. They do not replace the scientific approval policy or authorize publication/deployment.

## Use

Keep each skill directory under the repository root `.agents/skills/`. Codex discovers repository skills from the current working directory up to the repository root. Use `/skills` to inspect discovery, or invoke explicitly:

- `$physicore-numerical-regression` for equations, numerical edge cases and independent expected results.
- `$physicore-api-workbench-check` for actual-app route/schema/authentication and UI result integrity.
- `$physicore-reviewed-github-update` for an already-authorized exact branch/PR update and landing evidence.

Descriptions also allow automatic selection. If a newly added skill does not appear, restart Codex and check `/skills`. No account configuration, plugin installation or external service is required for these instruction-only repository skills. They call for existing project commands rather than installing a new automation framework.

## Outputs, not certificates

A use should produce a scoped evidence record: exact revision/files, observed commands and numbers, reference/oracle provenance, failures/refusals, actual UI checks when relevant, review status and remaining gaps. Use the existing project evidence records and workflow rather than creating a second task ledger. Test each skill with a representative real task and a nearby non-trigger task. Acceptance of the skill's format does not prove its instructions were followed on future work.

Examples:

| Request | Skill | Expected boundary |
| --- | --- | --- |
| Check cantilever overflow and zero-load behavior | numerical-regression | independent arithmetic checks, not structural acceptance |
| Verify a new stateless plan endpoint | api-workbench-check | real middleware, bounded schema, no model execution |
| Publish this reviewed branch | reviewed-github-update | requires recorded owner permission and current CI |
| Change only a heading's spelling | none of these by default | normal small documentation edit |
| Approve an aircraft for flight | none can approve it | qualified review and appropriate physical evidence required |

## Basis

Codex format/discovery: https://developers.openai.com/codex/skills

Public workflow examples: https://developers.openai.com/blog/skills-agents-sdk

Existing project conventions inspected on main: `.agents/skills/physicore-work/SKILL.md`, `.agents/skills/scientific-review/SKILL.md`, `.agents/skills/market-scout/SKILL.md`, `AGENTS.md`, `.physicore/ops/WORKFLOW.md` and `.physicore/ops/SCIENTIFIC_GATES.md`.

Project-specific checks were distilled from equation/API/workbench regression and review experience. This addition makes no claim of full equation-engine scope, aircraft solver completion or experimental validation.
