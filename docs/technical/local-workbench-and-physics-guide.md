# Local design workbench: code, data and physics

Checkpoint: 5 October 2026. This extends the historical MVP guide. Execution is local, with synthetic examples explicitly labelled. It does not establish aircraft validation, operational payload allowance, hosted security or engineering approval.

## The user journey

Open `/web/workbench.html` on the local API server. In private local mode, connect once with its configured workspace access token. An HttpOnly, SameSite cookie remembers this browser for 30 days across the workbench and evidence desk, including refreshes and server restarts. The token is not stored in browser storage. Use “Forget this browser” to revoke that browser’s access; rotating the server token invalidates all remembered browsers. Create a project with explicit unknowns, or create the labelled hover fixture. Author the mass ledger, payload placement, fixed pack, required cases, rotor locations/limits and chronological segments. Import an eligible `rotor_map_v1` JSON source and bind its returned original-byte hash to matching rotors.

For an open shared workspace, start the server with `PHYSIMESH_PUBLIC_ACCESS=1` and no `PHYSIMESH_API_TOKEN`. Anyone with the server or tunnel URL can view and edit projects, upload geometry and save drafts without a token. Both desks open automatically and omit the connection and forget-browser controls. Public access stays enabled across refreshes and server restarts when that environment setting is kept. Hosted mode rejects this setting and continues to use individual project authorization.

In **Aircraft geometry**, select one or more original STL files, explicitly choose their common source units, then select **Upload and preview**. The preview supports orbit, zoom and reset. Select **Save draft** to attach the import record and original files to the project; reopening restores the preview from authenticated, integrity-checked retained bytes. Uploading replacement files or removing geometry changes only the draft until saved. Frozen revisions retain their earlier geometry. A malformed or oversized upload leaves the current draft geometry unchanged. The existing default intake limits are 50 MB and one million triangles in total.

An STL preview does not assign component roles, supply mass/inertia or establish mesh/CFD readiness. Source coordinates are converted to metres without inferring alignment with the declared rotor layout. Draft JSON exports contain immutable geometry references; original STL bytes remain in the server data root and must accompany that data root when transferring a project.

Save the draft, inspect mass/readiness, freeze the saved version, then evaluate. Dirty inputs disable freeze/evaluation. Edits never alter an existing revision or result. A frozen revision is a software snapshot, not aircraft approval. Inspect every case, the common-payload checks, residuals and any chronological energy ledger. Export the exact JSON or its source-bound PDF. Compare retained studies within the same project; changed inputs do not prove causation.

## Modules and responsibilities

| Code | Responsibility |
|---|---|
| `projects/repository.py` | Repository protocol, records and conflict/not-found exceptions |
| `projects/sqlite.py` | Transactional SQLite projects, expected-version saves, immutable revision and study associations |
| `projects/service.py` | Draft parsing, canonical snapshots, project creation/save/freeze |
| `projects/geometry.py` | Saved import/units/transform binding and retained STL byte integrity |
| `projects/performance.py` | Original performance-source retention and integrity checks |
| `projects/studies.py` | Frozen inputs/source/model binding, evaluation, first accepted result, read/export |
| `projects/reports.py` | Deterministic qualified PDF and input-aware retained comparisons |
| `api/projects.py` | Local and hosted project HTTP routes, saved-input inspection aggregation and error/status translation |
| `drone/authoring.py` | Installed and candidate mass/CG calculations |
| `drone/performance.py` | Typed rotor map, coverage, interpolation and restricted convex profile |
| `drone/trim.py` | Eligibility, linear constraints, allocation, certificate and independent recomputation |
| `drone/capacity.py` | Required-case aggregation and checked common payload |
| `drone/mission_capacity.py` | Joint allocation and chronological constant-power fixed-pack ledger |
| `drone/local_results.py` | Local V3 consistency and exact known-producer historical read policies |
| `web/js/input-editors.js` | Native authoring, explicit unknowns, map import and saved-input inspection |
| `web/js/workbench.js` | Serialized actions, version/dirty state, history and downloads |
| `web/js/geometry-upload.js` | STL upload, draft attachment/removal, retained preview restoration |
| `web/js/study-view.js` | Qualified outcome/energy/comparison display and keyboard-scrollable tables |
| `web/js/viewer3d.js` | Real declared rotor disks/axes and candidate CG; orbit/zoom/reset |

Paths in the table are under `src/physimesh/` except browser files. The viewer does not invent an airframe when CAD is unavailable. Workbench geometry and sphere native-field display use separate previews.

## Persistence and identities

The data root owns the SQLite ledger and content-addressed artifacts. Draft save uses `expected_version`; a stale writer receives a conflict instead of overwriting another version. Freeze binds canonical JSON to its SHA-256 and exact draft version. Study submission resolves that immutable revision and verifies every bound map's bytes before evaluation.

The study specification binds project/revision, canonical snapshot, source hashes, `convex_static_hover_v1`, the fingerprint of Python source files under `src/physimesh`, NumPy/SciPy versions, result schema and pending engineering approval. This is documentary local source identity, not a signed deployed-build or approver attestation. Changed source may cause numeric comparison to be withheld even when its equations are unchanged.

Repeated submissions retain one winning result association. Unresolved observations remain immutable. This synchronous local protocol does not yet supply recoverable attempts, cancellation, leases or multi-host worker fencing.

## Supported physical model

The first profile is static hover in `x_forward_y_left_z_up` body coordinates and `ENU_z_up` world coordinates. Attitude, translation/inflow, acceleration, angular velocity and angular acceleration must be zero. It accepts one candidate payload location, fixed rotor centres/unit axes, explicit sourced body loads about the origin, and a fixed battery on a declared constant DC bus.

Maps must cover the declared density, zero inflow, pitch, RPM interval and continuous duty. There is no extrapolation or implicit density scaling. Thrust is strictly increasing in RPM; absorbed shaft torque is affine in thrust; electrical demand is nondecreasing convex piecewise-linear in thrust. Shaft-power maps are eligible for linear trim only when torque is constant. General imported maps may be queryable while ineligible for this allocation model.

Ground effect, installation interference, airframe-load prediction, motion, sag, thermal dynamics, battery resizing, variable-power trajectories and uncertainty scenarios remain outside this profile. Missing inputs produce a reasoned refusal, never an invented capacity.

## Equations and conventions

Candidate payload replaces the payload ledger entries. For non-payload ledger items `m_j` at `r_j`, candidate payload `p` at `r_p`:

```text
m0 = sum(m_j)
m = m0 + p
CG = (sum(m_j*r_j) + p*r_p) / m
rho = absolute_pressure / (R_air * absolute_temperature)
Omega = RPM * 2*pi/60
```

The density equation is a declared ideal-gas air-state calculation; it does not authorize changing a rotor curve to another density. Mass completeness and fixed-pack consistency are checked separately.

For rotor unit axis `a_i`, positive thrust `T_i`, absorbed shaft torque magnitude `Q_i`, right-hand shaft rotation sign `s_i` and rotor centre `r_i`:

```text
F_i = a_i*T_i
reaction_i = -s_i*a_i*Q_i
F_residual = sum(F_i) + F_body + (0,0,-m*g0)
M_residual_CG = sum((r_i-CG) cross F_i + reaction_i)
                + M_body_origin - CG cross F_body
```

Gravity passes through total CG. Torque sign is defined about the positive axis; no viewing-direction CW/CCW shorthand is inferred. The six balance constraints are assembled about the fixed origin, where payload mass and its gravity moment enter linearly. Final forces and moments are independently recomputed about the actual payload-dependent CG.

```text
Q(T) = torque_slope*T + torque_offset
P_e(T) = max_k(power_slope_k*T + power_offset_k)
P_shaft = Q*Omega
P_e = P_shaft / declared_efficiency     [shaft map only; applied once]
P_total = sum(P_e_i) + P_aux
I_i = P_e_i / V_bus
```

Stored shaft point watts must agree with `Q*Omega`. Query interpolation evaluates that product at the requested operating point. Electrical-power maps are used as electrical watts and receive no second efficiency conversion.

Rotor input power is bounded by both continuous watts and `V_bus*I_rotor_limit`. The pack separately bounds total demand by continuous pack watts and `V_bus*I_pack_limit`. Currents here are DC input currents; motor phase-current conversions are not modelled.

The bounded linear program uses rotor thrust variables, electrical-power epigraph variables and one payload variable. It maximizes payload subject to force/moment balance, covered thrust bounds, electrical limits, declared payload domain and energy rows. At a fixed-payload verification query, payload is held constant and demand is minimized. A solver success flag alone never establishes feasibility.

Each resulting command is converted back through its map. Independent recomputation must satisfy all six retained residual tolerances, actual power/current, finite bounds and RPM limits. Numerical tolerances are fixture choices, not flight acceptance tolerances. Solver/runtime/recomputation failures after eligibility are unresolved; a numerical optimum is reported as a checked local payload lower bound rather than a demonstrated global aircraft maximum.

## Required alternatives and chronological energy

For alternatives, calculate each required case bound. Take the minimum only after all required cases pass again at exactly that common payload. Optional unused cases do not control the headline. Zero payload is not assumed feasible: moving the CG can make a positive-payload state feasible when the empty configuration is not. The code therefore does not blindly bisect from zero.

For a fixed installed pack:

```text
E_usable = battery_kg * Wh_per_kg * 3600
           * usable_fraction * (1-held_reserve_fraction)
E_case = P_case * declared_case_duration
E_mission = sum(P_segment * segment_duration)
E_remaining_after_k = E_usable - sum(E_segment_1 ... E_segment_k)
```

Declared usable energy must agree with the mass-derived pack budget. Held reserve is applied once. Each chronological segment references an eligible case, explicit duration/source and `power_profile=constant`. Joint allocation shares one payload across all participating conditions and constrains their time-weighted power against the single reserved budget. Independent fixed-payload case solves then recompute the powers used in the chronological ledger.

Required standalone cases retain their own declared duration constraints. Optional segment-only cases use their covered segment duty. With no cooling/reset model, the complete sequence duration must fit participating continuous-duty coverage. Constant-power integration is exact multiplication; it does not need a quadrature convergence claim.

A binding shared-pack energy limit can be lower than every individual case bound. The record then uses `aggregate_limit=sequence_energy` and no invented limiting case. Otherwise the identified participating case must attain the common bound. Disagreement with individual participating bounds is retained as unresolved.

## Four outcomes and evidence

| Outcome | Meaning |
|---|---|
| feasible | Independently recomputed candidate satisfies the declared restricted model |
| infeasible | A checked nonnegative linear-combination certificate contradicts the complete supported physical constraints |
| unsupported | Missing physics, eligibility, duty or source/domain coverage prevents the claim |
| unresolved | Numerical failure, time limit, invalid recomputation or disagreement prevents a conclusion |

Certificates retain row scaling, multipliers, finite-bound minimum, contradiction gap, rounding guard and bound origins. Coverage endpoints and analyst payload domains are distinguished from physical limits. A coverage/domain-dependent contradiction, or unknown admissible RPM states outside the retained source interval, cannot become a claim of physical infeasibility. Read-time contract validation checks consistency; it does not independently rederive an old certificate or authenticate an engineering approval.

## Contracts, comparisons and reports

New local results use `local_mission_capacity_v3`. The approved `AircraftStudyV1/V2` contracts and sphere `ResultsV1` remain separate. Known historical local V2 generations select their original acceptance rules only through exact producer fingerprints. Unknown V2 records must satisfy stronger consistency checks and may refuse if incomplete. No arbitrary historical working-tree compatibility is promised. Historical records display a qualifier and are never silently reassessed or migrated in place.

Comparison requires two retained records in one project. Arrays are compared as whole values, not guessed component identities. Numeric delta is shown only for matching model identity, schema, data scope and mission semantics with two feasible outcomes. Complete changes remain inspectable; they do not prove cause.

PDF generation resolves verified retained JSON and the exact frozen snapshot without running the model. It embeds result hash, snapshot/study identity, renderer source fingerprint and ReportLab version. Deterministic metadata uses a fixed timestamp; actual study retention time is in the ledger. Headlines are rounded down to two decimals, with exact values and complete evidence/input appendices retained. Historical wording, unsupported/unresolved outcomes and approval status survive export. The exact JSON remains authoritative. Bounded rendering refuses oversized reports with a JSON fallback.

## Operation, verification and unfinished work

Run the existing local app with `PHYSIMESH_API_TOKEN` and a persistent `PHYSIMESH_DATA_ROOT`; use a loopback bind. Open the workbench through the HTTP server, not `file://`. A static file cannot provide protected project APIs. Follow the repository's existing environment/backend setup when using sphere evidence; local hover evaluation does not execute OpenFOAM.

Verification at this checkpoint: 490 tests passed with three backend tests deselected; 118 reference tests passed; focused report checks passed after pagination changes; Ruff and JavaScript syntax checks passed. GitHub unit/lint checks passed on `f6fc497`, which merged through PR #5 into `main` at `8fe3cf7`. Claude accepted the stated synthetic local model and historical policy correction in the linked review receipts. The evidence verifier checks original records/package/native-output/vendor bytes and exact historical Git source separately; it does not claim a new solver run or numerical reproduction from that historical source.

See [browser audit](../qa/local-workbench-design-audit.md), [PDF checks](../qa/local-reports.md), [historical review](../reviews/2026-10-05-historical-contract-claude.md), [equation fixtures](../validation/local-hover-and-energy.md) and [work order](../plans/2026-10-04-implementation-plan.md).

Next independent local work: deterministic correlated uncertainty scenarios and reviewed external allowable limits, complete assembly authoring/repair, and recoverable execution. Historical-source numerical reproduction remains pending. Hosted access/operations are deferred by the user. Real geometry, measured rotor/installation data, validation tolerances and named human engineering acceptance remain required before client aircraft performance claims.

## Conditioned hover/climb and failure-state pilot

The opt-in model is `convex_axial_capacity_v2` / local result V4. Create the
**synthetic noisy hover/climb** or **synthetic octo motor-out** example in the
workbench, inspect declarations, freeze and evaluate. They are analytic CT/CQ
fixtures, including synthetic uncertainty bounds and moment allowances. The
original labelled hover example retains v1/V3 behavior.

In **Condition a retained rotor map**, supply raw SHA-256, policy source, maximum
relative torque residual, power/torque uncertainty and maximum hull shift/peak
power fraction. Every number is required; no client tolerance is supplied.
Conditioning retains a separate derived hash and preserves raw bytes. Binding
the result to matching rotors is an explicit second action. Save/freeze after
binding. Per-case matching-inflow source overrides remain separate.

In each case, declare failed rotor IDs or exact axial inflow/world/body velocities,
source overrides and per-axis torque-band moment allowances with source. For
steady positive axial climb, body air-relative velocity is the negative of
world climb velocity at zero attitude. Active sources must match density,
inflow and pitch. Arbitrary attitudes, acceleration, inflow extrapolation,
thermal/sag and general fault aerodynamics remain unsupported.

**Deterministic joint scenarios** and **External payload caps** accept sourced
versioned JSON arrays with explicit Apply-to-draft actions. See the schemas in
`drone/scenarios.py`. Up to 16 of each are supported. The result displays nominal
model capacity, deterministic common envelope and checked capped payload
separately. Proposed caps are not declared approved; caller approval claims are
not authenticated here. A capped payload below a feasible interval may refuse.

Import STL with explicit source units under **Airframe geometry and rotor links**.
Numeric transforms and rotor centres use the declared body frame. Choose rotor
component references, save and reopen to verify placement. Geometry does not
infer mass or loads. The preview shows retained airframe geometry, rotor disks,
CG and current governing-case rotor limits. Editing inputs clears stale results.
Comparisons show frozen input and active-constraint changes; causal attribution
is not inferred. Integer/float JSON serialization alone is not an input change.

A 409 draft conflict preserves unsaved inputs in a modal: export them, keep
editing, or explicitly replace with the newest saved draft. Tokens remain in
page memory. New API endpoints remain bearer-protected:
`POST /api/drone/projects/performance-sources/{raw_hash}/condition` with
`{"policy": {...}}`, realistic/motorout example POSTs, and
`GET /api/drone/projects/geometry-sources/{hash}` for verified original STL bytes.

Run browser acceptance with a Python containing Playwright and system Chromium
and FFmpeg: `python scripts/qa/next_development_browser.py`. It starts/stops its
own fresh isolated server and ephemeral credential, retains screenshots/receipt
in `docs/qa/assets/next-development` and keeps downloads/database/recording in an
ignored runtime directory. It uses actual Chromium native settings for 200%
zoom and verifies DPR/layout reflow. Two timings are automated rehearsals,
not human presenter timings or an API performance benchmark.
