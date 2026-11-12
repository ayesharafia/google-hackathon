# Experimental graph mission API

Authenticated local and hosted clients use these exact paths:

- `GET /api/drone/graph-mission/catalog`
- `POST /api/drone/graph-mission/evaluate`

Hosted paths require no suffix or trailing slash. Use the accepted `constant_condition_graph_mission_experimental` payload described in `graph-mission.md`; schemas are not automatically interpreted.

Caller-declared usable energy is in joules **before** reserve, which is held once. Wing eta combines propulsive/electrical efficiency; hover eta converts shaft power to electrical demand.

Declared and streamed bodies have a 128 KiB byte cap; excess returns 413. Invalid UTF-8, duplicate keys, nonfinite values, nonobject JSON, or exceeded JSON budgets return 422 with generic `Invalid graph mission request.`.

Semantic errors return 200 with `GRAPH_INVALID` and no admitted hash. Runtime failure returns 200 with `EXECUTION_FAILED`, empty final outputs, and prior segments marked incomplete.

Request/input SHA hashes cover the admitted payload. Evaluation SHA hashes the response before its own field is added.

Local cookie POSTs require same-origin requests; bearer-origin behavior is preserved.

This local-only experimental route provides no capacity or flight-feasibility verdict, mass/thermal/dynamics closure, deployments, or arbitrary model calls. It is not full M3 or aircraft qualification.

## Electrothermal selection

Explicitly select `constant_condition_electrothermal_mission_experimental` through `evaluation` on the existing POST route. The catalog’s `evaluations` provides required fields, schema version, and JSON values for each ID. Unknown IDs are refused without fallback. No arbitrary dispatch or new path is introduced.

The legacy default and 32,768-value top-level JSON budget remain unchanged. Selected electrothermal requests have a 49,152-value JSON budget; the shared 128 KiB body cap and depth-10 limit apply. Authentication and CSRF protections are inherited.

See [electrothermal-mission.md](electrothermal-mission.md) for the payload. Callers supply `heat_fraction_of_electrical_input`; losses are not inferred. Accepted constant-condition segments carry thermal state forward.

This is local-only experimental functionality without physical qualification. Feasibility remains `None`; results establish no aircraft thermal safety. No deployment is included.
