`evaluate_static_wrench_solve` uses `evaluation="bounded_static_wrench_solve_experimental"`.

Exact root keys: `evaluation`, `assembly_template`, `rotor_speed_bounds`, `required_net_force_body_n`, `required_net_moment_cg_body_nm`, `absolute_force_tolerance_n`, `absolute_moment_tolerance_nm`, `max_evaluations`.

Template: accepted rotor assembly; hover nodes must omit `angular_speed_rad_s`. Bounds follow rotor order; each has exactly `node`, `angular_speed_bracket_rad_s`, `initial_angular_speed_rad_s`. Brackets are positive, closed; initial speeds lie inside. Speeds use rad/s, not RPM. Air, mass, CG, geometry and axes stay fixed. Targets are body-frame 3-vectors: force in N, moment about CG in N*m. Tolerances are positive scalars in N and N*m.

Limits: 1–15 rotors; 1–512 annuli per rotor; 2–64 actual assembly evaluations; `max_evaluations * sum(annuli) <= 32768`; JSON <=32768 values. Finite differences and a fresh final evaluation count; reserve one slot for the final evaluation.

SciPy `trf` performs bounded local least squares on six residuals normalized by their respective tolerances, running the actual assembly at every probe. Choose the observed row minimizing the maximum absolute normalized residual; final recomputation must equal that row exactly.

`RESIDUAL_MET`, `EVALUATION_LIMIT`, `SOLVER_STOPPED` all return `COMPUTED_EXPERIMENTAL`. Only final maximum absolute normalized residual <=1 permits `RESIDUAL_MET`; other outcomes do not prove no solution exists.

All qualification: `NOT_ESTABLISHED`; evidence: `unverified`; aircraft/feasibility: `None`. No physical trim, control authority, uniqueness, global feasibility, power/thermal, installed-flight or API qualification.

Hash actual raw records; inner graph result SHA is checked for syntax only. Preflight: `GRAPH_INVALID`, no hash. Execution failure: atomic `EXECUTION_FAILED`, retained hash.
