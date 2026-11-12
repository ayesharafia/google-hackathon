# Rotor results presentation candidate (V139)

This increment adds a read-only approximate view of the existing
`polar_rotor_experimental` / `polar_rotor_v1` producer output. It supersedes
only the V138 workbench document's description that numeric values remain
exclusively in raw text. Scientific models, API, requests, studies and the older
plotting/CFD subsystem remain unchanged. The deferred V139 numerical refinement
wrapper is not implemented. This is post-processing, not benchmark validation.

The view reads `outputs.annuli` and each `solve_result.outputs.solution` for
selected evaluation index, `psi_rad` and `residual_m2_s`. Only a producer
`COMPUTED_EXPERIMENTAL` result with rotor state `COMPUTED`, every section
`CONVERGED`, and correctly shaped non-null `outputs.integrated` supplies totals
and charts. Totals come directly from `integrated.totals`: thrust N, torque N*m,
shaft power W. Densities come directly from `integrated.contributions`:
`thrust_density_n_m` in N/m and `torque_density_nm_m` in N*m/m, plotted at
`annuli[].midpoint_radius_m` in m. Producer contribution thrust/torque and widths
are also tabulated. Unit strings consumed from `output_units` must match these
native units. No browser quadrature, partial integration or scientific equation
is added. Signed and zero loads retain their sign/value in the approximate view.

Nonconverged/out-of-domain sections keep their producer solve-state table but
have no integrated totals or load charts. An absent selected residual is labeled
unavailable, never zero. Failure statuses, empty output and malformed presentation
fields show projection unavailable while retaining the full HTTP response.
Shallow V138 identity recognition still controls local capture eligibility,
independently of whether this projection is available.

Projection budgets follow the current producer's 8 annuli and 16 retained section
evaluations per annulus, at most 128 evaluations. Only a fixed set of geometry,
solution, contribution, total, state, count and unit fields is read. Large nested
polar tables and unused metadata/source strings are not traversed or displayed
by the projection. Counts and indices must be numbers matching their bounded
arrays; projected state labels come from a fixed allowlist. The legacy raw-state
roster is now capped at 8 entries and 2,000 characters per label.

The **arbitrary presentation range** for every consumed physical scalar is zero
or absolute magnitude in [1e-12, 1e12]; values must be finite JavaScript numbers
and integers must be safe integers. These are display restrictions, not solver
limits or scientific admission criteria. No clamping, overflow substitution,
normalization or missing-value zero fill occurs. The approximate view formats
five significant digits; raw strings keep their original precision and spelling.
Native JSON integer/float type distinctions are not recoverable from parsed
JavaScript numbers. No exact numeric preservation is claimed for the visual view.

Native SVG charts contain discrete points with no connecting interpolation,
smoothing or filled area. Axes use the sample extent plus 10% padding; a constant
nonzero value gets 10% relative padding, and constant zero gets [-1, 1] in its
axis units. Empty data produces no chart. Units, bounded scientific tick text,
SVG title/description and HTML table fallbacks accompany the plots. Charts and
tables scroll in focusable labeled regions on narrow screens. Each SVG stays
600 CSS pixels wide for its 600-unit viewBox, preserving 13px chart text; its
bounded wrapper owns horizontal scrolling. Tables retain a 52rem minimum width
with unbroken cells inside their own bounded scroll wrappers. Visible cues say
“Scroll horizontally to see full chart/table” for the corresponding region.
The projection continues to span all columns of the outer panel grid.
Desktop/mobile readability and clipping still
require independent real-browser review; DOM unit tests do not establish it.

Separate pressure-contour and flow-vector cards explain the missing matched
native rotor pressure/velocity fields and mesh. No rotor spatial field is
inferred from section loads or substituted from the stationary sphere path.
Pressure contours, flow vectors and velocity contours remain pending genuine
matched producer fields. Temperature is outside this increment's UI scope.

The UI explicitly says uncertainty not quantified, producer-reported/no
independent verification, not physical validation, and approximate IEEE754 browser
numbers. It supplies no measured comparison, error score, uncertainty bar, grid
sensitivity, blanket validation label, provenance authentication or numerical
qualification. Local checks apply only to consumed presentation fields: they are
not cryptographic, schema, whole-result, trace-replay or integration-arithmetic
verification. Embedded hashes and caller source assertions remain unverified.

Request, response and catalog text and the V138 `browser_capture_v1` envelope
semantics are unchanged: only the outer envelope is serialized. Editing, clear,
refresh, new run, context change and disconnect clear the projection with the raw
result and capture. Existing request/text-await stale-operation checks govern
projection rendering. No dependencies, fetches, deployment or git mutations.

Focused Node tests use explicitly synthetic UI fixtures based on the inspected
producer paths/units and a DOM double adapted from V138. They are not API, browser
or scientific evidence. Actual Python fixture/API auditing and independent
numerical plus desktop/mobile visual review are the owner's next acceptance
stage. This candidate has no scientific or visual acceptance claim.
