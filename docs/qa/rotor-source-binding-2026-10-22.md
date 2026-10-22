# Guided retained rotor source binding

22 October 2026. UI-002; owner approved the concrete design, targeted tests,
browser review and publication of all completed pending work to main. Source
baseline: `5477f94`. One primary implementing agent; no independent scientific
acceptance is claimed.

## Delivered workflow

Import a rotor_map_v1 JSON file in the existing rotor editor. The preview shows
the returned dataset ID, configuration ID, declared source kind and full retained
SHA-256. Choose matching rotors explicitly, then apply. No rotor is selected by
default. Incompatible configurations are disabled; ambiguous or missing rotor
IDs, empty/duplicate selections and draft changes refuse assignment atomically.

Only selected base rotor map_ref fields change. Case overrides, conditions,
limits, source bytes and advanced hash fields remain intact. Assignment marks
the draft unsaved, clears readiness results and returns focus to the rotor
editor. Save draft retains the references; reopening restores them. Existing
frozen revisions retain their original sources. A delayed import after an edit
or project/context change cannot create a current binding preview.

Configuration identity is a selection aid. It does not establish installed
performance, operating coverage, measurement accuracy or aircraft acceptance.
Inspect the saved draft after binding. Source truth and qualified engineering
review remain separate, pending evidence.

## Verification

| Check | Result | Receipt |
|---|---|---|
| Combined readiness/source-binding Node unit tests | 35 passed | [Unit receipt](../../.physicore/evidence/UI-002-test-20261022154956983658.json) |
| Existing local-study and project-geometry tests | 26 passed; existing Starlette/httpx deprecation warning | [Regression receipt](../../.physicore/evidence/UI-002-test-20261022155448346113.json) |
| Guided source-binding Chrome journey | 10 passed; no page JavaScript errors | [Browser receipt](../../.physicore/evidence/UI-002-test-20261022155217606684.json), [check list](assets/rotor-source-binding/browser-checks.json) |
| Readiness Chrome journey on final combined app | 18 passed; no page JavaScript errors | [Regression browser receipt](../../.physicore/evidence/UI-002-test-20261022155444048328.json) |
| Ruff | Passed | [Lint receipt](../../.physicore/evidence/UI-002-test-20261022155456764772.json) |
| JS syntax, protected-file diff, local links, whitespace and hashes | Passed | [Static record](../../.physicore/evidence/UI-002-static.json) |

The source journey used actual file selection, checkbox/button clicks and
save/reopen, exact raw-byte comparison in a disposable artifact store, frozen
revision preservation, mismatched/stale refusal and a delayed real API response.
All data was labelled synthetic, in a fresh loopback data root. Existing source
conditioning and advanced source fields were preserved, not redesigned. An
initial verification wrapper invocation rejected an absolute executable path;
using its permitted python3 command with the existing venv PATH ran the tests.
No application failure or dependency installation resulted from that refusal.

## Interface review

Re-read the owner's full interface law and the complete
[UI-001 applicability ledger](engineering-readiness-2026-10-22.md#interface-law-review).
That ledger applies to the combined readiness integration. Reviewed each rule
again for this added preview, then inspected the actual screenshots:
[desktop](assets/rotor-source-binding/desktop.png),
[390 px](assets/rotor-source-binding/mobile.png),
[CSS 200%](assets/rotor-source-binding/zoom-200-css.png).

- Palette/type/layout: the existing green/ink workbench, one tonal inset source
  sheet, actual metadata, native fieldset/checkboxes and one explicit action.
  No page/hero/footer template, font rotation, marketing filler, fake proof,
  decorative icon/boxed logo, pill, gradient, glow, rule or shadow was added.
- Motion/material: controls stay still, content is visible by default. No reveal
  gate, glass, hover lift, underline animation, background grid or texture layer.
  Selection, refusal, focus return and unsaved status provide real interaction.
- Readability: metadata and full hashes wrap. Phone and enlarged-text checks
  cover both element bounds and text ranges. No fixed text heights, clipping,
  notches, edge crowding, overlapping layers or ragged comparison columns.
  Checkbox rows share a grid with generous label targets. Action labels remain
  centered and readable, including when enlarged and wrapped.
- Behavior: actual imports, empty selection, individual selection, mismatches,
  stale edits and delayed responses were exercised. Success/refusal uses visible
  status text; checkboxes have native labels and the selection group has a legend.
  The original product geometry remains the actual visual artifact. A source
  assignment form does not warrant invented imagery, brand marks or a new kit.

Native browser zoom, human usability, real aircraft data, production hosting,
security/endurance/recovery qualification and scientific acceptance were not
assessed. CSS enlargement is explicitly recorded as such. No src/physimesh,
existing physics assertions, model tolerances, access settings or dependencies
changed.

## Reproduce

Use Node 22+ and the existing project Python environment:

```sh
node --test tests/web/test_rotor_source_binding.mjs tests/web/test_engineering_readiness.mjs
python3 -m pytest -q tests/projects/test_local_studies.py tests/projects/test_project_geometry.py
```

For browser checks, start a fresh disposable loopback app with its own artifact
root and local public mode. Set PHYSIMESH_BROWSER_BASE_URL,
PHYSIMESH_BROWSER_DISPOSABLE=1 and PHYSIMESH_BROWSER_DATA_ROOT to that root;
run node scripts/qa/rotor_source_binding_browser.mjs and the existing readiness
browser script. Playwright/Chrome must already be available;
PHYSIMESH_PLAYWRIGHT_MODULE may name an installed module and
PHYSIMESH_BROWSER_EVIDENCE_DIR selects output. Never target client data.
