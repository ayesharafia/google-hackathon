# Company-skill input map

These skills are drafted from ordinary project source/tests, existing company policies and public Codex format documentation. They are not a copy of an external assistant workflow. Historical permissions asserted by repository files must not be treated as new approval.

## All skills: native packaging and scope

- Required frontmatter `name` / `description`, repository discovery and explicit invocation: https://developers.openai.com/codex/skills (read 6 November 2026).
- Existing company skill patterns: `.agents/skills/physicore-work/SKILL.md`, `.agents/skills/scientific-review/SKILL.md`, `.agents/skills/market-scout/SKILL.md`.
- Project boundaries and ordinary review/publication conventions: `AGENTS.md`, `.physicore/ops/WORKFLOW.md`, `.physicore/ops/SCIENTIFIC_GATES.md`. These files are existing project material, not proof of a particular owner's approval.

## physicore-numerical-regression

- Contract, units, references, uncertainty, relevant checks, unchanged thresholds and evidence labels: `.physicore/ops/SCIENTIFIC_GATES.md` and original company drone/equation-engine specifications.
- Fixed-wing equations, declared envelope and reference links: `src/physimesh/drone/fixed_wing.py`; finite-number and subnormal refusal tests in `tests/drone/test_fixed_wing.py`.
- Thermal energy budget, zero conductance, equilibrium, underflow/cancellation support: `src/physimesh/drone/thermal.py`, `tests/drone/test_thermal.py`.
- Beam conventions and exclusions: `src/physimesh/drone/cantilever.py`, `tests/drone/test_cantilever.py`.
- Independent oracles, high precision and limiting-case checks are proposed repeatable test-design practices implementing the scientific-gates requirements. They do not claim all future models already have these tests.

## physicore-api-workbench-check

- Real application auth/hash/nonmutation checks: `tests/drone/test_fixed_wing_application.py::test_real_app_auth_refusal_hash_nonmutation`, `::test_local_cookie_csrf`; `test_thermal_application.py::test_auth_hash_refusal_schema_nonmutation`, `::test_cookie_csrf`; `test_cantilever_application.py::test_auth_hash_units_refusal_nonmutation`, `::test_exact_shape_declarations_and_csrf`.
- Strict nested shape, sanitized JSON and Unicode behavior: LOCAL `tests/drone/test_dependencies_application.py::{test_strict_nested_shape_and_sanitized_errors,test_invalid_json_sanitized,test_invalid_unicode_scalar_raw_json_is_sanitized_before_hash,test_valid_nonbmp_metadata_preserved_and_hashed}`; LOCAL `src/physimesh/api/dependencies.py`. Local planner/API work is not in PR26/main at this draft's cutoff.
- Canonical hashes: `src/physimesh/drone/provenance.py`, application tests above.
- UI text rendering, request generation/context checks and result validation: `web/js/{fixed-wing-screening,thermal-screening,cantilever-screening}.js`. Desktop/phone and keyboard checks are proposed reusable acceptance checks, not a universal claim of completed UI testing.

## physicore-reviewed-github-update

- Existing change/evidence/review/publication boundaries: `AGENTS.md`, `.physicore/ops/WORKFLOW.md`, `.physicore/ops/SCIENTIFIC_GATES.md`; actual authorization must come from current owner-approved scope.
- Exact CI job coverage, conditional vendor-backend dispatch and declared test commands: `.github/workflows/ci.yml`; supported Python/package context: `pyproject.toml` and locked requirements.
- Revision-specific PR evidence, preservation of unrelated work and reporting pending/skipped checks are proposed release practices supporting those project policies. They do not assert that a particular PR is currently green or permitted to merge.

Incident-specific editor, timeout and review-harness anecdotes are excluded from these revised skills. The package contains no account identity or authentication configuration. The three skills are instruction-only; format checks do not establish successful Codex discovery or behavioral execution until tested in an actual repository session.

The review evidence package, provided separately and not installed by these skill additions, contains company-source snapshot `local-reviewed-v34-2026-11-06` with per-file SHA256 values in its `snapshot-manifest.json` for these inspected implementation/test examples. PR26 head is `87f413d5d4b7918488e07e69665182bc9d9264eb`; dependency planner/API examples are later LOCAL reviewed files, not main. Fresh company convention bytes were provided separately for review; neither review input package is part of this six-file installation. This immutable snapshot identifies inspected inputs without asserting remote freshness or publication.
