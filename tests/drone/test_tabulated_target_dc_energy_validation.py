"""Full actual V118 captures, validated with every model blocked."""

import importlib
import math
from copy import deepcopy
from decimal import Decimal
from unittest.mock import Mock

import pytest

from physimesh.drone import tabulated_target_dc_energy as energy
from physimesh.drone import tabulated_target_dc_energy_validation as guard
from physimesh.drone.provenance import sha256_record
from tests.drone import test_tabulated_target_dc_energy as fixtures
from tests.drone.test_tabulated_target_dc_power_validation import block_models, rebind


@pytest.fixture(scope="module")
def actual_captures():
    standard = fixtures.request()
    eight = deepcopy(standard)
    eight["segments"] = [
        {**deepcopy(standard["segments"][index % 2]), "id": f"segment-{index}"}
        for index in range(8)
    ]
    captured = [(supplied, energy.evaluate_tabulated_target_dc_energy(supplied))
                for supplied in (standard, eight)]
    for supplied, actual in captured:
        assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
        assert actual["point_result_count"] == len(supplied["segments"])
        assert actual["assembly_inverse_result_count"] == actual["motor_result_count"] == 2 * len(
            supplied["segments"])
        assert actual["forward_evaluation_count"] == 38 * len(supplied["segments"])
    return captured


def block_all_models(monkeypatch):
    calls = block_models(monkeypatch)
    for name in ("tabulated_target_dc_energy", "thermal"):
        module = importlib.import_module("physimesh.drone." + name)
        for field in vars(module).copy():
            if (field.startswith(("evaluate_", "screen_", "integrate_")) or
                    field.endswith("_catalog") or field in ("deepcopy", "_response", "_seal", "_snapshot")):
                call = Mock(side_effect=AssertionError("runtime model/catalog: " + name + "." + field))
                monkeypatch.setattr(module, field, call)
                calls.append(call)
    return calls


@pytest.mark.parametrize("index", [0, 1])
def test_actual_captures(monkeypatch, actual_captures, index):
    supplied, actual = actual_captures[index]
    before = fixtures.encoded((actual, supplied))
    digests = sha256_record(actual), sha256_record(supplied)
    calls = block_all_models(monkeypatch)
    pure = Mock(wraps=guard.validate_tabulated_target_dc_power_result)
    monkeypatch.setattr(guard, "validate_tabulated_target_dc_power_result", pure)
    assert guard.validate_tabulated_target_dc_energy_result(actual, supplied) is None
    assert pure.call_count == len(supplied["segments"])
    for call, row, segment in zip(pure.call_args_list, actual["outputs"]["segments"],
                                  supplied["segments"], strict=True):
        assert call.args[0] is row["actual_power_result"]
        assert call.args[1] is segment["power_request"]
        assert fixtures.encoded(row).count(fixtures.encoded(row["actual_power_result"])) == 1
    assert fixtures.encoded((actual, supplied)) == before
    assert (sha256_record(actual), sha256_record(supplied)) == digests
    for call in calls:
        call.assert_not_called()


def rehash(actual):
    actual["evaluation_sha256"] = sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"})


def checked(monkeypatch, actual, supplied, *, rejects=True):
    before = fixtures.encoded((actual, supplied))
    calls = block_all_models(monkeypatch)
    if rejects:
        with pytest.raises(ValueError):
            guard.validate_tabulated_target_dc_energy_result(actual, supplied)
    else:
        assert guard.validate_tabulated_target_dc_energy_result(actual, supplied) is None
    assert fixtures.encoded((actual, supplied)) == before
    for call in calls:
        call.assert_not_called()


def resummarize(actual, supplied):
    """Repair outer chronology/energy/provenance without changing any actual point."""
    digest, durations = sha256_record(supplied), []
    actual["request_sha256"] = digest
    elapsed, energies = 0.0, {key: [] for key in energy._POWER_FIELDS}
    for index, (row, segment) in enumerate(zip(actual["outputs"]["segments"], supplied["segments"], strict=True)):
        row.update(duration_s=segment["duration_s"], start_time_s=elapsed)
        durations.append(segment["duration_s"])
        elapsed = energy.dc._power_sum(durations)
        row["end_time_s"] = elapsed
        power = row["actual_power_result"]["outputs"]["power"]
        row["energy_j"] = {key: energy.th.checked_product(power[field], segment["duration_s"])
                           for key, field in energy._POWER_FIELDS.items()}
        for key, values in energies.items():
            values.append(row["energy_j"][key])
        row["cumulative_energy_j"] = {key: energy.dc._power_sum(values) for key, values in energies.items()}
        for transfer in actual["transfers"][9 * index:9 * index + 9]:
            transfer["consumer_request_sha256"] = digest
    totals = {key: energy.dc._power_sum(values) for key, values in energies.items()}
    actual["outputs"].update(elapsed_s=elapsed, totals_j=totals, totals_wh={
        key: energy.th.checked_quotient(value, 3600) for key, value in totals.items()})
    rehash(actual)


@pytest.mark.parametrize("field", list(energy._POWER_FIELDS))
@pytest.mark.parametrize("section", ["energy_j", "cumulative_energy_j", "totals_j", "totals_wh"])
@pytest.mark.parametrize("mode", ["value", "bool", "int"])
def test_energy_native_values(monkeypatch, actual_captures, field, section, mode):
    supplied, actual = deepcopy(actual_captures[0])
    values = (actual["outputs"]["segments"][1][section] if section in ("energy_j", "cumulative_energy_j")
              else actual["outputs"][section])
    original = values[field]
    values[field] = original + 0.25 if mode == "value" else bool(original) if mode == "bool" else int(original)
    assert type(values[field]) is not type(original) or values[field] != original
    rehash(actual)
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("field", list(energy._POWER_FIELDS))
def test_forged_joules_with_all_summaries_repaired(monkeypatch, actual_captures, field):
    supplied, actual = deepcopy(actual_captures[0])
    actual["outputs"]["segments"][0]["energy_j"][field] += 1.0
    values = []
    for row in actual["outputs"]["segments"]:
        values.append(row["energy_j"][field])
        row["cumulative_energy_j"][field] = energy.dc._power_sum(values)
    total = energy.dc._power_sum(values)
    actual["outputs"]["totals_j"][field] = total
    actual["outputs"]["totals_wh"][field] = energy.th.checked_quotient(total, 3600)
    rehash(actual)
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("coherent", [False, True])
def test_changed_duration_request_is_data_binding(monkeypatch, actual_captures, coherent):
    supplied, actual = deepcopy(actual_captures[0])
    point_hashes = [sha256_record(row["actual_power_result"]) for row in actual["outputs"]["segments"]]
    stage_bytes = fixtures.encoded(actual["stages"])
    supplied["segments"][0]["duration_s"] = 4
    if coherent:
        resummarize(actual, supplied)
    else:
        actual["request_sha256"] = sha256_record(supplied)
        actual["outputs"]["segments"][0]["duration_s"] = 4
        for transfer in actual["transfers"]:
            transfer["consumer_request_sha256"] = actual["request_sha256"]
        rehash(actual)
    assert point_hashes == [sha256_record(row["actual_power_result"]) for row in actual["outputs"]["segments"]]
    assert fixtures.encoded(actual["stages"]) == stage_bytes
    checked(monkeypatch, actual, supplied, rejects=not coherent)


def changed(value):
    if type(value) is bool:
        return not value
    if type(value) in (int, float):
        return value + 0.25
    if type(value) is str:
        return value + "!"
    if type(value) is list:
        return value + [None]
    if type(value) is dict:
        return {**value, "extra": None}
    return False


@pytest.mark.parametrize("field", sorted(guard._STATIC) + ["diagnostics_complete", "reasons"])
def test_root_catalog_metadata(monkeypatch, actual_captures, field):
    supplied, actual = deepcopy(actual_captures[0])
    actual[field] = changed(actual[field])
    rehash(actual)
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("field", list(energy._COUNTS))
@pytest.mark.parametrize("mode", ["value", "float", "bool", "zero"])
def test_root_exact_native_counts(monkeypatch, actual_captures, field, mode):
    supplied, actual = deepcopy(actual_captures[1])
    old = actual[field]
    actual[field] = {"value": old + 1, "float": float(old), "bool": bool(old), "zero": 0}[mode]
    rehash(actual)
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("field", ["stage", "inputs", "inputs_sha256", "result_sha256"])
@pytest.mark.parametrize("index", [0, 1])
def test_each_stage_field(monkeypatch, actual_captures, field, index):
    supplied, actual = deepcopy(actual_captures[0])
    stage = actual["stages"][index]
    stage[field] = changed(stage[field])
    rehash(actual)
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("field", [
    "from_stage", "from_field", "to_stage", "to_field", "value", "unit",
    "producer_result_sha256", "consumer_request_sha256",
])
@pytest.mark.parametrize("index", [0, 8, 9, 17])
def test_each_transfer_field(monkeypatch, actual_captures, field, index):
    supplied, actual = deepcopy(actual_captures[0])
    transfer = actual["transfers"][index]
    transfer[field] = changed(transfer[field])
    rehash(actual)
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("case", ["row_extra", "row_missing", "outputs_extra", "outputs_missing",
                                  "root_extra", "root_missing", "stage_extra", "transfer_extra",
                                  "stages_short", "transfers_short", "rows_reversed", "transfer_order"])
def test_closed_shapes_and_order(monkeypatch, actual_captures, case):
    supplied, actual = deepcopy(actual_captures[0])
    row = actual["outputs"]["segments"][0]
    if case.endswith("extra"):
        {"row_extra": row, "outputs_extra": actual["outputs"], "root_extra": actual,
         "stage_extra": actual["stages"][0], "transfer_extra": actual["transfers"][0]}[case]["extra"] = None
    elif case.endswith("missing"):
        owner, field = {"row_missing": (row, "energy_j"), "outputs_missing": (actual["outputs"], "totals_j"),
                        "root_missing": (actual, "runtime_identity")}[case]
        owner.pop(field)
    elif case.endswith("short"):
        actual["stages" if case == "stages_short" else "transfers"].pop()
    else:
        (actual["outputs"]["segments"] if case == "rows_reversed" else actual["transfers"]).reverse()
    rehash(actual)
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("field", ["segment_id", "duration_s", "start_time_s", "end_time_s"])
@pytest.mark.parametrize("mode", ["value", "native"])
def test_chronological_row_bindings(monkeypatch, actual_captures, field, mode):
    supplied, actual = deepcopy(actual_captures[0])
    row = actual["outputs"]["segments"][0]
    old = row[field]
    if mode == "native":
        row[field] = False if field == "segment_id" else float(old) if type(old) is int else int(old)
    else:
        row[field] = changed(old)
    assert type(row[field]) is not type(old) or row[field] != old
    rehash(actual)
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("scope", ["segments", "elapsed_s", "totals_j", "totals_wh",
                                   "all_motors_within_declared_limits", "point_outputs_only"])
def test_catalog_units_scope(monkeypatch, actual_captures, scope):
    supplied, actual = deepcopy(actual_captures[0])
    if scope == "point_outputs_only":
        actual["output_units"]["segments"]["actual_power_result"]["request_sha256"] = "1"
    else:
        actual["output_units"][scope] = changed(actual["output_units"][scope])
    rehash(actual)
    checked(monkeypatch, actual, supplied)


def bind_points(actual, supplied):
    """Repair all enclosing hashes and transfers around retained actual point data."""
    for index, (row, segment) in enumerate(zip(actual["outputs"]["segments"], supplied["segments"], strict=True)):
        point = row["actual_power_result"]
        point["request_sha256"] = sha256_record(segment["power_request"])
        rebind(point)
        digest = sha256_record(point)
        actual["stages"][index].update(inputs=deepcopy(segment["power_request"]),
                                        inputs_sha256=point["request_sha256"], result_sha256=digest)
        for transfer, field in zip(actual["transfers"][9 * index:9 * index + 9],
                                   energy._POWER_FIELDS.values(), strict=True):
            transfer.update(value=point["outputs"]["power"][field], producer_result_sha256=digest)
    resummarize(actual, supplied)


@pytest.mark.parametrize("field", list(energy._POWER_FIELDS.values()) + ["all_motors_within_declared_limits"])
def test_full_point_power_fields_with_outer_arithmetic_repaired(monkeypatch, actual_captures, field):
    supplied, actual = deepcopy(actual_captures[0])
    power = actual["outputs"]["segments"][0]["actual_power_result"]["outputs"]["power"]
    power[field] = changed(power[field])
    bind_points(actual, supplied)
    checked(monkeypatch, actual, supplied)


def test_forged_motor_and_point_totals_with_all_outer_bindings_repaired(monkeypatch, actual_captures):
    supplied, actual = deepcopy(actual_captures[0])
    power = actual["outputs"]["segments"][0]["actual_power_result"]["outputs"]["power"]
    motor = power["motors"][0]
    motor["actual_motor_result"]["outputs"]["total_loss_w"] += 1.0
    motor["allocated_heat_w"] += 0.5
    motor["unallocated_loss_w"] += 0.5
    for field, delta in (("total_motor_loss_w", 1.0), ("total_allocated_motor_heat_w", 0.5),
                         ("total_unallocated_motor_loss_w", 0.5), ("total_heat_w", 0.5)):
        power[field] += delta
    bind_points(actual, supplied)
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("case", ["selected_content", "selected_digest", "unretained_digest"])
def test_nested_selected_and_unretained_trace_boundary(monkeypatch, actual_captures, case):
    supplied, actual = deepcopy(actual_captures[0])
    point = actual["outputs"]["segments"][0]["actual_power_result"]
    assembly = point["outputs"]["assembly"]
    target = assembly["outputs"]["rotors"][0]["actual_target_result"]
    if case == "selected_content":
        forward = target["outputs"]["actual_forward_result"]
        forward["outputs"]["radii_m"][0] += 0.001
        rehash(forward)
        target["trace"][-1]["full_actual_result_sha256"] = sha256_record(forward)
    else:
        index = 0 if case == "unretained_digest" else -1
        assert len(target["trace"]) > 2
        target["trace"][index]["full_actual_result_sha256"] = "0123456789abcdef" * 4
    rehash(target)
    assembly["stages"][1]["result_sha256"] = sha256_record(target)
    rehash(assembly)
    bind_points(actual, supplied)
    checked(monkeypatch, actual, supplied, rejects=case != "unretained_digest")


def test_lower_declared_limit_truthfully_preserving_flag(monkeypatch, actual_captures):
    supplied, actual = deepcopy(actual_captures[0])
    motor = supplied["segments"][0]["power_request"]["motors"][0]
    motor["declared_limits"]["maximum_current_a"] = 5000.0
    retained = actual["outputs"]["segments"][0]["actual_power_result"]["outputs"]["power"]["motors"][0]
    retained["actual_motor_request"]["declared_limits"] = deepcopy(motor["declared_limits"])
    assert retained["actual_motor_result"]["outputs"]["current_a"] < 5000.0
    assert retained["actual_motor_result"]["outputs"]["limit_checks"]["current"] is True
    bind_points(actual, supplied)
    checked(monkeypatch, actual, supplied, rejects=False)


def test_private_import_catalog_and_power_fields(monkeypatch, actual_captures):
    supplied, actual = actual_captures[0]
    public = energy.tabulated_target_dc_energy_catalog()
    public["limits"]["output_json"]["max_depth"] = 0
    public["point_catalog"]["limitations"].clear()
    public["limitations"].clear()
    public["output_field_units"]["segments"]["actual_power_result"].clear()
    public["power_fields"].clear()
    monkeypatch.setattr(energy, "_POWER_FIELDS", {})
    monkeypatch.setattr(energy, "_COUNTS", {})
    checked(monkeypatch, actual, supplied, rejects=False)


@pytest.mark.parametrize("case,status", [
    ("unsupported", "SOLVER_UNSUPPORTED"), ("unbracketed", "TARGET_NOT_BRACKETED"),
    ("iteration", "ITERATION_LIMIT"), ("domain", "MODEL_INAPPLICABLE"),
    ("numerical", "NUMERICAL_LIMIT"), ("execution", "EXECUTION_FAILED"),
])
@pytest.mark.parametrize("late", [False, True])
def test_actual_v118_noncomputed_deliberately_rejected(monkeypatch, case, status, late):
    supplied = fixtures.request()
    supplied["segments"][1]["power_request"] = deepcopy(supplied["segments"][0]["power_request"])
    target = supplied["segments"][int(late)]["power_request"]["assembly"]["rotors"][0]["target_template"]
    if case == "unsupported":
        supplied["evaluation"] = "unsupported"
    elif case == "unbracketed":
        target["target_thrust_n"] = 1e12
    elif case == "iteration":
        target["max_evaluations"] = 2
    elif case == "domain":
        target["rotor_template"]["stations"][0]["chord_m"] = -1
    elif case == "numerical":
        fixtures.numerical_target(supplied["segments"][int(late)]["power_request"])
    with monkeypatch.context() as patch:
        if case == "execution":
            patch.setattr(energy.point.dc, "_compute", Mock(side_effect=RuntimeError("capture execution fault")))
        actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert actual["status"] == status, actual["reasons"]
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("case", ["late_id", "duplicate_id", "late_motor", "point_work", "global_work"])
def test_changed_invalid_request_runs_actual_preflight(monkeypatch, actual_captures, case):
    supplied, actual = deepcopy(actual_captures[1])
    segment = supplied["segments"][-1]
    if case == "late_id":
        segment["id"] = "x" * 1993
    elif case == "duplicate_id":
        segment["id"] = supplied["segments"][0]["id"]
    elif case == "late_motor":
        segment["power_request"]["motors"][-1]["parameters"]["motor_constant_si"] = 0
    else:
        for entry in supplied["segments"]:
            for rotor in entry["power_request"]["assembly"]["rotors"]:
                rotor["target_template"]["rotor_template"]["annuli"] = 512
                rotor["target_template"]["max_evaluations"] = 8
        # Eight points * two rotors * 8 * 512 = 65536, admitted before this excess.
        segment["power_request"]["assembly"]["rotors"][-1]["target_template"]["max_evaluations"] = (
            64 if case == "point_work" else 9)
    actual["request_sha256"] = sha256_record(supplied)
    rehash(actual)
    preflight = Mock(wraps=energy._preflight)
    monkeypatch.setattr(energy, "_preflight", preflight)
    checked(monkeypatch, actual, supplied)
    preflight.assert_called_once_with(supplied)


def test_id_exact_1992_boundary_with_consistent_provenance(monkeypatch, actual_captures):
    supplied, actual = deepcopy(actual_captures[0])
    supplied["segments"][0]["id"] = "x" * 1992
    actual["outputs"]["segments"][0]["segment_id"] = "x" * 1992
    stage = "segment:" + "x" * 1992
    actual["stages"][0]["stage"] = stage
    for transfer in actual["transfers"][:9]:
        transfer["from_stage"] = stage
    resummarize(actual, supplied)
    checked(monkeypatch, actual, supplied, rejects=False)


@pytest.mark.parametrize("scope", ["input_json", "output_json", "point_input_json", "point_output_json"])
@pytest.mark.parametrize("resource", ["nodes", "depth", "container", "string", "integer"])
def test_helper_only_exact_json_limits(scope, resource):
    limits = guard._CATALOG["limits"][scope]
    if resource == "nodes":
        accepted = fixtures.node_tree(limits["max_nodes_including_keys"], limits["max_container_items"])
        refused = fixtures.node_tree(limits["max_nodes_including_keys"] + 1, limits["max_container_items"])
    elif resource == "depth":
        accepted = 0
        for _ in range(limits["max_depth"] - 1):
            accepted = [accepted]
        refused = [accepted]
    elif resource == "container":
        accepted = [0] * limits["max_container_items"]
        refused = accepted + [0]
    elif resource == "string":
        accepted = "x" * limits["max_string_characters"]
        refused = accepted + "x"
    else:
        accepted = (1 << limits["max_integer_bits"]) - 1
        refused = accepted + 1
    assert guard._json_walk(accepted, limits) is None
    with pytest.raises(ValueError):
        guard._json_walk(refused, limits)


def test_walker_counts_keys_and_alias_occurrences():
    limits = {**guard._CATALOG["limits"]["input_json"], "max_nodes_including_keys": 7}
    shared = [0, 0]
    assert guard._json_walk([shared, shared], limits) is None
    with pytest.raises(ValueError):
        guard._json_walk({"key": [shared, shared]}, limits)


@pytest.mark.parametrize("scope", ["actual", "request"])
@pytest.mark.parametrize("case", ["nan", "infinity", "utf8", "integer", "string", "depth", "container",
                                  "cycle", "tuple", "decimal", "foreign_object", "key", "nodes"])
def test_full_walks_refuse_before_preflight_hash_or_point(monkeypatch, actual_captures, scope, case):
    supplied, actual = deepcopy(actual_captures[0])
    limits = guard._CATALOG["limits"]["output_json" if scope == "actual" else "input_json"]
    values = {"nan": math.nan, "infinity": math.inf, "utf8": "\ud800", "integer": 1 << 1023,
              "string": "x" * 2001, "container": [0] * (limits["max_container_items"] + 1),
              "tuple": (1,), "decimal": Decimal(1), "foreign_object": object(), "key": {1: 0}}
    bad = values.get(case)
    if case == "depth":
        bad = 0
        for _ in range(limits["max_depth"]):
            bad = [bad]
    elif case == "cycle":
        bad = []
        bad.append(bad)
    elif case == "nodes":
        bad = fixtures.node_tree(limits["max_nodes_including_keys"] + 1, limits["max_container_items"])
    (actual if scope == "actual" else supplied)["untrusted"] = bad
    calls = block_all_models(monkeypatch)
    sentinels = []
    for owner, name in ((energy, "_preflight"), (guard, "sha256_record"),
                        (guard, "validate_tabulated_target_dc_power_result"), (guard, "_exact")):
        sentinel = Mock(side_effect=AssertionError("must complete full builtin walks first"))
        monkeypatch.setattr(owner, name, sentinel)
        sentinels.append(sentinel)
    with pytest.raises(ValueError):
        guard.validate_tabulated_target_dc_energy_result(actual, supplied)
    for call in calls + sentinels:
        call.assert_not_called()


@pytest.mark.parametrize("scope", ["actual", "request"])
@pytest.mark.parametrize("builtin", [dict, list, int, float, str])
def test_foreign_subclasses_call_no_hooks(monkeypatch, actual_captures, scope, builtin):
    supplied, actual = deepcopy(actual_captures[0])
    hooks = []

    def forbidden(self, *args, **kwargs):
        hooks.append("foreign hook")
        raise AssertionError("foreign hook called")

    foreign = type("Foreign", (builtin,), {name: forbidden for name in (
        "__deepcopy__", "__eq__", "__iter__", "__float__", "__int__", "items", "bit_length", "encode")})
    value = foreign({}) if builtin is dict else foreign([]) if builtin is list else foreign(1)
    (actual if scope == "actual" else supplied)["untrusted"] = value
    calls = block_all_models(monkeypatch)
    with pytest.raises(ValueError):
        guard.validate_tabulated_target_dc_energy_result(actual, supplied)
    assert hooks == []
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("scope", ["point_input_json", "point_output_json"])
@pytest.mark.parametrize("index", [0, 1])
def test_independent_point_walk_before_full_pure_guard(monkeypatch, actual_captures, scope, index):
    supplied, actual = actual_captures[0]
    calls = block_all_models(monkeypatch)
    original, seen = guard._json_walk, []
    pure = Mock(wraps=guard.validate_tabulated_target_dc_power_result)
    monkeypatch.setattr(guard, "validate_tabulated_target_dc_power_result", pure)

    def walk(value, limits):
        if limits is guard._CATALOG["limits"][scope]:
            seen.append(value)
            if len(seen) == index + 1:
                raise ValueError("independent point budget sentinel")
        return original(value, limits)

    monkeypatch.setattr(guard, "_json_walk", walk)
    with pytest.raises(ValueError, match="independent point budget sentinel"):
        guard.validate_tabulated_target_dc_energy_result(actual, supplied)
    assert pure.call_count == index
    expected = (supplied["segments"][index]["power_request"] if scope == "point_input_json"
                else actual["outputs"]["segments"][index]["actual_power_result"])
    assert seen[-1] is expected
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("dependency", ["preflight", "hash", "point", "product", "sum"])
@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt, OverflowError, ZeroDivisionError])
def test_pure_dependency_exception_lifecycle(monkeypatch, actual_captures, dependency, error_type):
    supplied, actual = actual_captures[0]
    before = fixtures.encoded((actual, supplied))
    calls = block_all_models(monkeypatch)
    owner, name = {"preflight": (energy, "_preflight"), "hash": (guard, "sha256_record"),
                   "point": (guard, "validate_tabulated_target_dc_power_result"),
                   "product": (energy.th, "checked_product"), "sum": (energy.dc, "_power_sum")}[dependency]
    fault = error_type("private pure dependency fault")
    sentinel = Mock(side_effect=fault)
    monkeypatch.setattr(owner, name, sentinel)
    expected = ValueError if error_type in (OverflowError, ZeroDivisionError) else error_type
    with pytest.raises(expected) as raised:
        guard.validate_tabulated_target_dc_energy_result(actual, supplied)
    assert sentinel.called
    if expected is ValueError:
        assert raised.value.__cause__ is fault
    else:
        assert raised.value is fault
    assert fixtures.encoded((actual, supplied)) == before
    for call in calls:
        call.assert_not_called()


def test_point_guard_must_return_none(monkeypatch, actual_captures):
    supplied, actual = actual_captures[0]
    monkeypatch.setattr(guard, "validate_tabulated_target_dc_power_result", Mock(return_value=False))
    checked(monkeypatch, actual, supplied)
