# Conditioned capacity and deterministic uncertainty validation

5 October 2026. Analytic fixtures only. Implementation review is pending; this
receipt is author verification, not independent physics or client acceptance.

Tests exercise CT=.12, CQ=.006, diameter=.8 m, 11 fixed RPM coordinates,
Pshaft=Q*omega, declared eta=.85, and density computed from explicit pressure
and temperature. The climb fixture applies an artificial declared torque
multiplier; it is not a physical climb law. Bounds, duties and moment allowances
are synthetic. No real data, density scaling, resized battery or flight limit
is inferred.

`test_conditioning_and_axial.py` runs 20 deterministic seeds at each of 0.1%,
1% and 5% noise. Every fitted power sample bounds its declared target envelope;
all checked capacities are no greater than the exact ideal comparator, with
identical thrust/RPM coordinates. Both torque/electrical noise measurements are
independent perturbations around ideal, not compounded noise. Independent
per-rotor torque corners are checked by the summed absolute axis error; tiny
allowances and excessive relative residuals refuse. Shaft and electrical
versions of the same varying-torque curve agree after efficiency is applied once.
A deliberately nonconvex high-power sample refuses when the declared shift limit
is zero. Forged stored power coefficients refuse without refitting history.

The known quad motor-out loses supported trim and retains a checked certificate.
An independently constructed square-octo fixture remains feasible with reduced
capacity. Failed rotor commands are exactly zero; hardware mass remains.
The API realistic octo example has its own full freeze/run/export/restart check.
Missing climb inflow coverage, a reversed air-relative sign and unknown failed
IDs refuse. Raw source hashes and conditioned policy receipts survive restart;
JSON and deterministic PDF exports bind exact retained bytes.

`test_scenario_limits.py` uses an independently solvable uniform-rotor analytic
capacity: nominal=153.6/G0-12 kg, joint scenario=138.24/G0-13 kg. The joint change
combines one mass, atmosphere and matching retained map, preserving correlation.
A separately sourced 1 kg structural cap leaves nominal/model/scenario values
distinct. Missing matching density yields incomplete uncertainty coverage and
no envelope. Proposed caps do not count as approved declarations. A 0 kg cap
below a nonzero feasible interval is not falsely reported feasible. Contract
validation rejects forged minima, omitted common-case checks, inconsistent caps
and altered chronological energy. v1 refuses extended declarations.

The local V4 evidence checks do not independently reconstruct an aircraft from
exported scalar values. Frozen inputs and raw/conditioned source hashes remain
necessary for reproduction. Independent review must verify policy assumptions,
all refusal semantics and the conditioned-surrogate infeasibility qualification.

A strict existing bound check can classify trig-coordinate motor-out candidates
unresolved at a floating-point endpoint. It has not been relaxed or clamped.
The exact-square analytic acceptance case avoids conflating this numerical
endpoint limitation with physical infeasibility. Real maps/geometry require
engineer-owned tolerances and held-out measurements before any acceptance claim.
