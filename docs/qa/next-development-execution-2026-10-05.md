# Next-development execution receipt, 5 October 2026

The implementable fixture-driven model and workbench slices of the
[5 October specification](../plans/2026-10-05-next-development-plan.md) are
implemented on `codex/next-development-plan`. The single active roadmap is
[plan.md](../../plan.md#active-slice-status). **Independent physics review,
human engineering acceptance, client inputs and hosting decisions remain
pending.** No new model is merged/tagged as an approved physics release.
The client confirmed real data is unavailable now and will arrive later.

## Implemented behavior

- N0.3: one status table; historical specifications carry pointers to it.
- N0.5: explicit numerical-model dependency closure and library identity;
  UI/API/report changes do not invalidate capacity identity. Historical retained
  V2/V3 dispatch remains. New extended physics emits local V4, never rewrites old bytes.
- N1.1/N1.3/N1.4: retained raw maps plus separately hashed conditioned profiles,
  explicit bounded residual/uncertainty/shift policy, conservative power sample
  envelope, independent torque-error corners, varying-torque shaft efficiency
  applied once. Labelled CT/CQ fixtures exercise 0.1%, 1%, 5% noise over 60 seeds.
- N2.1: failed rotor commands fixed to zero, mass preserved, six-component trim
  solved again; quad failure certificate and reduced feasible octo fixtures.
- N2.2: steady +z axial climb with exact matching density/inflow/pitch sources,
  explicit negative body-relative air velocity and declared loads. Missing
  coverage or unsupported motion refuses, without hover extrapolation.
- N2.3/IP12: sourced correlated deterministic scenarios and common-payload
  case/sequence-energy checks. External structural/operational caps have
  separate source/scope/approval declarations and fixed-candidate feasibility
  checks. Nominal capacity stays distinct; no probability or flight approval.
- N0.4/N3.1/N3.2: explicit-unit original STL preview, numerical rotor/component
  links and transforms, CG/governing rotor limits, input/constraint comparison,
  draft-conflict preservation, exact completed JSON/PDF downloads. Browser
  integer/float round trips no longer invent input changes.
- N3.3: two timed automated full journeys and a retained backup recording.
  Actual human presenter rehearsals still need a presenter and spoken explanations.

[ADR-0005](../decisions/ADR-0005-conditioned-axial-profile.md) gives the bounded
conservatism argument; [validation](../validation/capacity-uncertainty.md) records
independent analytic comparators and refusal tests. Upper-envelope infeasibility
is not physical impossibility: conditioned-surrogate certificates are unsupported.
No motor-out bound is clamped to hide a numerical endpoint failure.

## Executed validation

| Check | Actual result |
|---|---|
| `.venv/bin/python -m pytest -q -m 'not backend'` | **511 passed**, 3 backend tests deselected, 35.49 s |
| `.venv/bin/python -m pytest -q reference_impl` | **118 passed**, 1.06 s |
| `.venv/bin/ruff check .` | Passed, including new scripts/tests |
| All `web/js/*.js` checked with Node module syntax | Passed |
| `tests/backend/test_sphere_smoke.py -m backend` | **1 passed**, 33.73 s; new pinned-image 20-iteration sphere, four stage logs retained |
| Standard Chromium workflow helper | Passed: actual clicks, completed downloads, conditioned-map form, native zoom, conflict, explicit-unit geometry, comparisons and failure-state render |
| Native declared-grid sampler probe | Capability-only pass: 25 coordinates, p/U/vorticity finite raw data, 3.97 s wall |

One existing FastAPI/Starlette `httpx` deprecation warning is reported; no assertion
was disabled. The other two optional backend fixtures remain unrun: they require
the vendor tutorial archive whose network destination was blocked during setup.
The 20-iteration smoke does not establish CFD convergence or aircraft validation.
The prior [performance baseline](performance-baseline-2026-10-05.md) remains the
unchanged baseline for its earlier code/workloads; these automated demo timings
are not new load-test or startup/throughput measurements. No performance optimization
was performed in this development slice.

## Browser evidence and reproducibility

Run `python scripts/qa/next_development_browser.py` with installed Playwright,
`/usr/bin/chromium` and `/usr/bin/ffmpeg`, after normal `.venv` setup. The helper
starts/stops its own fresh Uvicorn and isolated SQLite/artifact root, creates an
ephemeral in-process token, clears its input and never prints/saves the token.
It retains [machine evidence](assets/next-development/receipt.json), eleven
screenshots and local downloads. It checks the returned study POST response,
rather than assuming creation timestamps uniquely order fast automated runs.
See the existing [design audit](local-workbench-design-audit.md#standard-chromium-follow-up-5-october-2026)
for the performed journeys and remaining acceptance scope.

The successful recording is [next-development-backup.webm](../demo/assets/next-development-backup.webm),
20.08 s, 2,250,508 bytes, SHA-256
`4f0b1d406ca17b230100ddb560522f3196ecf314f9dc87fbfeaec5b9fb07c20f`.
Its 153 native screencast frames use timestamps and system FFmpeg; no failed
Playwright FFmpeg download was substituted as a verified bundled binary.
This is a browser-only technical recording with no narration or real client data.
Automated rehearsal durations are **1.361 s and 1.298 s**, including completed
JSON/PDF downloads. Human presentation duration and usability acceptance remain
unmeasured. [Exact example JSON](../demo/assets/synthetic-conditioned-study.json)
and [PDF](../demo/assets/synthetic-conditioned-study.pdf) are retained with their
hashes in the browser receipt. The frozen snapshot and four raw/conditioned
source files are retained beside them; `.venv/bin/python
scripts/qa/reproduce_conditioned_fixture.py` verified their hashes, original
semantic model/library identity and reproduced the headline and case bounds; the displayed ~4.25 kg fixture result is not an
aircraft payload claim.

Screenshot review verified preserved conflict choices, readable zoom/mobile
content, actual imported geometry, amber governing rotor limits and red failed
rotor. The policy controls have no engineering defaults. The required Product
Design Browser skill/shared override resource were unavailable, so this receipt
claims repository Chromium QA, not a completed Product Design plugin audit.

## Side investigations

[Registration](../validation/sphere-investigation-registration.md) was committed
as `1e58cd8` before new sampling executions. I01's
[recipe/hash receipt](native-grid-probe-2026-10-05.json),
[raw native samples](assets/native-grid/labelled_grid_p_U_vorticity.xy),
[dictionary](assets/native-grid/gridCapabilityProbe) and
[log](assets/native-grid/grid_probe.log) preserve the exact experiment.
Initial `simpleFoam -postProcess` probes registered only p/U and warned that
vorticity was absent. Those partial runs remain under the ignored investigation
root and did not pass. The generic `postProcess` driver explicitly reads all
three retained fields and emitted the complete 25x10 file at registered points.
This is a native supplied-point sampling capability, not interpolated-field
accuracy, a new plane protocol or a direction/refinement acceptance. All four
historical refused slices and every historical policy version remain unchanged.

I02 has a controlled domain/surface preregistration, explicit resource ceilings
and reproduction preconditions. The full campaign remains unrun. Reference
bundle reproduction and independent protocol review are missing; no cause is
assigned to the historical +2.65% correlation gap.

## Outstanding gates and delivery

N0.1/N0.2 and N4 need client scope/owner, real source-labelled inputs, approved
uncertainty/allowable policies and explicit recipients/sending instruction. The
[data request](../client/aircraft-data-request.md) was extended; no message sent.
N1.2 MILP and N2.4 variable-power work remain conditional on real-data triggers.
N5/IP13–15/IP17 require D01–D03 hosting/identity/confidentiality decisions. No
externally accessible deployment or production release is claimed.

The plan requires: “Do not merge or tag a physics release without its required
independent review and human engineering acceptance.” Existing Claude reviews
cover historical models only. Claude/cross-family review tooling is unavailable
in this runtime; author tests/derivations do not substitute for it. A review
branch preserves all implementation and evidence while those gates remain
pending. GitHub `main` remained at `802c63a` when checked; new physics stays on
the review branch. Repository setup/install/start instructions are already saved
in the cloud environment draft and continue to support the unchanged dependency
set. That saved draft is not a public app deployment.

Delivery verification: all implementation/evidence commits were pushed to
[`codex/next-development-plan`](https://github.com/PhysiCoreEngine12/Drone-Project/tree/codex/next-development-plan).
Draft PR creation was attempted with `gh pr create --draft --base main`; the
runtime returned `Post "https://api.github.com/graphql": Forbidden`. No PR was
created or claimed. The [comparison](https://github.com/PhysiCoreEngine12/Drone-Project/compare/main...codex/next-development-plan)
contains the full reviewable change. `api.github.com` was added to the saved
cloud network draft, preserving the three existing explicit tunnel destinations;
the platform returned `status=saved`, `requires_publish=true`. This saved draft
does not change current connectivity, provide API authentication or publish an
app. Apply/publish the environment settings and retry the API operation before
claiming PR delivery. Git push is already verified; no new credentials were
requested or exposed. Required model/client review remains separate from that
network prerequisite.
