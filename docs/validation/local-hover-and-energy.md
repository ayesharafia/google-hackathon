# Local hover and constant-segment verification

Scope: analytic software fixtures, with declared fixed pack, constant DC bus, static sourced body loads and retained isolated fixed-condition curves. Independent physics acceptance remains pending. Real installation effects, uncertainty and aircraft validation are not established.

## Equations

Candidate mass replaces installed payload entries: `m = sum(non-payload ledger masses) + payload`. CG uses the corresponding mass-weighted positions. The battery remains one installed ledger item.

For each rotor, `F_i = axis_i*T_i`. Its reaction couple is `-rotation_sign_i*axis_i*Q_i`; `Q` is the retained absorbed shaft-torque magnitude. Moments about the origin give linear allocation constraints. Final residuals are recomputed about candidate CG: `sum(cross(r_i-CG,F_i)+reaction_i) + body_moment_origin - cross(CG,body_force)`. Gravity passes through total CG. All six components must pass the retained numerical policy.

The electrical curve is either retained electrical watts, or supported shaft watts divided by one declared efficiency. Shaft watts must equal `Q*RPM*2*pi/60`; interpolation evaluates that product at the query point. The linear allocation currently accepts shaft curves only with constant torque. Electrical power versus thrust must be nondecreasing, convex and piecewise linear; absorbed torque versus thrust must be affine. No extrapolation or implicit density adjustment is used.

Rotor DC input power is bounded by its declared continuous watts and `bus_voltage*DC_input_current_limit`. The pack has its own corresponding bounds. These are DC bus currents; phase-current conversion is outside this model. Auxiliaries are added once to rotor electrical demand.

Pack usable energy is `battery_kg*Wh_per_kg*3600*usable_fraction*(1-held_reserve_fraction)`. A declared usable-energy value must agree. For ordered constant conditions, `E = sum(P_segment*duration_segment)`, carrying remaining energy across every segment. Reserve is already held back and is not applied again. Without cooling/reset evidence, total flight duration must fit every participating rotor map's continuous-duty coverage.

## Performed automated checks

`tests/drone/test_hover_pilot.py`: analytic symmetric lift, signed yaw couples, asymmetric payload CG allocation, power/auxiliary/energy limits, every required case, nonconvex/uncovered inputs, an independently recomputed infeasibility certificate, and a design whose zero-payload state is infeasible but positive payload is feasible. Failure injection checks time limits and optimizer success with an invalid wrench. Shaft consistency and efficiency are checked independently.

Chronological fixtures: segments that pass separately have a lower shared-pack capacity; a longer sequence cannot lift the empty aircraft; removing held reserve changes the bound by the analytic energy difference; unsupported transient profiles and continuous-duty coverage refuse.

`tests/projects/test_local_studies.py`: retained revision/source/model association, repeat submission, restart, edit retention, exact export hash, authentication/project scoping, corrupt/deleted map bytes, corrupt result bytes, incomplete inputs, and missing/altered V2 aggregate evidence.

These checks establish implemented fixture behavior, not measured rotor accuracy. Held-out measured interpolation errors, variable-power quadrature/refinement, actual motor/battery duty and installed-aircraft comparison remain pending. Native CFD was not rerun for this pure local model increment.
