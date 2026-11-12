# Experimental prescribed section loads (V133)

`physimesh.drone.section_load.evaluate_section_load` is a standalone local Python
entry point. Its exact root is `evaluation`, `polar`, `section`, with evaluation
`section_load_experimental` and response schema `section_load_v1`.
`section_load_catalog()` returns fresh metadata without evaluating a model.

The polar is exactly the accepted V132 `section_polar` input, with all source,
classification, uncertainty and declared Mach applicability claims **UNVERIFIED**.
There is no external dataset, source fetching, API, UI, induction, nonlinear rotor
solver, motor, mission integration or publication.

The exact section fields are `axial_velocity_m_s`, `tangential_velocity_m_s`,
`chord_m`, `radius_m`, `density_kg_m3`, `dynamic_viscosity_pa_s`,
`speed_of_sound_m_s`, `pitch_rad`, and `blade_count`. Numeric fields accept exact
builtin int/float only: axial velocity is nonnegative normal or zero; tangential
velocity, chord, radius, density, viscosity and sound speed are positive normal;
pitch is normal or zero in [0, pi/2]. Blade count is an exact builtin int in 1..64.
Booleans and subclasses are rejected as numeric inputs. Bounds establish no
physical applicability.

The entire request must pass an exact builtin JSON walk before copying or hashing:
32768 nodes including keys, depth 10 with root at 1, 256 items per container,
2000 characters per string, UTF8 encoding, 1023 integer bits, finite floats.
All polar tables and section fields are preflighted before kinematics or lookup.
V132 `_preflight` receives a synthetic query (alpha 0, Re 1, Mach 0); coverage is
not a preflight requirement, so empty/malformed tables are safely rejected.
The original native request snapshot is hashed without numeric normalization.

Kinematics use prescribed total blade-relative components Wa and Wt directly:

```
phi = atan2(Wa, Wt)       alpha = pitch - phi
W = hypot(Wa, Wt)        Re = rho*W*c/mu       Mach = W/a
q = 0.5*rho*W^2          L' = B*q*c*Cl        D' = B*q*c*Cd
T' = L'*(Wt/W) - D'*(Wa/W)
Q' = r*(L'*(Wa/W) + D'*(Wt/W))
```

Loads include all B blades at one radius, per unit radial length: L', D', T'
in N/m and Q' in N*m/m; q is Pa. Positive T' is axial thrust; positive Q' is
resisting shaft torque. Signed T'/Q' are accepted without a windmill, reverse-flow
or feasibility claim. No velocity is inferred from RPM or induction. Direct
projection permits Cl=0 and avoids division by Cl. The convention follows
[Drela's QPROP formulation, equations 48–53](https://web.mit.edu/drela/Public/web/qprop/qprop_theory.pdf);
only the local force projection is used, with no QPROP solver or closure.

Derived queries are checked binary64. Every product, quotient and sum must be
normal or zero; nonzero underflow is refused and exact cancellation is allowed.
The fixed evaluation order can refuse extremes even when a rearrangement might
succeed. Finite arithmetic establishes no numerical or physical qualification.

After static validation and checked kinematics, the actual V132 evaluator is
called exactly once. Its complete return is bounded and deep-copied immediately.
A pure full boundary guard compares fresh catalog metadata against an import-time
frozen accepted V132 catalog, including status matrix, units, limits, source URLs
and limitations. It reconstructs the full expected computed/OOD response using
independent bracket, log1p/fallback weight, corner and coefficient arithmetic;
it never reruns an evaluator or calls V132 `_lookup`, `_response` or `_seal`.
Exact native types, signed zeros, source rows, indices, positive corner weights,
query, hashes and all root fields must agree. Hashes alone cannot admit a child.
Freezing metadata duplicates no evaluator; changes to the accepted V132 contract
require an explicit review of this adapter.

| Root status | Result |
| --- | --- |
| `MODEL_INAPPLICABLE` | Invalid bounded input/static schema; zero children, null hashes. |
| `SOLVER_UNSUPPORTED` | Exact bounded root with another evaluation string; zero children, null hashes. |
| `COMPUTED_EXPERIMENTAL` | One fully guarded child, retained in full. |
| `EXECUTION_FAILED` | Sanitized failure; no partial loads or retained child payload. |

A guarded OOD child remains fully retained under root `COMPUTED_EXPERIMENTAL`,
with `load_state=NOT_RUN_OUT_OF_POLAR_DOMAIN`, `loads=null` and accepted count 1.
It establishes no infeasibility. A computed child produces `load_state=COMPUTED`.
Unexpected child execution/model failure after preflight is narrowly treated as
`LOOKUP_BOUNDARY_FAILED`; this deliberately does not trust child failure causes.
Guard failure has count 0. A subsequent load/export failure preserves count 1 but
clears all outputs/units. Counts mean accepted guarded results, not attempted calls
or execution attestation. Ordinary Exception is sanitized; BaseException propagates.

Parent outputs allow 32768 nodes and depth 16 to retain the complete child;
all other JSON limits are unchanged. The child additionally obeys its own 8192-node,
depth-12 output limit. SHA256 binds sorted compact UTF8 JSON with `ensure_ascii=False`
and `allow_nan=False`; the response hash excludes only `evaluation_sha256`.
Persistent hashing/export failure drops both hashes. Hashes confer no authenticity,
scientific accuracy, runtime identity, physical/numerical qualification or feasibility.

Tests use invented synthetic polars, independent Decimal95 load arithmetic and
adversarial child modifications. They establish local contract/arithmetic behavior.

Native exact-knot coefficients and source rows retain V132 builtin types and
signed zeros, including integer coefficients such as `2**53+1`. The load stage
explicitly converts retained coefficients to binary64; it does not claim exact
integer load arithmetic. The boundary comparator distinguishes `0.0` from `-0.0`,
including in a rehashed child payload.

A zero sum is accepted only when its two already-rounded contributions are exact
opposites. This permits exact cancellation in the chosen binary64 arithmetic;
it does not establish cancellation of the unrounded real-valued expression.
The tests cover signed-zero/native-knot admission, zero Cl, signed T'/Q', bounded
walks before copy hooks, catalog tampering, hash faults and BaseException propagation.

Arithmetic failures before the child (for example an overflowing Reynolds
numerator) have accepted count 0. Checked load underflow/overflow after a guarded
child has accepted count 1 and still returns no partial loads or child payload.
The tests exercise both boundaries, persistent parent response hashing failure,
ordinary child exceptions, full units/types, detached result ownership, and the
maximum 8-table/256-row synthetic polar. Catalog and result freshness do not
provide protection against arbitrary changes to the Python runtime itself.
