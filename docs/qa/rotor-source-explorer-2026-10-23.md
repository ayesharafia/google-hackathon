# Rotor Source Explorer: executed checks

23 October 2026. Owner approved “Proceed with Rotor Source Explorer”, including
targeted tests, browser checks, full interface review and publication to main.
One implementing Codex agent; no independent scientific approval claimed.
Baseline: `ff2b2785b02a863e8439b8134ecf072591034323`.

## Delivered behavior

The existing library's Inspect source view now has discrete retained-point
plots of thrust, absorbed torque or recorded power against RPM, literal coverage
bars, exact selected values and original-row table. Electrical and shaft bases
remain separate; gaps and uncovered retained points remain visible. Native
sample/quantity selection and pointer/keyboard marker selection share one current
point. Search/source/project changes clear prior data and suppress late responses.
Existing permissions, original/conversion downloads and explicit binding remain.

## Recorded checks

Receipts are in `.physicore/evidence/`; each records the actual command/output.
Counts below describe distinct checks in each final suite, not cumulative reruns.

| Check | Result | Receipt suffix after `SOURCE-EXPLORE-001-test-` |
|---|---|---|
| Projection, identity, units/basis, conditions, coverage, exact row mapping, display transforms and request lifecycle; prior readiness/binding/comparison/energy/pack/trim units | 124 pass: 24 new, 100 existing | `20261023064755126605.json` |
| Existing source library, tabular importer and reuse pagination Python tests | 45 pass | `20261023063347389625.json` |
| New explorer, actual local API and installed Chrome | 17 pass | `20261023064428155593.json` |
| New explorer with actual hosted-mode viewer and server pagination | 7 pass | `20261023064426366908.json` |
| Existing CSV/XLSX importer/library browser regression | 12 pass | `20261023063740834663.json` |
| Existing source-binding browser regression | 9 pass | `20261023064143623498.json` |
| Existing hosted-viewer browser regression | 4 pass | `20261023064142857652.json` |
| Existing Case Trim Evidence browser regression | 19 pass | `20261023064144969093.json` |
| Built wheel contains exact six web assets and their resource hashes | pass | `20261023064537216936.json` |
| New explorer JavaScript syntax | pass | `20261023064537432219.json` |
| Seven JavaScript syntax checks, protected paths, local documentation links, 147-entry ledger, whitespace and screenshot hashes | pass | `20261023064854244650.json` |

Total browser coverage: 68 checks across the six listed journeys, no page
JavaScript errors. Earlier successful reruns and a 76-test subset are retained;
the final 124-test run includes the complete intended seven-file unit selection.
Existing Python Starlette/httpx deprecation warning remains. No failed task
checks were hidden or converted into acceptance.

## Fixtures and negative cases

The new public-mode browser journey saves labelled synthetic CSVs through the
actual existing API. Electrical samples include physical rows 2, 4, 5, 7, 8,
zero values, two separated coverage intervals and a stored point in the gap.
A separate shaft source carries declared efficiency but displayed watts equal
the retained shaft watts. Original bytes and manifest downloads match exactly;
inspection leaves draft and source detail unchanged.

Delayed real detail responses exercise source/search/project races. Labelled
response fixtures exercise mismatched identity, malformed sample and denied
source rendering. These injected responses establish UI refusal behavior, not
production authorization. Actual server permission/corruption behavior is covered
by the unchanged Python tests and hosted-mode viewer journey.

The viewer fixture uses a disposable SQLite hosted-mode app with owner/viewer
identities. Source inspection and point selection remain available, upload/reuse
remain disabled, a real second catalog page leaves the inspector usable, exact
download leaves the draft untouched, and sign-out removes private evidence and
rejects a detached action. Its all-zero torque source stays on the zero axis.

## Interface review and corrections

The [full 147-entry law ledger](rotor-source-explorer-design-law-2026-10-23.md)
records the point-by-point re-check. Existing product typography and tonal
green/ink surfaces are retained. The authored visual is real retained point data,
with linked exact readout/table and meaningful coverage gaps. No decorative
illustration, new card system, motion dependency, framework or font was added.

Visual inspection caught a malformed container-query condition that kept wide
controls stacked. It was corrected and the final browser check asserts two
columns on wide layouts. Native sample options were shortened to original-row
labels, retaining exact RPM in the readout/table/marker name. SVG name and
description were separated; keyboard instructions match the implemented arrows.
Final screenshots were regenerated and inspected after these changes.

Desktop width 1440, phone width 390 and CSS `zoom: 2` were checked for gutters,
text/control containment, marker and tick containment and table reachability.
Coverage bars are data, axes carry units, selected values use aligned responsive
field/value cells, and whole numeric table cells scroll rather than truncate.
Pointer selection, native select changes, Left/Right/Home/End/Enter/Space marker
handlers and existing download/reuse controls were exercised. Content is visible
without an entrance animation; selection updates immediately.

- [Desktop context](assets/source-explorer/desktop-context.png)
- [Phone context](assets/source-explorer/phone-context.png) and [plot](assets/source-explorer/phone-plot.png)
- [Enlarged context](assets/source-explorer/enlarged-context.png) and [plot](assets/source-explorer/enlarged-plot.png)
- [Explorer results](assets/source-explorer/results.json) and [viewer results](assets/source-explorer/viewer/results.json)

## Limits

Synthetic software evidence does not qualify measured sources, model equations,
flight performance or real aircraft. Native OS select-popup keyboard behavior,
screen-reader output, native browser zoom, real-user usability and production
identity/provider integration were not verified. CSS enlargement is not native
zoom. Axis tick rounding is visual only; the exact retained values remain exposed.
No scientific parameters, retained source/result bytes, dependencies, API/access
settings or existing scientific assertions were edited. Disposable QA servers
are separate from the original shared service; no deployment/restart is included.
Usage: [technical guide](../technical/rotor-source-explorer.md).
