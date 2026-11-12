# Polar rotor HTTP adapter (V137)

`GET /api/drone/polar-rotor/catalog` returns a fresh, unchanged V136
`polar_rotor_catalog()` under `catalog`, with separate HTTP `transport` metadata.
Catalog access runs no evaluator or child model.

`POST /api/drone/polar-rotor/evaluate` accepts the native V136 request described
in [polar-rotor.md](polar-rotor.md). It calls the actual
`evaluate_polar_rotor` exactly once in the threadpool. The full structured result
is returned unchanged with HTTP 200, including refusals, OOD, nonconvergence,
counts, units, hashes and nested traces. HTTP 200 does not establish convergence,
physical validation, numerical qualification, runtime identity or feasibility.
Native integers are retained without a JSON roundtrip or float conversion.

Admission requires one complete strict UTF-8 JSON object. Duplicate keys at any
depth, BOM, nonfinite numbers, malformed JSON and violations of the actual V136
`_walk` input bounds receive generic HTTP 422. These bounds include 262,144 nodes
including keys, depth 16 (root 1), 256 items per container, 2,000 characters per
string and 1,023 integer bits. Semantic decisions belong to V136.

Independently, ingress permits at most 1,048,576 actual request bytes, including
UTF-8 bytes and whitespace. Content-Length can reject early but cannot bypass
receive counting. Oversize requests receive 413; malformed length receives 400.
This is not a response cap: actual V136 responses may exceed 1 MiB. Semantic
model maxima do not promise every combination fits the HTTP request budget.
As in V130, body JSON is parsed without requiring a JSON media-type header.

The existing application authentication runs before length checks, body reads,
parsing or evaluation. Local bearer/browser and hosted individual-session rules
are inherited. Hosted authorization adds only the two exact canonical paths;
encoded aliases of those paths receive 403, as do hosted trailing-slash and
neighbor paths. Local namespace authentication retains its existing behavior.
The byte limiter also recognizes trailing slashes before the existing redirect.

No defaults, saved studies, datasets, UI, model mathematics, deployment or
publication behavior are added. V136 source assertions and limitations remain
unchanged, including historical metadata describing the standalone V136 module.

Test source covers invented polar data evaluated by actual V136, full HTTP/direct
result equality, threadpool dispatch, catalog freshness, strict JSON admission,
request-byte boundaries, authentication ordering and hosted canonical paths.
The eight-annulus case retains 128 actual residual/load/lookup results and checks
that a response larger than 1 MiB is returned in full. These are coverage
assertions in test source, not a claim that the test suite has passed.
