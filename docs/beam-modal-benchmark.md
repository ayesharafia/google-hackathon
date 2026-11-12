# V52 provisional uniform modal benchmark candidate

`physimesh.drone.beam_modal_benchmark.uniform_modal_refinement` is a bounded,
standalone direct helper. It adds no API route or automatic approval. All six
keyword arguments are required: `length_m`, `E_pa`, `I_m4`,
`mass_per_length_kg_m`, `element_counts`, and `modes`. Scalars follow the core's
positive finite normal binary64 policy and accept only exact builtin int/float.
Counts require an exact builtin list of 2–6 strictly increasing exact builtin
integers in 2–64; modes require an exact builtin integer in
1–min(6, twice the smallest mesh). Nonnested meshes are supported.

Each mesh calls the accepted cantilever modal solver. Any core refusal discards
all partial outputs and preserves its exact nested refusal in `core_refusal`.
Malformed data produces a closed refusal with empty outputs. An expected
Brent root convergence RuntimeError produces `REFERENCE_FAILURE` with empty
outputs, including failure after an earlier root was computed. Results contain
finite builtin JSON data. Core results are not mutated; private solver data is
not accessed. Physical frequencies are not used to infer continuum accuracy.

The dimensionless continuum frequency is beta squared, with the first six roots
of `cos(beta) + 1/cosh(beta) = 0`. Bracketed SciPy Brent solves use (1,2), (4,5),
(7,8), (10,11), (14,15), and (17,18), preserving mode assignment. Returned roots
and frequencies are finite binary approximations, not exact values or error
bounds. The actual dimensionless frequency is the square root of the core's
dimensionless eigenvalue. The signed `dimensionless_frequency_relative_error` is
`sqrt(eigenvalue_dimensionless)/beta**2 - 1`;
`absolute_dimensionless_frequency_relative_error` is its absolute value.
Orders and error-decrease flags use the absolute field. Subtraction near unity
can cancel to zero and lose relative precision; a zero is not proof of an exact
frequency. These quantities remain finite binary observations;
physical scale overflow can still cause a core refusal.

For the continuum displacement, the usual unscaled expression is
`cosh(beta*xi)-cos(beta*xi)-sigma*(sinh(beta*xi)-sin(beta*xi))`, where
`sigma=(cosh(beta)+cos(beta))/(sinh(beta)+sin(beta))`. Expanding the hyperbolics
into exponentials, multiplying numerator and denominator by `2*exp(-beta)`,
and collecting the growing and decaying coefficients gives the stable runtime
form. With `t=exp(-beta)` and `D=1-t*t+2*sin(beta)*t`, its coefficients are
`A=(-t+sin(beta)-cos(beta))/D`, `B=(1+(sin(beta)+cos(beta))*t)/D`, and
`sigma=(1+t*t+2*cos(beta)*t)/D`. The displacement is
`A*exp(beta*(xi-1))+B*exp(-beta*xi)-cos(beta*xi)+sigma*sin(beta*xi)`.
Its xi derivative multiplies beta into
`A*exp(beta*(xi-1))-B*exp(-beta*xi)+sin(beta*xi)+sigma*cos(beta*xi)`.
Both are divided by the computed tip displacement. Computed clamped-end
roundoff is retained rather than structurally overwritten.

An independent 80-decimal-digit fixture evaluates the original unscaled
hyperbolic expression and its analytic derivative using separately supplied
high precision roots. It covers all six modes at xi=0,1/32,...,1. Tests compare
both runtime quantities against that fixture with a conservative absolute
1e-11 tolerance, including slopes of magnitude about 18. This tolerance is
local verification evidence, not a universal accuracy guarantee.

Every mesh reports maximum absolute nodal displacement and xi-derivative
errors; zero crossings do not produce relative shape errors. These observations
combine continuum reference approximation, discrete approximation, and solver
roundoff; they do not isolate a certified discretization error. Adjacent
frequency orders use differences of logarithms of positive errors, divided by
logarithmic mesh ratios. Zero or nonfinite errors give null orders. Error
increase flags are observations. Different nodal sets make shape maxima
diagnostic; no shape convergence order is asserted.

The model assumes a uniform ideal undamped Euler–Bernoulli cantilever with
small linear transverse motion and ideal clamping. It excludes shear deformation,
rotary inertia, tip mass and tip rotational inertia, prestress, damping, and
aeroelastic effects. It does not establish applicability to a real structure.

Results use schema_version `uniform_modal_refinement_v1`, evidence_level, and
aircraft_status envelope keys. All results retain physical validation, numerical qualification, and mesh
accuracy as `NOT_ESTABLISHED`, evidence_level as `unverified`, and aircraft_status and
feasibility as null. There are no benchmark acceptance thresholds, accuracy
guarantees, or physical claims. This remains a provisional candidate, without
acceptance or full CI qualification.

Continuum references: [Cantilever beam natural frequencies and mode shapes](http://www.vibrationdata.com/tutorials/free_cant.pdf),
[Washington University beam vibration laboratory](https://classes.engineering.wustl.edu/mems431_lab/lab6.html),
and [Introduction to finite element methods, chapter 31](https://quickfem.com/wp-content/uploads/IFEM.Ch31.pdf).
