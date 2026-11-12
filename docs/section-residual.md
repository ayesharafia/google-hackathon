# Experimental local section residual (V134)

`physimesh.drone.section_residual.evaluate_section_residual` evaluates one caller
prescribed psi, using exactly one accepted V133 section-load evaluation at most.
The exact request root is `evaluation`, `polar`, `section`; the selector is
`section_residual_experimental` and response schema is `section_residual_v1`.
`section_residual_catalog()` returns fresh metadata without evaluating a model.
This is a local nonlinear residual, with no derivative, root solve, convergence,
rotor performance, integration, dataset, API, UI or publication claim.

The original [Drela QPROP formulation, page 5, equations 17–32](https://web.mit.edu/drela/Public/web/qprop/qprop_theory.pdf)
provides the equations. Ua and Ut are imposed velocities **excluding this rotor's
own induction**. The empirical modified Prandtl relation uses a non-contracting
helical wake with constant pitch across radii. The perpendicularity assumption
in equation 11 is strictly valid only for a lightly loaded rotor with Goldstein
circulation. These assumptions establish no CFD or physical qualification.

```
U = hypot(Ua, Ut)
Wa = 0.5*Ua + 0.5*U*sin(psi)     Wt = 0.5*Ut + 0.5*U*cos(psi)
va = Wa - Ua                     vt = Ut - Wt
lambda_w = (r/R)*(Wa/Wt)
f = (B/2)*(1-r/R)/lambda_w        F = (2/pi)*acos(exp(-f))
Gamma_induced = vt*(4*pi*r/B)*F*hypot(1, 4*lambda_w*R/(pi*B*r))
Gamma_lift = 0.5*W*c*Cl           residual = Gamma_induced - Gamma_lift
```

Circulation and residual have units m²/s. Cl=0 is allowed; there is no Cd/Cl
ratio. The full V133 loads retain drag. This adapter admits only positive
induction: Ua>=0, Ut>0, atan2(Ua,Ut)<psi<pi/2, R>r>0, with independently checked
strictly positive normal Wa, Wt, va and vt. Tip, hub, windmill and reverse-flow
branches are excluded. A valid real-valued angle inequality alone cannot prevent
rounded zero induction in binary64.

All products, quotients and sums must produce normal floats or exact zero;
nonzero contribution underflow is refused. Zero sums require the two already
rounded contributions to be exact opposites. This policy does not establish
cancellation of the unrounded real-valued expression. The plain acos(exp(-f))
branch requires 0<exp(-f)<1 and 0<F<1: rounded endpoints, underflow, and unresolved
small/large f fail closed. There is no clamp, asymptotic replacement or hidden
limit policy. The geometry factor uses hypot to avoid squaring overflow, while
other checked products can still fail; there is no full-range promise.

All polar tables and static section fields are validated before velocities or
child calls. The polar contract is exactly accepted V132. The complete V133
return is bounded and copied immediately, then guarded against its frozen
import-time catalog and a fresh catalog. The adapter reconstructs V133 query,
kinematics, loads, complete root metadata, statuses, units, counters and hashes.
It reuses the accepted pure V132 nested guard; it does not independently rebuild
that entire nested guard. It never invokes V133 numerical helpers to guard a
result and never repeats a child evaluation.

A fully guarded child gives both result counts 1, including polar domain refusal.
OOD retains the full child and derived velocities under COMPUTED_EXPERIMENTAL,
with residual_state NOT_RUN_OUT_OF_POLAR_DOMAIN and null closure/residual. It
creates no circulation values. Boundary failure gives LOAD_BOUNDARY_FAILED,
counts 0 and empty payload. Subsequent closure/export failure clears all payload
but preserves counts 1. Counts are accepted results, not attempted calls,
physical evidence or execution attestation.

All source, classification, uncertainty and Mach applicability claims remain
UNVERIFIED. Physical/numerical qualification and runtime identity are not
established; aircraft status and feasibility are null. Hashes bind full native
requests/responses, not authenticity or qualification.

The exact section fields are:

| Field | Meaning and admitted values |
| --- | --- |
| `imposed_axial_velocity_m_s` | Ua, nonnegative normal or zero, m/s |
| `imposed_tangential_velocity_m_s` | Ut, positive normal, m/s |
| `psi_rad` | Positive normal radians in the strict branch above |
| `tip_radius_m` | Positive normal R>r, m |
| `radius_m` | Positive normal r, m |
| `chord_m` | Positive normal c, m |
| `density_kg_m3` | Positive normal density, kg/m³ |
| `dynamic_viscosity_pa_s` | Positive normal viscosity, Pa·s |
| `speed_of_sound_m_s` | Positive normal sound speed, m/s |
| `pitch_rad` | Normal or zero in [0, pi/2], radians |
| `blade_count` | Exact builtin int in 1..64 |

Numeric fields admit exact builtin int/float only; bools and subclasses are
rejected. Original native values remain in the request hash. The exact V132 polar
retains its native coefficients, including exact integer knots; V133 converts
load coefficients to binary64. None of these bounds establishes applicability.
Native R>r is necessary, and the computed r/R must also be strictly below 1 with
a resolved positive gap. Converting two distinct native integers to the same
float does not authorize an unresolved tip gap.

The complete input is walked before copying, hashing or invoking child code.
Limits include dictionary keys in the node count and start root depth at 1:

| Budget | Nodes | Depth | Container items | String characters | Integer bits |
| --- | --- | --- | --- | --- | --- |
| V134 request | 32768 | 10 | 256 | 2000 | 1023 |
| V134 response | 65536 | 24 | 256 | 2000 | 1023 |
| Retained V133 response | 32768 | 16 | 256 | 2000 | 1023 |

Strings must encode as strict UTF8 and floats must be finite. Foreign objects,
subclasses, cycles, oversized containers and excessive depth are refused before
copy hooks. V133 enforces its own V132 output budget of 8192 nodes/depth 12;
the reused pure nested guard enforces it again. Full retained request polar
tables contribute to the V133 and V134 budgets; they are never truncated.

Static validation includes every row in every polar table, even if the eventual
query will be out of domain. Only after this validation is the psi sign branch
tested with atan2. Checked Wa/Wt/va/vt derivation and query arithmetic precede the
single actual V133 call. The derived V133 request uses exactly the nine accepted
section fields: derived total Wa/Wt replace imposed Ua/Ut, while geometry,
properties, pitch and blade count retain their native values. Psi and tip radius
are not silently added to the V133 contract.

The full retained child contains `actual_lookup_request` and
`actual_lookup_result`. The boundary guard checks exact native types and signed
float zeros, all nested statuses and arithmetic, original polar query data,
full units, limits, URLs, classification labels and hashes. Rehashing a forged
load or changing a nested query does not admit it. Fresh catalog equality checks
all V133 catalog fields against the frozen import-time snapshot. V133 kinematics
and loads use independent checked simple formulas in this module; the accepted
pure V132 guard is imported for nested lookup validation. Fresh catalog calls
are metadata operations, not evaluator calls. The scope is nested guard reuse,
not an independently implemented whole guard from scratch.

| Root status | Counts and retained payload |
| --- | --- |
| `RESEARCH_ONLY` | Catalog, counts 0, null hashes |
| `MODEL_INAPPLICABLE` | Invalid bounded/static request or branch; counts 0, null hashes |
| `SOLVER_UNSUPPORTED` | Exact bounded root with another evaluation string; counts 0, null hashes |
| `COMPUTED_EXPERIMENTAL` | Counts 1, full guarded V133 child and derived velocities |
| `EXECUTION_FAILED` | Empty outputs/units; counts 0 or 1 according to guarded acceptance |

Unexpected child MODEL_INAPPLICABLE, execution failure, ordinary exception or
any malformed response becomes LOAD_BOUNDARY_FAILED with counts 0. A guarded
V133 OOD is accepted with counts 1 and no fake Gamma values. A subsequent
closure or export failure also has counts 1 but clears the child and velocities
along with all other payload. Pre-child representational failure has counts 0.
Ordinary Exception is sanitized; BaseException propagates.

Outputs include Ua, Ut, U, Wa, Wt, va, vt and psi; closure includes r/R, resolved
tip gap, local wake lambda, f, exp(-f), acos angle, F, geometry argument/factor,
circulation length scale, Gamma_lift and Gamma_induced. The full V133 child
provides W, phi, alpha, Re, Mach and q/L'/D'/T'/Q'. Each field has explicit units;
all closure dimensionless factors have unit `1`. The residual is signed, while
Gamma_induced must be positive. Gamma_lift may be zero or signed according to Cl.
No residual derivative, root bracket, convergence or equilibrium is asserted.

Request SHA256 binds the entire original validated native JSON snapshot.
Evaluation SHA256 binds the complete response excluding only `evaluation_sha256`.
Both use sorted compact UTF8 JSON, `ensure_ascii=False`, `allow_nan=False`.
A persistent response hashing/export failure clears both hashes while preserving
the guarded count and exposing no partial payload. Catalogs and returned results
are fresh detached values. Hashes and freshness do not protect against arbitrary
changes to the Python runtime or provide account/model attestation.

The tests use invented synthetic polar tables, independent math reconstruction,
full child equality and adversarial tampering. They check local arithmetic and
contract behavior only.
