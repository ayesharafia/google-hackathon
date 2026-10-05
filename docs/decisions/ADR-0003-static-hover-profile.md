# ADR-0003: first local map-based trim profile

Status: implementation design within the approved local Pilot-1 path; physics acceptance pending independent review. This does not expand a validated aircraft envelope.

Use a restricted static-hover allocation model first. Rotor thrust increases strictly with RPM, absorbed torque is affine in thrust, and electrical power is convex, nondecreasing and piecewise linear in thrust over one declared covered interval. Axes/positions are fixed. Body loads are declared about the body origin; attitude, angular rates and translational acceleration are zero. Maps match the declared density/inflow/pitch. Sources and continuous duty are explicit.

A generic nonlinear trim solver was considered, but would need multistart/nonconvergence treatment before it could support the same fixture journey. Bisection in payload was considered, but shifted CG and thrust floors can make zero payload infeasible while a positive payload is feasible. The restricted model instead defines bounded linear constraints in rotor thrust, electrical-power epigraph variables and payload. It checks each candidate independently and verifies the mission headline at one compatible payload.

Convex power curves are represented exactly by the maximum of their affine segments inside the retained thrust range. Force balance and moments about a fixed origin are linear in thrust/payload. The final solution is recomputed independently about the payload-dependent CG using interpolated source values. All six residuals, actual powers and limits must pass. Time limits and numerical failures remain unresolved. Physical infeasibility requires an independently checked bound or nonnegative linear-combination certificate, never just an optimizer status.

This is not a general aircraft optimizer or a global physical maximum. Unsupported nonlinear torque, nonconvex power, uncovered intervals, inflow, maneuvers or thermal/sag behavior refuse. Original screening and result contracts remain unchanged. Initial outputs identify frozen draft scope and pending engineering approval. Later methods require separately versioned eligibility and review.

Numerical residual policy and solver limits are software/fixture choices, not client flight-acceptance tolerances. Use SciPy's installed HiGHS implementation and retain its version: [official linear-programming interface](https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html). Real measurement coverage, installation discrepancy and independent validation remain separate gates.

The local V2 contract adds explicitly sourced constant-condition chronological segments. The joint program shares payload across required cases, sums their time-weighted electrical epigraphs and enforces one already-reserved pack budget. Independent fixed-payload solves recompute the actual powers and six-component wrench before the segment ledger is retained. A binding aggregate energy limit has no invented limiting case. Constant-power integration is exact; variable-power quadrature remains unsupported.

Shaft-map point watts must equal absorbed torque times angular speed. Query interpolation computes that product before applying efficiency once. Since a varying torque introduces a quadratic product between RPM samples, the initial linear trim accepts shaft curves only with constant torque. General shaft curves remain importable/queryable but ineligible for this allocation method.

Rotation sign is right-hand shaft rotation about the declared positive rotor axis. Airframe reaction torque has the opposite sign. No CW/CCW viewing-direction shorthand is inferred. Explicit angular velocity and angular acceleration must both be zero; unsupported physical case declarations refuse.
