"""Pure, success-only admission of full actual V118 chronological energy results."""

from . import tabulated_target_dc_energy as _energy
from .provenance import sha256_record
from .reference_air_tabulated_hover import _exact
from .tabulated_hover_bemt_request import _json_walk, _require
from .tabulated_target_dc_power_validation import validate_tabulated_target_dc_power_result

# Private code-owned snapshots: no runtime catalogs or caller copying hooks.
_CATALOG = _energy.tabulated_target_dc_energy_catalog()
_POWER_FIELDS = dict(_energy._POWER_FIELDS)
_COUNTS = dict(_energy._COUNTS)
_STATIC = frozenset((
    "evaluation", "schema_version", "evidence_level", "physical_validation",
    "numerical_qualification", "runtime_identity", "aircraft_status", "feasibility",
    "limitations", "limits",
))
_DYNAMIC = frozenset((
    "status", "diagnostics_complete", "request_sha256", "evaluation_sha256", "reasons",
    "outputs", "output_units", "stages", "transfers",
)) | _COUNTS.keys()
_OUTPUTS = frozenset((
    "segments", "elapsed_s", "totals_j", "totals_wh", "all_motors_within_declared_limits",
))
_ROW = frozenset((
    "segment_id", "duration_s", "start_time_s", "end_time_s", "actual_power_result",
    "energy_j", "cumulative_energy_j",
))


def _success(actual, request):
    outputs = actual["outputs"]
    _require(type(outputs) is dict and outputs.keys() == _OUTPUTS)
    rows, segments = outputs["segments"], request["segments"]
    _require(type(rows) is list and len(rows) == len(segments))
    stages, transfers = actual["stages"], actual["transfers"]
    _require(type(stages) is list and len(stages) == len(segments))
    _require(type(transfers) is list and len(transfers) == 9 * len(segments))
    counts = dict.fromkeys(_COUNTS, 0)
    energies = {key: [] for key in _POWER_FIELDS}
    durations, elapsed, all_within = [], 0.0, True
    for index, (row, segment) in enumerate(zip(rows, segments, strict=True)):
        _require(type(row) is dict and row.keys() == _ROW)
        _exact(row["segment_id"], segment["id"])
        _exact(row["duration_s"], segment["duration_s"])
        retained, supplied = row["actual_power_result"], segment["power_request"]
        _json_walk(supplied, _CATALOG["limits"]["point_input_json"])
        _json_walk(retained, _CATALOG["limits"]["point_output_json"])
        _require(validate_tabulated_target_dc_power_result(retained, supplied) is None)
        _exact(retained["status"], "COMPUTED_EXPERIMENTAL")
        counts["point_result_count"] += 1
        for key in _COUNTS:
            if key != "point_result_count":
                counts[key] += retained[key]
        _exact(row["start_time_s"], elapsed)
        durations.append(segment["duration_s"])
        start, elapsed = elapsed, _energy.dc._power_sum(durations)
        _require(elapsed > start)
        _exact(row["end_time_s"], elapsed)
        power = retained["outputs"]["power"]
        energy = {key: _energy.th.checked_product(power[field], segment["duration_s"])
                  for key, field in _POWER_FIELDS.items()}
        _exact(row["energy_j"], energy)
        for key in _POWER_FIELDS:
            energies[key].append(energy[key])
        _exact(row["cumulative_energy_j"], {
            key: _energy.dc._power_sum(values) for key, values in energies.items()})
        all_within = all_within and power["all_motors_within_declared_limits"]
        stage, digest = "segment:" + segment["id"], sha256_record(retained)
        _exact(stages[index], {
            "stage": stage, "inputs": supplied, "inputs_sha256": sha256_record(supplied),
            "result_sha256": digest,
        })
        for offset, (key, field) in enumerate(_POWER_FIELDS.items()):
            _exact(transfers[9 * index + offset], {
                "from_stage": stage, "from_field": "outputs.power." + field,
                "to_stage": "energy", "to_field": f"outputs.segments[{index}].energy_j.{key}",
                "value": power[field], "unit": "W", "producer_result_sha256": digest,
                "consumer_request_sha256": actual["request_sha256"],
            })
    for key in _COUNTS:
        _exact(actual[key], counts[key])
    totals = {key: _energy.dc._power_sum(values) for key, values in energies.items()}
    _exact(outputs["elapsed_s"], elapsed)
    _exact(outputs["totals_j"], totals)
    _exact(outputs["totals_wh"], {
        key: _energy.th.checked_quotient(value, 3600) for key, value in totals.items()})
    _exact(outputs["all_motors_within_declared_limits"], all_within)


def validate_tabulated_target_dc_energy_result(actual, request):
    """Return None for a computed actual V118 contract; otherwise raise ValueError.

    This narrow prerequisite deliberately rejects every noncomputed status,
    including legitimate V118 failures. No model, copying or mutation occurs.
    Unexpected pure dependency exceptions (including BaseException) propagate;
    arithmetic OverflowError and ZeroDivisionError are normalized to ValueError.
    """
    try:
        # Both full walks precede hashes, equality and actual V118 preflight.
        _json_walk(actual, _CATALOG["limits"]["output_json"])
        _json_walk(request, _CATALOG["limits"]["input_json"])
        _require(type(request) is dict and request.keys() == set(_CATALOG["required_fields"]))
        _exact(request["evaluation"], _CATALOG["evaluation"])
        _energy._preflight(request)
        _require(type(actual) is dict and actual.keys() == _STATIC | _DYNAMIC)
        for name in _STATIC:
            _exact(actual[name], _CATALOG[name])
        _exact(actual["status"], "COMPUTED_EXPERIMENTAL")
        _exact(actual["diagnostics_complete"], True)
        _exact(actual["reasons"], [])
        _exact(actual["output_units"], _CATALOG["output_field_units"])
        for name, maximum in _COUNTS.items():
            _require(type(actual[name]) is int and 0 <= actual[name] <= maximum)
        _exact(actual["request_sha256"], sha256_record(request))
        _exact(actual["evaluation_sha256"], sha256_record({
            key: value for key, value in actual.items() if key != "evaluation_sha256"}))
        _success(actual, request)
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Invalid bounded target DC energy arithmetic.") from error
