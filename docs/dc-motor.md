# Experimental DC motor

`evaluate_dc_motor` specifies the strict `constant_parameter_dc_motor_experimental` evaluation. Its scope is a steady constant-parameter DC equivalent at one prescribed operating point. There is no API endpoint or direct V93 integration yet. The code remains experimental and unverified; results establish no physical validation, safety, or feasibility.

## Model and conventions

[Mark Drela's MIT motor theory](https://web.mit.edu/drela/Public/web/qprop/motor1_theory.pdf) defines inverse torque constant `KQ` in A/Nm and speed constant `KV` in rad/s/V. This model instead uses one constant `k = 1/KQ = 1/KV`, expressed consistently as Nm/A or V*s/rad. Sharing this constant between torque and back-EMF preserves SI energy consistency.

For shaft torque `Q`, angular speed `omega`, terminal resistance `R`, and zero-torque current `I0`:

```text
I = Q/k + I0
E = k*omega
V = E + I*R
Pshaft = Q*omega
Pelectrical = V*I
Pcopper = I*I*R
Pfriction = E*I0
Ploss = Pcopper + Pfriction
residual = Pelectrical - (Pshaft + Ploss)
accounted = Pshaft + Ploss
eta = Pshaft/(Pshaft + Ploss), when accounted > 0
```

`Pfriction` is the declared equivalent zero-torque loss term. Constant `R` and `I0` are caller assumptions, not an inferred performance map.

[Maxon's motor-constant reference](https://support.maxongroup.com/hc/en-us/articles/360005873794-Motor-constants) distinguishes SI torque constant from inverse speed constant. Its separately named motor constant must not be confused with this document's `k`.

## Request contract

The request root has exactly `evaluation`, `parameters`, `operating_point`, and `declared_limits`; numeric units are encoded in the named keys, and unknown fields are strictly rejected at every level.

The request declares:

| Group | Required fields |
|---|---|
| Parameters | `motor_constant_si`, `terminal_resistance_ohm`, `zero_torque_current_a`, `parameter_source`, `applicability_declaration` |
| Operating point | `angular_speed_rad_s`, `shaft_torque_nm` |
| Declared limits | `maximum_current_a`, `maximum_terminal_voltage_v`, `maximum_angular_speed_rad_s`, `maximum_shaft_torque_nm`, `limit_source` |

`motor_constant_si` and angular speed must be positive. Resistance, zero-torque current, and shaft torque may be zero but cannot be negative. Every declared maximum must be positive. Source strings must be nonblank.

The applicability declaration must literally equal `constant_parameter_dc_equivalent_only`. A recorded source documents provenance; citing a model reference does not establish measured motor parameters.

Numeric inputs must be builtin integers or floats, finite, and normal when nonzero. Booleans are rejected as numbers. Nonfinite values and nonzero subnormals are rejected.

Before deep copying, validation bounds the builtin JSON request to 4096 visited values, depth 10, 256 entries per container, and 2000 characters per string. Unsupported structures and invalid declarations return `GRAPH_INVALID` without a request hash.

## Results and arithmetic

Outputs report current, back-EMF, required terminal voltage, shaft power, electrical input power, copper loss, friction loss, total loss, energy-balance residual, efficiency, declared-limit status, and four individual limit checks.

Each check compares current, voltage, angular speed, or shaft torque with its declared maximum. Comparisons are inclusive: equality is within the limit. This status records declared comparisons and supplies no physical qualification.

Efficiency is `None` when both accounted power and electrical input power are zero; the evaluator never computes `0/0`. Zero shaft power with positive no-load losses yields zero efficiency. The ideal zero-loss case is allowed.

The power-loss efficiency formula is algebraically equivalent to `Pshaft/(V*I)` under the source equations. It uses the existing accounted power only after the normalized VI balance gate of `64*epsilon` passes, allowing the checked arithmetic roundoff between accounted power and `V*I`. This avoids efficiency greater than one from roundoff in the zero-loss case and gives exactly one without clipping. Reported electrical input power remains the actual `V*I`, and the residual remains `Pelectrical - (Pshaft + Ploss)`. This arithmetic treatment supplies no physical evidence.

Checked finite-normal arithmetic rejects overflow, underflow of nonzero results, and positive contributions rounded away during summation. The normalized balance tolerance of `64*epsilon` is an internal arithmetic gate. Passing it establishes neither physical qualification nor independent proof from the reported residual.

Execution failures are caught through a broad `Exception` boundary. Failure is atomic: partial results are discarded, diagnostics are sanitized, and an established request hash is retained.

## Applicability and future composition

Only positive rotation and nonnegative shaft torque are supported. Negative speed, negative torque, and regeneration are unsupported.

[Maxon's motor-data guidance](https://www.maxongroup.com/medias/CMS_Downloads/DIVERSES/12_137_EN.pdf) explains that no-load current varies with speed and temperature, while current, resistance, and voltage definitions depend on phase and commutation conventions. Phase, terminal, and RMS conventions are not interchangeable. Continuous-current limits also depend on thermal state and the manufacturer's operating envelope; static declared checks provide no thermal proof.

There is no automatic BLDC or ESC phase-constant conversion, battery model, commanded PWM model, or ESC loss model. Supply-bus current is not motor current, and required motor terminal voltage is not battery voltage.

Later selected-speed composition must feed actual V93 shaft torque and angular speed into the motor evaluator, avoiding caller-duplicated operating points. Thermal composition must use actual motor losses with explicit ownership and heat allocation. It must not assume that every motor loss heats an arbitrary thermal body.
