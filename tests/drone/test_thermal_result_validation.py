"""Capture real thermal results before blocking the model and integrator."""

import math
import sys
from copy import deepcopy
from unittest.mock import Mock

import pytest

from physimesh.drone import thermal
from physimesh.drone import thermal_result_validation as guard
from physimesh.drone.thermal_result_validation import validate_thermal_result


def _request(segments=None):
    return {
        "evaluation": "lumped_thermal_screening", "mass_kg": 1,
        "specific_heat_j_kg_k": 500, "initial_temperature_k": 300,
        "lumped_biot_number": 0.05, "property_source": "Declared test properties",
        "segments": segments if segments is not None else [
            {"duration_s": 25, "ambient_temperature_k": 290,
             "heat_input_w": 20, "conductance_w_k": 2},
        ],
    }


def _block_models(monkeypatch):
    calls = []
    for name, module in tuple(sys.modules.items()):
        if not name.startswith("physimesh.drone.") or module is None:
            continue
        for field in tuple(vars(module)):
            if (field.startswith(("evaluate_", "screen_", "solve_")) or field.endswith("_catalog") or
                    field in ("integrate_segment", "_compute", "deepcopy", "sha256_record")):
                call = Mock(side_effect=AssertionError("forbidden guard call: " + name + "." + field))
                monkeypatch.setattr(module, field, call)
                calls.append(call)
    return calls


def _checked(monkeypatch, actual, request, *, rejects=False, expected_error=ValueError):
    before = deepcopy((actual, request))
    calls = _block_models(monkeypatch)
    error = None
    if rejects:
        with pytest.raises(expected_error) as caught:
            validate_thermal_result(actual, request)
        error = caught.value
    else:
        assert validate_thermal_result(actual, request) is None
    assert (actual, request) == before
    for call in calls:
        call.assert_not_called()
    return error


@pytest.mark.parametrize("count", [1, 3])
def test_coherent_forged_temperature_with_repaired_ledger_rejected(monkeypatch, count):
    request = _request()
    request["segments"] *= count
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    outputs = actual["outputs"]
    capacity, temperature = 500.0, 300.0
    for row in outputs["segments"]:
        row["start_temperature_k"] = temperature
        row["end_temperature_k"] = temperature + 1.0
        row["thermal_storage_change_j"] = capacity * (row["end_temperature_k"] - temperature)
        row["convective_exchange_j"] = row["heat_input_j"] - row["thermal_storage_change_j"]
        row["energy_balance_residual_j"] = 0.0
        temperature = row["end_temperature_k"]
        assert row["heat_input_j"] - row["thermal_storage_change_j"] - row["convective_exchange_j"] == 0.0
    outputs["final_temperature_k"] = temperature
    outputs["maximum_temperature_k"] = temperature
    for total, field in (
        ("total_heat_input_j", "heat_input_j"),
        ("total_storage_change_j", "thermal_storage_change_j"),
        ("total_convective_exchange_j", "convective_exchange_j"),
    ):
        outputs[total] = math.fsum(row[field] for row in outputs["segments"])
    outputs["total_energy_balance_residual_j"] = (
        outputs["total_heat_input_j"] - outputs["total_storage_change_j"] -
        outputs["total_convective_exchange_j"]
    )
    assert outputs["total_energy_balance_residual_j"] == 0.0
    # These rows balance and remain continuous, but violate the governing ODE.
    _checked(monkeypatch, actual, request, rejects=True)


@pytest.mark.parametrize("conductance,duration", [(0, 5), (2, 30), (0.001, 0.1)])
def test_actual_success_without_model_calls_or_mutation(monkeypatch, conductance, duration):
    request = {
        "evaluation": "lumped_thermal_screening",
        "mass_kg": 2,
        "specific_heat_j_kg_k": 500,
        "initial_temperature_k": 300,
        "lumped_biot_number": 0.05,
        "property_source": "Declared smoke-test properties",
        "segments": [{"duration_s": duration, "ambient_temperature_k": 290,
                      "heat_input_w": 40, "conductance_w_k": conductance}],
    }
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    before = deepcopy((actual, request))
    screener = Mock(side_effect=AssertionError("model called during guard"))
    integrator = Mock(side_effect=AssertionError("integrator called during guard"))
    monkeypatch.setattr(thermal, "screen_thermal", screener)
    monkeypatch.setattr(thermal, "integrate_segment", integrator)
    assert validate_thermal_result(actual, request) is None
    assert (actual, request) == before
    assert type(request["mass_kg"]) is int
    assert type(actual["outputs"]["segments"][0]["duration_s"]) is float
    screener.assert_not_called()
    integrator.assert_not_called()


def test_actual_full_128_segment_history(monkeypatch):
    segments = [
        {"duration_s": 10 + i % 3, "ambient_temperature_k": (280, 290, 320)[i % 3],
         "heat_input_w": (0, 40, 0)[i % 3], "conductance_w_k": (2, 0, 2)[i % 3]}
        for i in range(128)
    ]
    request = _request(segments)
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    rows = actual["outputs"]["segments"]
    assert len(rows) == 128
    assert any(row["end_temperature_k"] < row["start_temperature_k"] for row in rows)
    assert any(row["convective_exchange_j"] < 0.0 for row in rows)
    for index, row in enumerate(rows):
        assert type(row["index"]) is int and row["index"] == index
        assert all(type(value) is float for key, value in row.items() if key != "index")
        if index:
            assert row["start_temperature_k"] == rows[index - 1]["end_temperature_k"]
            assert row["cumulative_elapsed_s"] > rows[index - 1]["cumulative_elapsed_s"]
    _checked(monkeypatch, actual, request)


@pytest.mark.parametrize("conductance,heat,ambient,direction", [
    (0, 0, 290, 0), (2, 20, 290, 0), (2, 0, 280, -1), (2, 0, 320, 1),
])
def test_actual_equilibrium_cooling_and_negative_convection(
    monkeypatch, conductance, heat, ambient, direction,
):
    request = _request([{"duration_s": 25, "ambient_temperature_k": ambient,
                         "heat_input_w": heat, "conductance_w_k": conductance}])
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    row = actual["outputs"]["segments"][0]
    start, end = row["start_temperature_k"], row["end_temperature_k"]
    assert (end > start) - (end < start) == direction
    if ambient > start:
        assert row["convective_exchange_j"] < 0.0
    _checked(monkeypatch, actual, request)


@pytest.mark.parametrize("conductance,side", [
    (math.nextafter(0.05, 0.0), -1), (0.05, 0), (math.nextafter(0.05, math.inf), 1),
])
def test_actual_small_x_branch_boundary(monkeypatch, conductance, side):
    request = _request([{"duration_s": 1, "ambient_temperature_k": 290,
                         "heat_input_w": 20, "conductance_w_k": conductance}])
    x = conductance / 500.0
    assert (x > 1e-4) - (x < 1e-4) == side
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    _checked(monkeypatch, actual, request)


def test_actual_subnormal_biot_input_is_admitted(monkeypatch):
    request = _request()
    request["lumped_biot_number"] = math.nextafter(0.0, 1.0)
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    _checked(monkeypatch, actual, request)


@pytest.mark.parametrize("field", [
    "index", "duration_s", "cumulative_elapsed_s", "start_temperature_k", "end_temperature_k",
    "ambient_temperature_k", "heat_input_j", "thermal_storage_change_j", "convective_exchange_j",
    "energy_balance_residual_j",
])
@pytest.mark.parametrize("mutation", ["value", "native_type", "bool"])
def test_every_row_numeric_field_and_native_type(monkeypatch, field, mutation):
    request = _request()
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    row = actual["outputs"]["segments"][0]
    original = row[field]
    if mutation == "value":
        row[field] = original + 1 if field == "index" else math.nextafter(original, math.inf)
    elif mutation == "native_type":
        row[field] = False if field == "index" else int(original)
        assert row[field] == original  # Native type is the sole violation.
    else:
        row[field] = bool(original)
    _checked(monkeypatch, actual, request, rejects=True)


@pytest.mark.parametrize("path,value", [
    (("model_id",), "other_model"), (("status",), "COMPUTED"),
    (("evidence_level",), "validated"), (("aircraft_status",), "safe"),
    (("feasibility",), True), (("limitations",), []), (("reasons",), ["invented"]),
    (("sources",), []), (("sources", 0, "url"), "https://example.invalid/"),
    (("sources", 0, "scope"), "physical validation"),
    (("output_units", "elapsed_s"), "ms"),
    (("output_units", "segments", "end_temperature_k"), "C"),
    (("outputs", "segments", 0, "thermal_storage_change_j"), False),
])
def test_metadata_units_and_boolean_float_mutations(monkeypatch, path, value):
    request = _request()
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    target = actual
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    _checked(monkeypatch, actual, request, rejects=True)


@pytest.mark.parametrize("path", [
    (), ("outputs",), ("outputs", "segments", 0), ("output_units",),
    ("output_units", "segments"), ("sources", 0),
])
@pytest.mark.parametrize("operation", ["add", "remove"])
def test_exact_root_output_row_unit_source_fields(monkeypatch, path, operation):
    request = _request()
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    target = actual
    for key in path:
        target = target[key]
    if operation == "add":
        target["unexpected"] = None
    else:
        del target[next(iter(target))]
    _checked(monkeypatch, actual, request, rejects=True)


@pytest.mark.parametrize("field", ["request_sha256", "evaluation_sha256", "result_sha256"])
def test_thermal_digests_are_absent_not_null_or_recomputed(monkeypatch, field):
    request = _request()
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    assert field not in actual
    actual[field] = "a" * 64
    _checked(monkeypatch, actual, request, rejects=True)


@pytest.mark.parametrize("field,value,status", [
    ("evaluation", "unsupported", "SOLVER_UNSUPPORTED"),
    ("evaluation", 1, "SOLVER_UNSUPPORTED"),
    ("mass_kg", 0, "MODEL_INAPPLICABLE"),
    ("specific_heat_j_kg_k", 0, "MODEL_INAPPLICABLE"),
    ("initial_temperature_k", 0, "MODEL_INAPPLICABLE"),
    ("lumped_biot_number", -0.01, "MODEL_INAPPLICABLE"),
    ("lumped_biot_number", 0.100001, "MODEL_INAPPLICABLE"),
    ("property_source", "  ", "MODEL_INAPPLICABLE"),
    ("segments", [], "MODEL_INAPPLICABLE"),
    ("segments", [{"duration_s": -1, "ambient_temperature_k": 290,
                   "heat_input_w": 20, "conductance_w_k": 2}], "MODEL_INAPPLICABLE"),
])
def test_actual_noncomputed_statuses_deliberately_outside_admission(monkeypatch, field, value, status):
    request = _request()
    request[field] = value
    actual = thermal.screen_thermal(request)
    assert actual["status"] == status
    assert actual["outputs"] == actual["output_units"] == {}
    assert len(actual["reasons"]) == 1
    _checked(monkeypatch, actual, request, rejects=True)


def test_import_time_metadata_snapshot_survives_public_mutation(monkeypatch):
    request = _request()
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    monkeypatch.setattr(thermal, "MODEL_ID", "changed after import")
    original = thermal.LIMITATIONS[:]
    try:
        thermal.LIMITATIONS[:] = ["changed after import"]
        _checked(monkeypatch, actual, request)
    finally:
        thermal.LIMITATIONS[:] = original


@pytest.mark.parametrize("dependency", ["_number", "checked_product", "checked_quotient", "_finite", "expm1"])
@pytest.mark.parametrize("error_type", [ValueError, RuntimeError, KeyboardInterrupt])
def test_unexpected_pure_exceptions_propagate(monkeypatch, dependency, error_type):
    request = _request()
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    error = error_type("pure dependency sentinel")
    owner = guard.math if dependency == "expm1" else thermal
    call = Mock(side_effect=error)
    monkeypatch.setattr(owner, dependency, call)
    observed = _checked(monkeypatch, actual, request, rejects=True, expected_error=error_type)
    assert observed is error
    call.assert_called_once()


@pytest.mark.parametrize("error_type", [OverflowError, ZeroDivisionError])
def test_expected_arithmetic_exceptions_become_scoped_value_error(monkeypatch, error_type):
    request = _request()
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    error = error_type("expected arithmetic sentinel")
    call = Mock(side_effect=error)
    monkeypatch.setattr(thermal, "checked_product", call)
    observed = _checked(monkeypatch, actual, request, rejects=True)
    assert str(observed) == "Thermal arithmetic outside admitted range"
    assert observed.__cause__ is error
    call.assert_called_once()


def _node_tree(nodes):
    """Helper-only aliased JSON, counting each serialized occurrence."""
    cache = {1: 0, 2: [0], 3: {"key": 0}}

    def build(count):
        if count not in cache:
            width = min(8, count - 1)
            quotient, remainder = divmod(count - 1, width)
            cache[count] = [build(quotient + (i < remainder)) for i in range(width)]
        return cache[count]

    return build(nodes)


@pytest.mark.parametrize("scope", ["_INPUT_JSON", "_OUTPUT_JSON"])
@pytest.mark.parametrize("dimension", ["nodes", "depth", "items", "string", "integer"])
def test_walker_only_exact_resource_boundaries(monkeypatch, scope, dimension):
    limits = getattr(guard, scope)
    if dimension == "nodes":
        accepted = _node_tree(limits["max_nodes_including_keys"])
        rejected = _node_tree(limits["max_nodes_including_keys"] + 1)
    elif dimension == "depth":
        accepted = 0
        for _ in range(limits["max_depth"] - 1):
            accepted = [accepted]
        rejected = [accepted]
    elif dimension == "items":
        accepted = [0] * limits["max_container_items"]
        rejected = [0] * (limits["max_container_items"] + 1)
    elif dimension == "string":
        accepted = "x" * limits["max_string_characters"]
        rejected = accepted + "x"
    else:
        accepted = (1 << limits["max_integer_bits"]) - 1
        rejected = 1 << limits["max_integer_bits"]
    calls = _block_models(monkeypatch)
    assert guard._json_walk(accepted, limits) is None
    with pytest.raises(ValueError):
        guard._json_walk(rejected, limits)
    for call in calls:
        call.assert_not_called()


def test_walker_keys_and_aliased_occurrences_each_count(monkeypatch):
    calls = _block_models(monkeypatch)
    leaf = {"key": 0}
    aliased = [leaf, leaf]
    assert aliased[0] is aliased[1]
    for value, nodes in ((leaf, 3), (aliased, 7)):
        limits = {**guard._INPUT_JSON, "max_nodes_including_keys": nodes}
        assert guard._json_walk(value, limits) is None
        with pytest.raises(ValueError):
            guard._json_walk(value, {**limits, "max_nodes_including_keys": nodes - 1})
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("side", ["actual", "request"])
@pytest.mark.parametrize("kind", [dict, list, int, float, str])
def test_json_subclasses_rejected_without_hooks(monkeypatch, side, kind):
    request = _request()
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    hook = Mock(side_effect=AssertionError("foreign hook invoked"))
    foreign = type("Foreign", (kind,), {
        "__eq__": hook, "__iter__": hook, "__deepcopy__": hook, "__float__": hook,
        "__int__": hook, "items": hook, "encode": hook, "__len__": hook,
    })
    bad = foreign()
    # Nested placement also rejects before any envelope equality/preflight.
    if side == "actual":
        actual["sources"][0]["scope"] = bad
    else:
        request["mass_kg"] = bad
    calls = _block_models(monkeypatch)
    preflight = Mock(side_effect=AssertionError("foreign input reached admission"))
    equality = Mock(side_effect=AssertionError("foreign JSON reached equality"))
    monkeypatch.setattr(guard, "_admit", preflight)
    monkeypatch.setattr(guard, "_exact", equality)
    with pytest.raises(ValueError):
        validate_thermal_result(actual, request)
    hook.assert_not_called()
    preflight.assert_not_called()
    equality.assert_not_called()
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("side", ["actual", "request"])
@pytest.mark.parametrize("case", [
    "nan", "infinity", "utf8", "integer", "string", "depth", "items", "cycle", "nodes",
    "nonstring_key", "tuple",
])
def test_json_resources_rejected_before_equality_or_preflight(monkeypatch, side, case):
    request = _request()
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    limits = guard._OUTPUT_JSON if side == "actual" else guard._INPUT_JSON
    if case == "nodes":
        bad = _node_tree(limits["max_nodes_including_keys"] + 1)
    elif case == "depth":
        bad = 0
        for _ in range(limits["max_depth"]):
            bad = [bad]
    elif case == "items":
        bad = [0] * (limits["max_container_items"] + 1)
    elif case == "cycle":
        bad = []
        bad.append(bad)
    else:
        bad = {"nan": math.nan, "infinity": math.inf, "utf8": "\ud800",
               "integer": 1 << 1023, "string": "x" * 2001, "nonstring_key": {1: 0},
               "tuple": (0,)}[case]
    calls = _block_models(monkeypatch)
    preflight = Mock(side_effect=AssertionError("unbounded input reached admission"))
    equality = Mock(side_effect=AssertionError("unbounded JSON reached equality"))
    monkeypatch.setattr(guard, "_admit", preflight)
    monkeypatch.setattr(guard, "_exact", equality)
    with pytest.raises(ValueError):
        validate_thermal_result(bad if side == "actual" else actual,
                                bad if side == "request" else request)
    preflight.assert_not_called()
    equality.assert_not_called()
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("field", [
    "elapsed_s", "final_temperature_k", "maximum_temperature_k", "total_heat_input_j",
    "total_convective_exchange_j", "total_storage_change_j", "total_energy_balance_residual_j",
])
@pytest.mark.parametrize("mutation", ["value", "native_type"])
def test_every_summary_numeric_field_and_native_type(monkeypatch, field, mutation):
    request = _request()
    actual = thermal.screen_thermal(request)
    assert actual["status"] == "SCREENING_COMPUTED"
    original = actual["outputs"][field]
    actual["outputs"][field] = (math.nextafter(original, math.inf) if mutation == "value"
                                else int(original))
    _checked(monkeypatch, actual, request, rejects=True)
