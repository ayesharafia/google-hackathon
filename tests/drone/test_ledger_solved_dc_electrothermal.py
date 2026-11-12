"""V100 wrapper contracts exercised through the real accepted V99 fixtures."""

from copy import deepcopy

import pytest

from physimesh.drone import ledger_solved_dc_electrothermal as m
from physimesh.drone.provenance import sha256_record

from .test_ledger_static_wrench import request as ledger_solve_request
from .test_solved_dc_power import bridge_request


@pytest.fixture
def wrapper_request():
    frozen = ledger_solve_request()
    point = bridge_request.__wrapped__()
    point["solve"] = frozen["solve_template"]
    # Translate ledger and rotor centers together: a nonzero actual CG without
    # changing the accepted target wrench or evaluating another model.
    shift = [.25, -.125, .05]
    for item in frozen["ledger"]["items"]:
        item["cg_body_m"] = [a + b for a, b in zip(item["cg_body_m"], shift, strict=True)]
    for rotor in point["solve"]["assembly_template"]["rotors"]:
        rotor["center_body_m"] = [a + b for a, b in zip(rotor["center_body_m"], shift, strict=True)]
    return {
        "evaluation": m.EVALUATION, "ledger": frozen["ledger"],
        "mission_template": {
            "evaluation": m.mission.EVALUATION, "usable_energy_j": 100000, "reserve_fraction": .1,
            "thermal_body": {
                "mass_kg": 2, "specific_heat_j_kg_k": 1000, "initial_temperature_k": 300,
                "lumped_biot_number": .05, "property_source": "Synthetic accepted fixture",
            },
            "segments": [{
                "id": name, "duration_s": duration, "point": deepcopy(point),
                "thermal": {"ambient_temperature_k": 290, "conductance_w_k": conductance},
            } for name, duration, conductance in (("first", 10, 2), ("second", 20, 4))],
        },
    }


@pytest.fixture
def observed(wrapper_request, monkeypatch):
    calls = {key: [] for key in ("ledger", "mission", "point", "thermal")}

    def spy(key, original):
        def wrapped(payload):
            saved = deepcopy(payload)
            raw = original(payload)
            calls[key].append((saved, raw))
            return raw
        return wrapped

    for key, owner, name in (
        ("ledger", m.ml, "evaluate_mass_ledger"),
        ("mission", m.mission, "evaluate_solved_dc_electrothermal"),
        ("point", m.mission.dp, "evaluate_solved_dc_power"),
        ("thermal", m.mission.th, "screen_thermal"),
    ):
        monkeypatch.setattr(owner, name, spy(key, getattr(owner, name)))
    return wrapper_request, calls


def assert_atomic(result, status="EXECUTION_FAILED"):
    assert result["status"] == status
    assert result["diagnostics_complete"] is False and result["reasons"]
    assert result["outputs"] == result["output_units"] == result["transfers"] == {}
    assert result["stages"] == []


def test_real_met_multi_segment_smoke_and_provenance(observed):
    request, calls = observed
    before = deepcopy(request)
    result = m.evaluate_ledger_solved_dc_electrothermal(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert {key: len(value) for key, value in calls.items()} == {
        "ledger": 1, "mission": 1, "point": 2, "thermal": 1,
    }
    assert request == before and result["request_sha256"] == sha256_record(before)
    ledger_request, ledger = calls["ledger"][0]
    instantiated, mission = calls["mission"][0]
    outputs = ledger["outputs"]
    assert outputs["total_mass_kg"] == 4 and outputs["cg_body_m"] == [.25, -.125, .05]
    for segment, transfer in zip(instantiated["segments"], result["transfers"]["mass_cg"], strict=True):
        assembly = segment["point"]["solve"]["assembly_template"]
        assert assembly["mass_kg"] == transfer["mass_kg"] == outputs["total_mass_kg"]
        assert assembly["cg_body_m"] == transfer["cg_body_m"] == outputs["cg_body_m"]
        assert transfer["segment_id"] == segment["id"]
    assert instantiated["thermal_body"] == before["mission_template"]["thermal_body"]
    assert calls["thermal"][0][0]["mass_kg"] == 2 != outputs["total_mass_kg"]
    assert result["outputs"] == {"ledger": outputs, "mission": mission["outputs"]}
    assert result["output_units"] == {"ledger": ledger["output_units"], "mission": mission["output_units"]}
    assert result["stages"] == [
        {"stage_id": "ledger", "request_sha256": sha256_record(ledger_request),
         "result_sha256": sha256_record(ledger)},
        {"stage_id": "mission", "request_sha256": sha256_record(instantiated),
         "result_sha256": sha256_record(mission), "stages": mission["stages"]},
    ]
    assert result["transfers"]["mission"] == mission["transfers"]
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[key] == "NOT_ESTABLISHED"
    assert result["feasibility"] is result["aircraft_status"] is None


@pytest.mark.parametrize("unmet_index", (0, 1))
def test_actual_unmet_retains_reached_prefix_only(observed, unmet_index):
    request, calls = observed
    segments = request["mission_template"]["segments"]
    segments.append({**deepcopy(segments[-1]), "id": "never_reached"})
    segments[unmet_index]["point"]["solve"].update(
        max_evaluations=2, required_net_force_body_n=[1e9, 0, 0],
    )
    result = m.evaluate_ledger_solved_dc_electrothermal(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(calls["ledger"]) == len(calls["mission"]) == 1
    assert len(calls["point"]) == unmet_index + 1 and calls["thermal"] == []
    out = result["outputs"]["mission"]
    assert out["mission_state"] == "STOPPED_AT_UNMET_SEGMENT"
    assert len(out["power_segments"]) == unmet_index + 1
    assert out["power_segments"][-1]["power"] is None
    assert out["energy"] is out["thermal"] is None
    assert result["transfers"]["mission"] == []
    assert len(result["transfers"]["mass_cg"]) == 3
    assert len(result["stages"][1]["stages"]) == unmet_index + 1


@pytest.mark.parametrize("defect", (
    "mass_duplicate", "cg_duplicate", "invalid_last", "global_work", "bad_ledger",
    "duplicate_segment", "capacity", "reserve", "duration_loss",
))
def test_all_preflight_before_any_evaluator(observed, defect):
    request, calls = observed
    template = request["mission_template"]
    segments = template["segments"]
    assembly = segments[-1]["point"]["solve"]["assembly_template"]
    if defect == "mass_duplicate":
        assembly["mass_kg"] = 4
    elif defect == "cg_duplicate":
        assembly["cg_body_m"] = [.25, -.125, .05]
    elif defect == "invalid_last":
        segments[-1]["point"]["motors"][-1]["parameters"]["motor_constant_si"] = False
    elif defect == "global_work":
        for segment in segments:
            solve = segment["point"]["solve"]
            solve["max_evaluations"] = 32
            for node in solve["assembly_template"]["graph"]["nodes"]:
                if node["model"] == "isolated_hover_bemt_experimental":
                    node["inputs"]["annuli"] = 256
    elif defect == "bad_ledger":
        request["ledger"]["items"][-1]["name"] = request["ledger"]["items"][0]["name"]
    elif defect == "duplicate_segment":
        segments[-1]["id"] = segments[0]["id"]
    elif defect == "capacity":
        template["thermal_body"].update(mass_kg=1e308, specific_heat_j_kg_k=1e308)
    elif defect == "reserve":
        template["reserve_fraction"] = 1e-200
    else:
        segments[0]["duration_s"] = 1e200
    result = m.evaluate_ledger_solved_dc_electrothermal(request)
    assert_atomic(result, "GRAPH_INVALID")
    assert "request_sha256" not in result
    assert all(value == [] for value in calls.values())


@pytest.mark.parametrize("defect", ("total", "cg", "inertia", "payload", "categories"))
def test_coherent_ledger_forgeries_are_bound_to_declared_items(observed, monkeypatch, defect):
    request, calls = observed
    original = m.ml.evaluate_mass_ledger

    def forged(payload):
        raw = original(payload)
        out = raw["outputs"]
        if defect == "total":
            out["total_mass_kg"] *= 2
            out["payload_kg"] *= 2
            out["by_category_kg"] = {key: value * 2 for key, value in out["by_category_kg"].items()}
            out["inertia_cg_body_kgm2"] = [[value * 2 for value in row]
                                         for row in out["inertia_cg_body_kgm2"]]
        elif defect == "cg":
            out["cg_body_m"][0] += 1
        elif defect == "inertia":
            for axis in range(3):
                out["inertia_cg_body_kgm2"][axis][axis] += 1
        else:
            # Keep total and category sum consistent while changing allocation.
            source, target = ("structure", "payload") if defect == "payload" else ("structure", "other")
            out["by_category_kg"][source] -= 1
            out["by_category_kg"][target] += 1
            out["payload_kg"] = out["by_category_kg"]["payload"]
        return raw

    monkeypatch.setattr(m.ml, "evaluate_mass_ledger", forged)
    assert_atomic(m.evaluate_ledger_solved_dc_electrothermal(request))
    assert len(calls["ledger"]) == 1
    assert calls["mission"] == calls["point"] == calls["thermal"] == []


MISSION_DEFECTS = (
    (("status",), "EXECUTION_FAILED"),
    (("evaluation",), "wrong"),
    (("request_sha256",), "0" * 64),
    (("physical_validation",), "ESTABLISHED"),
    (("numerical_qualification",), "ESTABLISHED"),
    (("runtime_identity",), "ESTABLISHED"),
    (("feasibility",), False),
    (("diagnostics_complete",), 1),
    (("reasons",), ["refused"]),
    (("stages", 0, "stage_id"), "point_1"),
    (("stages", 0, "request_sha256"), "0" * 64),
    (("stages", 0, "result_sha256"), "A" * 64),
    (("stages", 0, "stages", 0, "request_sha256"), "0" * 64),
    (("stages", 0, "stages", 0, "stages", 0, "request_sha256"), "0" * 64),
    (("stages", 0, "stages", 0, "stages", 1, "request_sha256"), "0" * 64),
    (("stages", 0, "stages", 1, "request_sha256"), "0" * 64),
    (("stages", 0, "stages", 1, "result_sha256"), "not-a-digest"),
    (("stages", -1, "request_sha256"), "0" * 64),
    (("transfers", 0, "heat_input_w"), False),
    (("outputs", "energy", "total_energy_j"), 1),
    (("outputs", "energy", "elapsed_s"), False),
    (("outputs", "thermal", "final_temperature_k"), 1),
    (("outputs", "thermal", "segments", 0, "index"), False),
    (("outputs", "thermal", "segments", 0, "index"), 0.0),
    (("outputs", "power_segments", 0, "duration_s"), True),
    (("outputs", "power_segments", 0, "solve", "evaluations_used"), False),
    (("outputs", "power_segments", 0, "power", "auxiliary_heat_w"), False),
    (("output_units", "energy", "total_energy_j"), "W"),
    (("output_units", "thermal", "segments", "index"), "s"),
    (("output_units", "power_segments", 0, "duration_s"), "K"),
)


@pytest.mark.parametrize("path,value", MISSION_DEFECTS)
def test_actual_mission_envelope_and_retained_contract_forgeries(observed, monkeypatch, path, value):
    request, calls = observed
    original = m.mission.evaluate_solved_dc_electrothermal

    def forged(payload):
        raw = original(payload)
        assert raw["status"] == "COMPUTED_EXPERIMENTAL"
        target = raw
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return raw

    monkeypatch.setattr(m.mission, "evaluate_solved_dc_electrothermal", forged)
    result = m.evaluate_ledger_solved_dc_electrothermal(request)
    assert_atomic(result)
    assert len(calls["ledger"]) == len(calls["mission"]) == 1
    assert len(calls["point"]) == 2 and len(calls["thermal"]) == 1


def test_copy_isolation_of_inputs_returned_children_and_output_branches(observed, monkeypatch):
    request, calls = observed
    before = deepcopy(request)
    original_ledger = m.ml.evaluate_mass_ledger
    original_mission = m.mission.evaluate_solved_dc_electrothermal

    def ledger_mutates_input(payload):
        raw = original_ledger(payload)
        payload.clear()
        return raw

    def mission_mutates_input(payload):
        raw = original_mission(payload)
        payload.clear()
        return raw

    monkeypatch.setattr(m.ml, "evaluate_mass_ledger", ledger_mutates_input)
    monkeypatch.setattr(m.mission, "evaluate_solved_dc_electrothermal", mission_mutates_input)
    result = m.evaluate_ledger_solved_dc_electrothermal(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL" and request == before
    saved = deepcopy(result)
    calls["ledger"][0][1]["outputs"]["cg_body_m"][0] = 999
    calls["mission"][0][1]["outputs"]["thermal"]["final_temperature_k"] = 999
    request["ledger"]["items"][0]["mass_kg"] = 999
    assert result == saved
    result["transfers"]["mass_cg"][0]["cg_body_m"][0] = 999
    assert result["transfers"]["mass_cg"][1]["cg_body_m"] == [.25, -.125, .05]
    assert result["outputs"]["ledger"]["cg_body_m"] == [.25, -.125, .05]


@pytest.mark.parametrize("child", ("ledger", "mission"))
@pytest.mark.parametrize("exception", (RuntimeError, KeyboardInterrupt, SystemExit))
def test_exceptions_are_atomic_but_baseexceptions_propagate(observed, monkeypatch, child, exception):
    request, calls = observed
    owner, name = ((m.ml, "evaluate_mass_ledger") if child == "ledger"
                   else (m.mission, "evaluate_solved_dc_electrothermal"))

    def raises(payload):
        raise exception("private exception text")

    monkeypatch.setattr(owner, name, raises)
    if exception is RuntimeError:
        result = m.evaluate_ledger_solved_dc_electrothermal(request)
        assert_atomic(result)
        assert "private exception text" not in str(result)
    else:
        with pytest.raises(exception, match="private exception text"):
            m.evaluate_ledger_solved_dc_electrothermal(request)
    assert calls["point"] == calls["thermal"] == []


class CustomDict(dict):
    pass


class CustomList(list):
    pass


class CustomInt(int):
    pass


class CustomString(str):
    pass


@pytest.mark.parametrize("value", (
    CustomDict(), CustomList(), CustomInt(1), CustomString("x"), (1,), {1: "value"},
    {CustomString("key"): 1}, float("nan"), float("inf"), -float("inf"),
    1 << 1023, "x" * 2001, "\ud800", [None] * 257,
))
def test_outer_json_adversaries_prevent_all_calls(observed, value):
    request, calls = observed
    request["unexpected"] = value
    with pytest.raises((ValueError, UnicodeError)):
        m._outer_json(request)
    assert_atomic(m.evaluate_ledger_solved_dc_electrothermal(request), "GRAPH_INVALID")
    assert all(value == [] for value in calls.values())


def test_outer_json_exact_depth_node_and_scalar_boundaries():
    value = 0
    for _ in range(12):
        value = [value]
    m._outer_json(value)  # Root depth is one; final scalar is at depth 13.
    with pytest.raises(ValueError):
        m._outer_json([value])
    # Exact 98,304 visited nodes, at most 256 items in any container.
    value = [[None] * 256 for _ in range(255)]
    value.append([[None] * 256 for _ in range(127)] + [None] * 128)
    m._outer_json(value)
    value[-1].append(None)
    with pytest.raises(ValueError):
        m._outer_json(value)
    m._outer_json({"x" * 2000: [(1 << 1023) - 1, -((1 << 1023) - 1), True, None]})


@pytest.mark.parametrize("path", (
    ("ledger", "items", 0, "mass_kg"),
    ("ledger", "items", 0, "cg_body_m", 0),
    ("mission_template", "usable_energy_j"),
    ("mission_template", "thermal_body", "mass_kg"),
    ("mission_template", "segments", 1, "duration_s"),
    ("mission_template", "segments", 1, "thermal", "conductance_w_k"),
))
def test_builtin_json_boolean_is_not_a_numeric_input(observed, path):
    request, calls = observed
    target = request
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = True
    assert_atomic(m.evaluate_ledger_solved_dc_electrothermal(request), "GRAPH_INVALID")
    assert all(value == [] for value in calls.values())


@pytest.mark.parametrize("path,value", (
    ((), []),
    ((), CustomDict()),
    (("outputs",), []),
    (("output_units",), []),
    (("stages",), {}),
    (("stages", 0), []),
    (("stages", 0, "stages"), {}),
    (("transfers",), {}),
    (("transfers", 0), []),
    (("outputs", "energy"), []),
    (("outputs", "energy", "segments"), {}),
    (("outputs", "thermal"), []),
    (("outputs", "power_segments"), {}),
    (("outputs", "power_segments", 0), CustomDict()),
    (("limitations",), "unqualified"),
    (("reasons",), ()),
    (("output_units", "power_segments", 0, "power", "motors", 0, "motor", "current_a"), "W"),
    (("outputs", "power_segments", 0, "power", "motors", 0, "motor", "limit_checks", "current"), 1),
))
def test_invalid_actual_envelope_container_and_leaf_types(observed, monkeypatch, path, value):
    request, calls = observed
    original = m.mission.evaluate_solved_dc_electrothermal

    def forged(payload):
        raw = original(payload)
        if not path:
            return value
        target = raw
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return raw

    monkeypatch.setattr(m.mission, "evaluate_solved_dc_electrothermal", forged)
    assert_atomic(m.evaluate_ledger_solved_dc_electrothermal(request))
    assert len(calls["ledger"]) == len(calls["mission"]) == 1


@pytest.mark.parametrize("field", ("stages", "transfers", "energy"))
def test_unexpected_deep_or_large_actual_metadata_fails_closed(observed, monkeypatch, field):
    request, calls = observed
    original = m.mission.evaluate_solved_dc_electrothermal

    def forged(payload):
        raw = original(payload)
        if field == "stages":
            deep = "x"
            for _ in range(200):
                deep = [deep]
            raw["stages"][0]["stage_id"] = deep
        elif field == "transfers":
            raw["transfers"] = [{} for _ in range(10000)]
        else:
            raw["outputs"]["energy"]["segments"] = [{} for _ in range(10000)]
        return raw

    monkeypatch.setattr(m.mission, "evaluate_solved_dc_electrothermal", forged)
    assert_atomic(m.evaluate_ledger_solved_dc_electrothermal(request))
    assert len(calls["ledger"]) == len(calls["mission"]) == 1
