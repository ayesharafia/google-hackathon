# MVP presenter guide

The demo shows a retained sphere verification pipeline and an illustrative
payload screening example. It does not calculate thrust from arbitrary STL
geometry or validate the client's aircraft. Use the software as built on
`mvp/3day`; record the actual commit before each presentation.

## Preparation

From a fresh terminal, follow the README setup and demo commands. Generating
the three runs is preparation, not part of the ten-minute presentation. Reuse
is permitted only after the driver verifies the retained input/output hashes.
Keep the API bound to `127.0.0.1`. Enter its session token privately before
recording. Never display or record the token itself.

Open `/web/results.html` and connect. Confirm that the sphere case loads,
all plot images render, and the native surface is visible. Keep the browser
at a readable desktop size. Record the page content only, excluding unrelated
tabs, the desktop, notifications and other applications. Use no microphone
unless the presenter intends to narrate. Keep the evidence ZIP alongside the
recording so reviewers can inspect the numbers without a running server.

For the frozen reviewed demonstration, run
`.venv/bin/python scripts/verify_baseline.py demo --check-only`, then
`.venv/bin/python scripts/verify_baseline.py demo`. The launcher checks the
inventory-bound preset before starting on localhost, default port 8766; use
`--port` for an available alternative. It selects `.backend/demo-reviewed`
regardless of an inherited data-root/image/bind-host setting. Historical
packages under `demo-final` share the run-group ID but predate the corrections
and are refused by this preset. The verified manifest SHA-256 is
`e5c2a75cca8b009aa69fce0205fced8e74442bab12aa26f0a42a5a335348cbc9`.
Identify the exported revision by ZIP SHA-256
`c3fe646f64e44a80d2ecb176aef374fcf475e08ff7b7fda31f8043ed193bf6c7`.
Fresh README commands rebuild with the corrected code; use a fresh publishing
root rather than an existing historical immutable package.

The frozen inventory and [production baseline record](../qa/production-baseline.md)
distinguish original solver, review and source revisions. These checks preserve
the old evidence; they do not attest to a future changed calculation, perform a
presentation rehearsal, or upgrade the envelope's pending review field.

Claude's independent code review passes the bounded MVP at f19cbeb (see §6 of
`docs/qa/independent_physics_review.md`). The retained envelope's review-pending
label is a separate machine attestation field and was not upgraded by this
external review. Its evidence level remains unverified.

If an image, source check, connection or download fails, stop and show the
failure. Do not replace it with a fabricated result or suppress the refusal.

## Ten-minute walkthrough

These are planned presentation durations. They are not recorded measurements.
The navigation steps below use the actual controls in the evidence desk.

| Time | Action and explanation | Evidence to show |
|---|---|---|
| 0:00–0:30 | Introduce the scope. Say: "This demo follows retained solver data through geometry checks, numerical checks, plots and export. The sphere is a verification case; the drone example is illustrative screening." | Case label and evidence status |
| 0:30–1:30 | Move to **Bring your geometry**. Select the generated sphere STL and explicitly choose **Metres**, then **Import and check**. Explain that STL supplies a surface, not mass, rotor performance or a complete CFD setup. | 20,480 triangles, closed surface, original/revision hashes and 3D preview |
| 1:30–2:00 | Click **Show missing-input readiness check**. Explain the listed missing fields. The template is intentionally incomplete; a clean STL does not make it execution-ready. | Actual blocking paths; no ready/validated claim |
| 2:00–3:00 | Return to the retained case. Show the pinned backend digest, run-group hash and the three mesh records. Expand **Native checks and residuals** for a mesh. | Cells, iterations, measured runtime/memory, native forces and residuals |
| 3:00–4:00 | Show **Loads and numerical checks**. Explain pressure plus viscous force, positive-x drag, native reconciliation and the separate last-two-window drift check. | Fine total Fx about 0.44007 N and Cd 1.12062; all three native matches accepted |
| 4:00–5:00 | Show **What changes with the mesh**. Explain the untuned correlation difference and the qualifications on GCI. | Cd 1.14689 / 1.12491 / 1.12062; reference 1.09173; fine difference +2.65%; order-capped GCI about 0.408%; observed-order GCI about 0.110% |
| 5:00–6:00 | Show **Through the flow**. Switch **Mesh** from Fine to Medium or Coarse and back. Expand **Recipe and source hashes**. Explain shared colour bounds and nominal y=0 projection; vectors and streamlines are in-plane views. | Real pressure, speed and native vorticity plots; recipe and source hashes |
| 6:00–7:00 | Show the wake profile and histories, then the native surface. Switch **Colour field** from pressure to shear, orbit with a drag and use **Reset view**. | Native face-constant values, units/extrema, steady iteration histories, no smoothing used for loads |
| 7:00–7:30 | Show **What the record supports** and **Requests the data refuses**. Explain that interpretation is a metric-bound template and unsupported requests are refused by the engine. | Laminar y+, absent physical mean, missing blades and independent comparison ranges |
| 7:30–9:30 | Click **Calculate example capacity**. Show both cases and the limiting climb case, then **Test a missing case**, and restore the example. Expand bound sources and assumptions. Mention the separate A/B/C battery exercise. | 52.23 kg illustrative ceiling; hover 73.68 kg; climb 52.23 kg; missing case removes headline; `screening_only` |
| 9:30–10:00 | Click **Export evidence ZIP**, then **Save evidence ZIP**. Finish with the inputs needed for a real aircraft study. | Downloaded package, hashes, limitations and input list |

## What each number means

For the retained sphere, density is 1 kg/m³, speed is 1 m/s, diameter is 1 m
and kinematic viscosity is 0.01 m²/s. Thus Re = 100. Cd uses reference area
πD²/4. The 812 index is a steady solver iteration, not elapsed physical time.
The empirical Schiller–Naumann correlation is a comparison, not an exact answer.
Do not attribute the observed difference to a specific error source without
additional evidence. The GCI is qualified mesh sensitivity; it excludes domain,
geometry, boundary and model uncertainty, and asymptotic convergence is unproven.

For the illustrative drone, empty mass is 65 kg. Hover supplies 1360 N world-z
force; climb supplies 1220 N with required upward acceleration 0.6 m/s².
The calculation is `Fz / (9.80665 + az) - empty_mass`. Each supplied operating
point must also pass source binding and its declared power/energy limits. Those
checks do not establish the physical validity of supplied power or energy. The
acceleration is an instantaneous margin; duration checks constant-point energy,
not an integrated accelerating trajectory. The headline
is the minimum across every declared case. Missing one case blocks it.
The result assumes supplied performance already accounts for environment,
attitude and reserve policy. Trim, allocation, structure and actual rotor
performance remain unresolved. Case energies are checked independently; this
MVP does not sum a sequential mission's energy.

A/B/C use a separate eight-rotor ideal-hover battery fixed-point exercise.
Their masses do not resize or validate the four-rotor capacity example. A
diverged exercise is a failure to obtain a solution, not an aircraft mass.

## Claims and handover

Say that numbers trace to retained evidence and solver-native reconciliation.
Say that the software refuses unsupported results. Keep "VERIFICATION CASE"
and "Illustrative example inputs" visible when discussing their numbers.
Do not claim aircraft validation, certification, total accuracy, payload inferred
from shape alone, a fixed 750 kg target, or sequential-mission endurance.

Real aircraft screening needs the approved component geometry and transforms,
mass ledger, all mission conditions, rotor thrust/power data at sustained limits,
motor/power limits and usable battery energy. Source records must bind to that
exact design and those operating cases. Geometry by itself is insufficient.

## Rehearsal record

Complete this table only after performing each full walkthrough from a fresh
terminal. Use a clock for actual timing; note stalls, refusals and corrective
actions. A functional browser QA pass or prepared script is not a timed narrated
presentation. Recheck the backup video's readability and completeness by replaying
it after saving.

| Attempt | Actual date/time | Reviewed commit | Actual duration | Complete scope? | Issues and corrective action | Video path/hash |
|---|---|---|---|---|---|---|
| 1 | Pending | Pending | Pending | Pending | Pending | Pending |
| 2 | Pending | Pending | Pending | Pending | Pending | Pending |

As of 2026-10-03, the primary agent could open QuickTime and its recording menu,
but the automation tool could not expose or capture the recording controls.
No backup video has been saved or verified. Both full timed presentation
rehearsals remain pending. These limits must remain visible in the release gate.

## Release gate

Keep the branch unmerged and untagged until the independent physics findings
are resolved, the Day 3 product gate is signed off, both full rehearsals are
recorded and a playable backup exists. The human must approve final client
report wording under master plan §1.5/§13. A model review cannot supply that
human approval or certify aircraft performance.

Sources: master `plan.md` §1.5/§7/§13; three-day plan §8/§10/§11/§12;
`docs/validation/sphere_re100_loads.md`; retained `results.json`; illustrative
`docs/demo/example_multirotor.yaml`; `docs/qa/results_page_checklist.md`.

## Next-development workbench rehearsal receipt, 5 October 2026

The current opt-in local workbench journey uses synthetic CT/CQ hover/climb maps,
explicit conditioning bounds, frozen V4 studies and JSON/PDF exports. Introduce
it as model/software demonstration only. The original MVP walkthrough above
retains its historical scope and separate evidence identities.

Two **automated** complete create → freeze → evaluate → download JSON/PDF
rehearsals are timed in [the Chromium receipt](../qa/assets/next-development/receipt.json).
Their machine-click durations are not human speaking or presentation durations.
Both downloads finish and bind the retained bytes. A full browser-only
[backup recording](assets/next-development-backup.webm) is retained with its
SHA-256 in the receipt. Native zoom/mobile/conflict/geometry/comparison checks
appear in the recording; there is no narration, client data or plaintext token.
This recording is a technical backup, not a rehearsed client presentation.

Before presenting: run the helper, check the target commit, inspect data scope,
verify the two downloaded reports and rehearse twice **with the actual human
presenter**, including explanations and questions. Log actual speaking durations
and follow-ups here. Those human rehearsals remain pending. For a real design,
wait for client-approved inputs, independent model review and engineer-owned
scope/tolerances. Do not substitute this fast automated recording for those gates.
