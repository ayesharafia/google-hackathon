# Polar rotor workbench (V138)

The initially closed advanced panel in `web/workbench.html` accepts standalone
V136 native caller JSON for the accepted V137 endpoints:
`GET /api/drone/polar-rotor/catalog` and
`POST /api/drone/polar-rotor/evaluate`. Its identity is
`polar_rotor_experimental`, schema `polar_rotor_v1`, matching the Python model
constants. See [the model contract](polar-rotor.md) and
[the HTTP contract](polar-rotor-api.md) for the complete requirements.

This is an experimental isolated axial rotor calculation over prescribed finite
annuli. The textarea starts blank. The caller supplies the complete request,
including polars, geometry, source assertions, fluid properties and solve
settings. There are no invented defaults, templates, automatic model selection,
automatic requests or automatic runs. The panel is not a configuration wizard
or a saved project study. It does not save or modify private project inputs.
The prescribed electrothermal, solved electrothermal and cantilever panels
remain separate.

Explicitly refresh the catalog, review its full raw limitations, then enter and
run a request. Running requires a successful current catalog with the expected
evaluation, schema, limitations array and numeric transport byte limit. These
are shallow recognition checks, not independent verification of the catalog or
its scientific claims. A failed, malformed or mismatched refresh leaves running
disabled. Opening the panel and reconnecting do not fetch a catalog.

Requests go through the existing `request()` transport as the exact textarea
value, with `Content-Type: application/json`. The input is never parsed and
reserialized. Whitespace, `9007199254740993`, `-0.0`, Unicode such as `µ`, duplicate
keys and nonfinite tokens such as `NaN` remain unchanged in the submitted text.
This preserves native numeric tokens; it does not make invalid JSON admissible.
Strict duplicate/nonfinite rejection, native numeric types, JSON bounds, schema
and scientific admission belong to the server. Invalid JSON is forwarded for
server refusal. Admission and transport failures, including HTTP 422, produce
generic text and clear prior results and capture eligibility; server exception
details are not inserted into the page.

Before dispatch, the browser blocks blank text, actual unpaired Unicode
surrogates and requests exceeding **1,048,576 actual UTF-8 bytes**, including
whitespace. Exactly that byte count is allowed by the browser gate, subject to
server admission. A literal JSON escape such as `\ud800` remains server-owned
input; an actual unpaired UTF-16 code unit is blocked because UTF-8 encoding
would replace it. The 1 MiB request limit is not a response cap. The model has
its own output bounds, and a response may exceed 1 MiB. Scrollable raw blocks
bound the visible area without truncating the stored response text.

The full successful HTTP response is displayed verbatim from `response.text()`
using `textContent`, including unrecognized identities or malformed response
JSON. Catalog text and string-state labels also use text sinks. Supplied HTML
is displayed as text, never interpreted as markup. Parsed response data is
used only for shallow evaluation/schema/status recognition and string-state
display. Recognized workflow statuses are `COMPUTED_EXPERIMENTAL`,
`MODEL_INAPPLICABLE`, `SOLVER_UNSUPPORTED` and `EXECUTION_FAILED`.
HTTP 200 does not mean convergence or establish computational or physical
success.

For a recognized identity, the panel can show producer-reported `rotor_state`
and the ordered per-annulus `solve_state` roster. Non-string states are labeled
unavailable. These labels do not constitute a nested result guard. Numeric
physical fields are not used for a totals summary, formatting, exact-value
claims or capture reconstruction. T/Q/P values and producer-reported counts
remain in the full raw result. Parsing metadata never replaces the retained raw
strings with JavaScript numbers or a reconstructed JSON object.

The visible totals rule is: **Only all-converged supplies integrated T/Q/P in
full raw result**. Under the model contract, a nonconverged or out-of-polar-domain
section retains all annuli and their traces, reports
`NOT_RUN_SECTION_NOT_CONVERGED`, and returns `integrated: null` with no partial
totals. This covers out-of-domain, not-bracketed and evaluation-budget exits.
That is a description of the model contract; the browser does not independently
check convergence, trace completeness, null totals or integration arithmetic.
Execution and admission failures have their separate model/API semantics.

The panel exposes the strict interior F refusal: require
`0 < exp(-f) < 1` and `0 < F < 1`. Rounded endpoints are refused without clamping,
asymptotes or a hidden limit policy. Caller polar and geometry assertions remain
unverified. The isolated calculation establishes no installed-aircraft behavior,
CFD agreement, motor/DC feasibility, physical validation, numerical qualification,
flight or safety qualification. The browser makes no independent physical or
computational verification claim.

A fresh response with recognized evaluation/schema/status enables an explicit
download named `polar-rotor-browser-capture.json`. The `browser_capture_v1`
envelope contains `raw_request_json`, `raw_response_json` and `raw_catalog_json`
as strings only, preserving their complete captured text, including whitespace
and native numeric tokens. Only the outer envelope is serialized. Its other
fields describe the evaluation/schema, reported status, HTTP status and capture
limitations. It does not include workspace credentials or context identifiers.

This is an **unverified local browser capture**, not a retained project study or
server-attested execution record. Embedded hashes are unverified producer data;
the browser neither recomputes nor verifies them. Shallow identity recognition
does not authenticate a producer or establish that nested results are valid.
Download uses a local JSON Blob and temporary anchor, with object URL cleanup
in `finally`, including anchor failures. Download errors produce generic text.
No upload, extra HTTP request, model call, publication or deployment occurs.

Starting another run, editing the textarea, clearing it or refreshing the
catalog invalidates prior results, string states and capture eligibility.
Clear removes the input and results; explicit refresh also invalidates the old
catalog gate while preserving the input. Edits and clear invalidate pending
work. Context generation, session/token, organization, project or connection
changes clear the input, catalog, results and capture. Reconnection requires a
new explicit catalog refresh. Context and operation serial checks surround both
the request and `response.text()` awaits, preventing delayed results from
restoring stale state. Download rechecks context and the exact current input.

The panel uses the existing shared transport and context hooks. Existing
`public_access`, local browser access and hosted authentication/authorization
policies remain unchanged. No API, model or study code is modified. CSS is
scoped to the new panel, wraps controls and long text, restricts textarea
resizing to the vertical direction and bounds raw blocks for desktop and mobile
review.

`tests/web/test_polar_rotor.mjs` supplies unit DOM test source adapted from the
solved electrothermal precedent. Its DOM double includes `replaceChildren`;
catalog identity comes from the actual unchanged Python API catalog. Response
fixtures are explicitly synthetic UI data. DOM fixtures do not establish
browser behavior, API correctness or scientific qualification. Actual browser
and API checks should verify full HTTP/direct-result equality, unchanged raw
requests, exact raw response and capture strings, native numeric precision,
nonconvergence and large-response handling, stale-context invalidation, safe
text rendering, and readable desktop/mobile layouts without page overflow.
