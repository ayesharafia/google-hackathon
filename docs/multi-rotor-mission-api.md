# Multi-rotor mission API

The existing authenticated endpoints are:
- `GET /api/drone/graph-mission/catalog`
- `POST /api/drone/graph-mission/evaluate`

Authentication, CSRF protection, the 128 KiB body limit, and maximum JSON depth of 10 remain unchanged.

The catalog entry declares:
- `evaluation`: `constant_condition_multi_rotor_mission_experimental`
- `required_fields`: `evaluation`, `usable_energy_j`, `reserve_fraction`, `segments`
- `json_values`: `32768`
- `schema_version`: `constant_condition_multi_rotor_mission_v1`

Requests follow [multi-rotor-mission.md](multi-rotor-mission.md) and explicitly select `constant_condition_multi_rotor_mission_experimental`. Existing single-power and electrothermal evaluations remain unchanged; no automatic translation occurs.

Segments are evaluated chronologically. Each rotor’s actual shaft power is divided by its efficiency; these electrical powers are summed, with auxiliary power added once. Energy is integrated over segment duration in joules and converted using `Wh = J / 3600`. The reserve fraction is applied once to usable energy, without reapplication per rotor or segment.

Malformed JSON returns HTTP `422`. Semantic rejection returns HTTP `200` with `GRAPH_INVALID` and no admitted-input hash. Execution failure returns HTTP `200` with `EXECUTION_FAILED`, preserves `request_sha256`, `input_sha256`, and `evaluation_sha256`, and returns no segments, outputs, units, or partial results.

Existing admitted-input canonicalization is preserved: `input_sha256` equals `request_sha256`, the SHA-256 hash of the canonical request. `evaluation_sha256` hashes the response before its own field is added. An admitted-input hash identifies admitted input; it does not establish execution success, aircraft acceptance, or API qualification. This documents existing routes only and introduces no remote execution, deployment, new validation, aircraft-pass determination, or API qualification.
