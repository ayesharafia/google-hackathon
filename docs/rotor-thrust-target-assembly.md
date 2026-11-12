`rotor_thrust_target_assembly.py`: `evaluate_rotor_thrust_target_assembly(request)`.

Exact request shape (`…` expands the template):

```json
{
  "evaluation": "prescribed_rotor_thrust_target_assembly_experimental",
  "assembly_template": { "…": "…" },
  "targets": [{
    "node": "r1",
    "target_thrust_n": 100,
    "angular_speed_bracket_rad_s": [10, 500],
    "absolute_thrust_tolerance_n": 0.01,
    "max_evaluations": 64
  }]
}
```

Template: accepted `ra` request, except every hover node must **omit** `angular_speed_rad_s`, preventing conflicting prescriptions. Targets exactly follow rotor order. Mass, CG, geometry, axes and air stay caller-fixed.

Before any model: JSON ≤32768 values before deepcopy; all structural checks; temporary speed 1 for `ra` preflight and density 1 for `ht._preflight`, including geometry, evaluation and declarations. Require 1–15 rotors, 2–64 evaluations each, 1–512 annuli each, Σannuli≤8192 and Σ(evaluations×annuli)≤32768.

Deepcopy the original air node into an edgeless graph targeting density/gravity; call `ag` once. Bind its density into one independent `ht` inverse per rotor. Require every `TARGET_RESIDUAL_MET`. Substitute solved speeds; call `ra`, recomputing common air and rotors. Recheck target thrust tolerances and best-candidate torque with relative/absolute 1e-12 numerical equality.

Outputs nest air scalars, ordered node+inverse outputs and assembly outputs, with matching units. Transfers contain density and node+solved speeds. Stages `air`, `rotor_<node>`, `assembly` hash actual full requests/raw results; inner candidate hashes remain data, without independent raw-candidate proof.

`GRAPH_INVALID`: no hash. Execution failure is atomic: retained request hash, generic reason, empty stages/transfers/outputs/units.

Success: `COMPUTED_EXPERIMENTAL`, unverified; all three qualification labels remain `NOT_ESTABLISHED`; aircraft/feasibility null. Frozen isolated small-angle models add no physics, trim, allocation, interference, loss/Re/Mach polars or installed-flight/power qualification. Residual tolerance establishes no physical accuracy.
