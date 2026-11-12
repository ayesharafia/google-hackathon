# Advanced tabulated electrothermal workbench (V125)

The collapsed **Advanced: tabulated electrothermal request JSON** panel consumes
accepted V123/V122 HTTP transport without changing the V121 workflow or Python.
It is standalone and independent of saved project inputs. It supplies no seed,
synthetic defaults, templates, model selection, autosave or persistence.

Connect the workspace, explicitly refresh the catalog, inspect its full raw
metadata and limitations, then enter a complete caller-owned V121 request and
choose **Run supplied request**. **Clear JSON and results** removes the request
and result from this panel. No network requests occur automatically.

V125 adds **Download current raw evidence** inside the same collapsed panel.
Only an explicit click saves a local file; there is no automatic export,
upload, sharing, persistence, new endpoint or retained-study integration.
The label is: “Unverified local browser capture. Not a retained project study
or server-attested execution record; embedded hashes are unverified producer
data. Not physical validation.”

Download is disabled until a fresh current run has successful HTTP transport,
an object root with the actual evaluation and schema identity below, and one
of the four recognized root statuses. This includes recognized noncomputed
workflow outcomes; recognition does not establish computational success.
Unknown, malformed or mismatched successful-HTTP responses remain visible as
raw text, with **Capture unavailable** and download disabled. Non-successful
HTTP, network and text-read failures retain the existing generic error path.

The fixed filename is `tabulated-electrothermal-browser-capture.json` and the
Blob MIME type is `application/json;charset=utf-8`. The outer JSON envelope has
`schema_version: "browser_capture_v1"`, a fixed descriptive disclaimer,
`evaluation`, `response_schema_version`, recognized `status`, actual
`http_status`, and three **string** fields: `raw_catalog_json`,
`raw_request_json`, `raw_response_json`. These preserve the exact catalog that
gated this run, textarea POST body and `Response.text()` respectively, including
whitespace, duplicate keys and integers larger than 2**53. `JSON.stringify`
serializes only the outer envelope; parsed scientific data is never reserialized.
There is no added timestamp, identity, context, credential or execution/hash
verification metadata. Caller-supplied raw JSON is included verbatim.

Capture and result clear together on input edits, clear, catalog refresh,
new run, failed run, context changes or disconnect. Pending and stale runs
cannot enable download. The click handler synchronously rechecks context,
connection, pending state, run serial and exact current textarea value,
including programmatic changes without an input event. It never substitutes
edited inputs into an older capture. Saving uses a temporary local object URL
and anchor; the anchor is removed and URL revoked in `finally`, including error
paths. Failures show generic text without exception contents.

The mount receives `{request, readContext, isContext, isConnected, saveCapture?}`.
Tests can inject `saveCapture(blob, filename)`; the default uses the browser
Blob/object-URL/anchor path. Workbench
passes the existing Response-returning `request` helper, preserving its cookie,
authorization, context, no-store and 60-second timeout behavior. Catalog readiness
checks the actual `catalog.evaluation` value
`prescribed_tabulated_dc_electrothermal_experimental`, `catalog.schema_version`
`tabulated_electrothermal_v1`, limitations array and numeric transport request
limit of 1,048,576 bytes. Every refresh invalidates the prior catalog and result.

The textarea value is the exact POST body with `Content-Type: application/json`.
It is never parsed and serialized again. Duplicate keys, native integers larger
than 2**53 and whitespace reach server admission unchanged. Client checks only
nonblank input, valid paired Unicode surrogates and at most 1,048,576 UTF-8 bytes,
including whitespace. Surrogates are checked before TextEncoder can replace
unpaired code units. Strict JSON, schema, bounds and scientific checks remain
server-owned; malformed nonblank text can be submitted for server rejection.

Catalog and full result use `response.text()` and `textContent` verbatim, without
pretty-printing, truncation, response byte caps or HTML interpolation. Parsing
catalog metadata and the result's top-level status never supplies displayed raw
JSON. This avoids JavaScript Number rounding in the disclosed native integers.
The actual root result vocabulary is `COMPUTED_EXPERIMENTAL`,
`MODEL_INAPPLICABLE`, `SOLVER_UNSUPPORTED`, `EXECUTION_FAILED`; it has no
`INPUT_INVALID` alias. Unknown or missing status is labeled unavailable, with
the full successful-HTTP response still disclosed. HTTP 200 alone establishes
neither computational nor physical success. Errors use generic text and do not
echo exception or rejected server bodies.

Generation, token, organization, project and connection changes clear catalog,
request and result. Context checks occur after both request and text awaits.
Input edits, clearing and refresh invalidate pending serials; busy guards block
concurrent duplicate actions. Late results cannot repopulate cleared evidence.

This remains one-way allocated-heat screening with synthetic or unverified
declared properties. It establishes no thermal feedback, battery model, measured
temperature/hotspot/Biot validation, aircraft feasibility, flight qualification,
scientific approval or deployed availability. Full child limitations apply.
Hashes and scientific values are displayed without client recomputation.

## Verification boundaries

`tests/web/test_tabulated_electrothermal.mjs` uses the existing native Node test
route and a minimal DOM double. Its real catalog fixture is extracted by calling
the unchanged Python catalog through a bounded subprocess (set `PYTHON` if needed).
Run in this workspace with
`PYTHON=/downloads/physimesh-continuation-venv/bin/python node --test tests/web/test_tabulated_electrothermal.mjs`.
Elsewhere, set `PYTHON` to a Python environment containing the project dependencies.
These are code unit tests, not actual browser, HTTP, authentication, API equality
or visual evidence. They exercise exact raw bodies/results, Unicode byte limits,
identity gates, status disclosure, generic failures and asynchronous invalidation.
V125 adds capture callback and DOM-double URL lifecycle checks, exact raw-string
round trips, four-status identity gates, no added sensitive metadata, click-time
invalidation and generic save failures. These checks are explicitly nonbrowser.
Actual HTTP Playwright and pixel review are separate checks; this document does
not claim they have passed or that the product is ready.

The independent runner must exercise the default Blob download path in actual
Playwright. No author claim of independent browser or pixel verification is made.
The inherited V124 atmosphere suite has 31 failures associated with its missing
fixture; V125 does not repair or claim to resolve that gap.

Run the complete native web test route with
`PYTHON=/downloads/physimesh-continuation-venv/bin/python node --test tests/web/*.mjs`.
The catalog subprocess may be denied with EPERM in the author environment;
that is not a reason to replace the real fixture or change product behavior.
The eight V125 capture tests supplement the preserved 47 panel tests. Their
response envelopes and URL/anchor operations are unit doubles, not execution
attestation or actual browser download evidence.
## Retained web baseline provenance

The integration baseline is the parent reviewer's 43 retained web files at
`/downloads/v123-reviewer-web/web`, reported with verified SHA-256
`5504fb94477133e954f942970e9b75725d7fae15e10ffe3cecb4ef07dea58ddd`.
This provenance covers the retained web files, not the whole owner repository.
V124 adds two lines to `workbench.html` and three to `web/js/workbench.js`;
all accepted cantilever imports, mount, synchronization, stylesheet, section
and module bytes are preserved. The old incomplete V124 candidate is superseded;
its historical review hash is not redefined or mutated by this repair.
The repaired candidate still requires the parent reviewer's integration and
actual Chromium checks; this note grants no reviewer acceptance.
