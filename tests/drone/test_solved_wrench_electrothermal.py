import math
from copy import deepcopy

import pytest

from physimesh.drone import solved_wrench_electrothermal as m
from physimesh.drone.provenance import sha256_record

from .test_solved_wrench_power import request as power_request


def request():
    p = power_request()
    return {
        "evaluation": m.EVALUATION,
        "usable_energy_j": 100000,
        "reserve_fraction": 0.1,
        "thermal_body": {
            "mass_kg": 2,
            "specific_heat_j_kg_k": 900,
            "initial_temperature_k": 300,
            "lumped_biot_number": 0.05,
            "property_source": "Synthetic",
        },
        "segments": [
            {
                "id": name,
                "duration_s": duration,
                "solve": deepcopy(p["solve"]),
                "conversion": deepcopy(p["conversion"]),
                "thermal": {
                    "ambient_temperature_k": ambient,
                    "conductance_w_k": conductance,
                    "heat_fraction_of_electrical_input": fraction,
                    "heat_source": "Synthetic",
                },
            }
            for name, duration, ambient, conductance, fraction in [
                ("first", 10, 290, 2, 0.2),
                ("second", 20, 295, 3, 0.4),
            ]
        ],
    }


def test_evaluate(monkeypatch: pytest.MonkeyPatch):
    power_calls, thermal_calls = [], []

    def spy(original, calls):
        def wrapped(payload):
            captured = deepcopy(payload)
            raw = original(payload)
            calls.append((captured, deepcopy(raw)))
            return raw
        return wrapped

    for module, name, calls in [
        (m.sp, "evaluate_solved_wrench_power", power_calls),
        (m.th, "screen_thermal", thermal_calls),
    ]:
        monkeypatch.setattr(module, name, spy(getattr(module, name), calls))
    payload = request()
    before = deepcopy(payload)
    result = m.evaluate_solved_wrench_electrothermal(payload)
    assert payload == before
    assert len(power_calls) == 2
    assert len(thermal_calls) == 1
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    outputs = result["outputs"]
    assert outputs["mission_state"] == "COMPUTED_FROM_RESIDUAL_MET_SEGMENTS"
    powers = [raw["outputs"]["power"] for _, raw in power_calls]
    for row, segment, power in zip(outputs["power_segments"], payload["segments"], powers, strict=True):
        assert (row["segment_id"], row["duration_s"], row["power"]) == (
            segment["id"], segment["duration_s"], power,
        )
    total = math.fsum(p["total_electrical_power_w"] * s["duration_s"] for p, s in zip(powers, payload["segments"], strict=True))
    assert outputs["energy"]["total_energy_j"] == total
    assert outputs["energy"]["mission_budget_j"] == 90000
    assert outputs["energy"]["held_reserve_j"] == 10000
    assert outputs["energy"]["remaining_budget_j"] == 90000 - total
    thermal_request, thermal_raw = thermal_calls[0]
    assert outputs["thermal"] == thermal_raw["outputs"]
    for segment, source, power in zip(thermal_request["segments"], payload["segments"], powers, strict=True):
        assert segment["heat_input_w"] == power["total_electrical_power_w"] * source["thermal"]["heat_fraction_of_electrical_input"]
    timeline = outputs["thermal"]["segments"]
    assert timeline[1]["start_temperature_k"] == timeline[0]["end_temperature_k"]
    provenance = result
    assert provenance["request_sha256"] == sha256_record(before)
    stages = provenance["stages"]
    assert [stage["stage_id"] for stage in stages] == ["power_0", "power_1", "thermal"]
    for stage, (captured, raw) in zip(stages, power_calls + thermal_calls, strict=True):
        assert stage["request_sha256"] == sha256_record(captured)
        assert stage["result_sha256"] == sha256_record(raw)
    assert result["feasibility"] is None
    assert result["aircraft_status"] is None
    assert result["evidence_level"] == "unverified"
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["numerical_qualification"] == "NOT_ESTABLISHED"
    assert result["runtime_identity"] == "NOT_ESTABLISHED"
def _forbid_evaluation(*args, **kwargs):
    pytest.fail("Unexpected model evaluation")


def _records(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _records(child)


@pytest.mark.parametrize("index", [0, 1])
def test_unmet_segment_stops_mission(monkeypatch, index):
    payload, calls = request(), []
    payload["segments"][index]["solve"].update(
        max_evaluations=2, required_net_force_body_n=[1e9, 0, 0]
    )
    original = m.sp.evaluate_solved_wrench_power

    def spy(value):
        calls.append(deepcopy(value))
        return original(value)

    monkeypatch.setattr(m.sp, "evaluate_solved_wrench_power", spy)
    monkeypatch.setattr(m.th, "screen_thermal", _forbid_evaluation)
    result = m.evaluate_solved_wrench_electrothermal(payload)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["mission_state"] == "STOPPED_AT_UNMET_SEGMENT"
    assert len(calls) == len(result["outputs"]["power_segments"]) == index + 1
    assert result["outputs"]["power_segments"][-1]["power"] is None
    for key in ("energy", "thermal"):
        assert result["outputs"][key] is result["output_units"][key] is None
    assert len(result["stages"]) == index + 1
    assert result["transfers"] == []
    assert result["aircraft_status"] is result["feasibility"] is None


@pytest.mark.parametrize("path,value", [
    (("segments", 1, "conversion", "rotors", 0, "conversion_efficiency"), 0),
    (("segments", 1, "thermal", "ambient_temperature_k"), 0),
    (("segments", 1, "id"), "first"),
    (("reserve_fraction",), True),
    (("reserve_fraction",), 1),
    (("thermal_body", "mass_kg"), 0),
    (("thermal_body", "lumped_biot_number"), 0.2),
    (("segments", 1, "duration_s"), 0),
    (("unexpected",), 1),
])
def test_invalid_request_precedes_all_models(monkeypatch, path, value):
    payload = request()
    parent = payload
    for part in path[:-1]:
        parent = parent[part]
    parent[path[-1]] = value
    monkeypatch.setattr(m.sp, "evaluate_solved_wrench_power", _forbid_evaluation)
    monkeypatch.setattr(m.th, "screen_thermal", _forbid_evaluation)
    result = m.evaluate_solved_wrench_electrothermal(payload)
    assert result["status"] == "GRAPH_INVALID"
    assert "request_sha256" not in result
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []


def test_global_work_boundary():
    payload = request()
    for segment in payload["segments"]:
        segment["solve"]["max_evaluations"] = 63
        nodes = [row for row in _records(segment)
                 if {"id", "model", "inputs"} <= row.keys()
                 and isinstance(row["inputs"], dict) and "annuli" in row["inputs"]]
        assert len(nodes) == 2
        for node in nodes:
            node["inputs"]["annuli"] = 128
    m._preflight(payload)
    payload["segments"][1]["solve"]["max_evaluations"] = 64
    for segment in payload["segments"]:
        m.sp._preflight(m._power_request(segment))
    with pytest.raises(ValueError):
        m._preflight(payload)


@pytest.mark.parametrize("stage", ["power", "thermal"])
@pytest.mark.parametrize("error", [RuntimeError, AssertionError])
def test_execution_failure_discards_partial_results(monkeypatch, stage, error):
    payload, marker = request(), "PRIVATE_EXECUTION_MARKER"
    expected_hash = sha256_record(m._preflight(payload))

    def fail(value):
        raise error(marker)

    owner, name = ((m.sp, "evaluate_solved_wrench_power") if stage == "power"
                   else (m.th, "screen_thermal"))
    monkeypatch.setattr(owner, name, fail)
    result = m.evaluate_solved_wrench_electrothermal(payload)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == expected_hash
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert marker not in repr(result)


def test_exceeded_energy_budget_still_computes_thermal():
    payload = request()
    payload.update(usable_energy_j=100, reserve_fraction=0.1)
    result = m.evaluate_solved_wrench_electrothermal(payload)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    energy = result["outputs"]["energy"]
    assert energy["budget_status"] == "EXCEEDS_DECLARED_ENERGY"
    assert energy["mission_budget_j"] == 90
    assert energy["held_reserve_j"] == 10
    assert energy["remaining_budget_j"] == 90 - energy["total_energy_j"]
    assert energy["remaining_budget_j"] < 0
    assert result["outputs"]["thermal"] is not None
    assert result["output_units"]["thermal"] is not None
    assert result["stages"][-1]["stage_id"] == "thermal"
    assert result["aircraft_status"] is result["feasibility"] is None
def _mutate_power_raw(raw, case):
    solve, power = raw["outputs"]["solve"], raw["outputs"]["power"]
    if case == "status":
        raw["status"] = "BAD"
    elif case == "evidence":
        raw["evidence_level"] = "validated"
    elif case == "request_hash":
        raw["request_sha256"] = "0" * 64
    elif case == "extra_stage":
        raw["stages"].append(deepcopy(raw["stages"][0]))
    elif case == "stage_request_hash":
        raw["stages"][0]["request_sha256"] = "0" * 64
    elif case == "stage_result_hash":
        raw["stages"][0]["result_sha256"] = "bad"
    elif case in ("angular_speed_rad_s", "electrical_power_w", "shaft_torque_nm"):
        power["rotors"][0][case] *= 1.1
    elif case == "boolean_total":
        power["total_electrical_power_w"] = True
    elif case == "power_units":
        raw["output_units"]["power"]["wrong"] = "W"
    elif case == "candidate_boolean":
        assert solve["candidates"][0]["force_residual_n"][0] == 0
        solve["candidates"][0]["force_residual_n"][0] = False
    elif case == "selected_boolean":
        solve["selected_candidate"] = deepcopy(solve["selected_candidate"])
        solve["selected_candidate"]["force_residual_n"][0] = False
    elif case == "solve_outcome":
        solve["outcome"] = "SOLVER_STOPPED"
    elif case == "power_state":
        raw["outputs"]["power_state"] = "BAD"
    elif case == "transfer_speed":
        raw["transfers"]["angular_speeds_rad_s"][0] *= 1.1
    elif case == "extra_output":
        raw["outputs"]["unexpected"] = 1
    else:
        raise AssertionError(case)


def _mutate_thermal_raw(raw, case):
    if case == "segment_start":
        raw["outputs"]["segments"][1]["start_temperature_k"] += 1
    elif case == "final_temperature_units":
        raw["output_units"]["final_temperature_k"] = "C"
    else:
        raise AssertionError(case)


def _run_atomic_failure(monkeypatch, case, thermal=False):
    payload = deepcopy(request())
    actual_power = m.sp.evaluate_solved_wrench_power
    actual_thermal = m.th.screen_thermal
    calls = {"power": 0, "thermal": 0}
    mutated = []

    def power_spy(*args, **kwargs):
        calls["power"] += 1
        raw = deepcopy(actual_power(*args, **kwargs))
        if not thermal:
            _mutate_power_raw(raw, case)
            mutated.append(case)
        return raw

    def thermal_spy(*args, **kwargs):
        calls["thermal"] += 1
        raw = deepcopy(actual_thermal(*args, **kwargs))
        if thermal:
            _mutate_thermal_raw(raw, case)
            mutated.append(case)
        return raw

    with monkeypatch.context() as patch:
        patch.setattr(m.sp, "evaluate_solved_wrench_power", power_spy)
        patch.setattr(m.th, "screen_thermal", thermal_spy)
        result = m.evaluate_solved_wrench_electrothermal(payload)

    assert mutated == [case]
    assert calls == {
        "power": 2 if thermal else 1,
        "thermal": 1 if thermal else 0,
    }
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == sha256_record(payload)
    assert type(result["reasons"]) is list
    assert result["reasons"] == [
        "Solved wrench electrothermal execution failed."
    ]
    for key in ("outputs", "output_units", "stages", "transfers"):
        assert not result[key]
    return result


@pytest.mark.parametrize("case", [
    "status",
    "evidence",
    "request_hash",
    "extra_stage",
    "stage_request_hash",
    "stage_result_hash",
    "angular_speed_rad_s",
    "electrical_power_w",
    "boolean_total",
    "shaft_torque_nm",
    "power_units",
    "candidate_boolean",
    "selected_boolean",
    "solve_outcome",
    "power_state",
    "transfer_speed",
    "extra_output",
])
def test_power_raw_mutations_fail_atomically(monkeypatch, case):
    _run_atomic_failure(monkeypatch, case)


@pytest.mark.parametrize("case", [
    "segment_start",
    "final_temperature_units",
])
def test_thermal_raw_mutations_fail_atomically(monkeypatch, case):
    _run_atomic_failure(monkeypatch, case, thermal=True)
def test_direct_power_and_thermal_oracles():
    payload = request()
    powerresults = [m.sp.evaluate_solved_wrench_power(m._power_request(s))
                    for s in payload['segments']]
    thermalreq = {
        'evaluation': 'lumped_thermal_screening',
        **deepcopy(payload['thermal_body']),
        'segments': [{
            'duration_s': s['duration_s'],
            'ambient_temperature_k': s['thermal']['ambient_temperature_k'],
            'conductance_w_k': s['thermal']['conductance_w_k'],
            'heat_input_w': p['outputs']['power']['total_electrical_power_w']
                            * s['thermal']['heat_fraction_of_electrical_input'],
        } for s, p in zip(payload['segments'], powerresults, strict=True)],
    }
    directthermal = m.th.screen_thermal(thermalreq)
    result = m.evaluate_solved_wrench_electrothermal(payload)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert result['outputs']['mission_state'] == 'COMPUTED_FROM_RESIDUAL_MET_SEGMENTS'
    assert result['outputs']['thermal'] == directthermal['outputs']
    assert result['outputs']['energy']['total_energy_j'] == math.fsum(
        p['outputs']['power']['total_electrical_power_w'] * s['duration_s']
        for s, p in zip(payload['segments'], powerresults, strict=True))
    for transfer, oracle in zip(result['transfers'], thermalreq['segments'], strict=True):
        assert transfer['heat_input_w'] == oracle['heat_input_w']


def test_second_segment_atmosphere_is_solved_independently():
    # Declared segment atmospheres drive independent solves without mass feedback.
    payload = request()
    for node in payload['segments'][1]['solve']['assembly_template']['graph']['nodes']:
        if node['model'] == 'reference_air_properties':
            node['inputs']['altitude_m'] = 21000
    result = m.evaluate_solved_wrench_electrothermal(payload)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert result['outputs']['mission_state'] == 'COMPUTED_FROM_RESIDUAL_MET_SEGMENTS'
    first, second = result['outputs']['power_segments']
    assert first['solve']['selected_candidate']['angular_speeds_rad_s'] != second['solve']['selected_candidate']['angular_speeds_rad_s']
    assert first['power']['total_electrical_power_w'] != second['power']['total_electrical_power_w']


def test_segment_order_changes_thermal_history():
    payload = request()
    reversed_payload = deepcopy(payload)
    reversed_payload['segments'].reverse()
    forward = m.evaluate_solved_wrench_electrothermal(payload)
    backward = m.evaluate_solved_wrench_electrothermal(reversed_payload)
    for result in (forward, backward):
        assert result['status'] == 'COMPUTED_EXPERIMENTAL'
        assert result['outputs']['mission_state'] == 'COMPUTED_FROM_RESIDUAL_MET_SEGMENTS'
        timeline = result['outputs']['thermal']['segments']
        assert timeline[1]['start_temperature_k'] == timeline[0]['end_temperature_k']
    assert forward['outputs']['energy']['total_energy_j'] == backward['outputs']['energy']['total_energy_j']
    assert forward['outputs']['thermal']['final_temperature_k'] != backward['outputs']['thermal']['final_temperature_k']
@pytest.mark.parametrize("duration", [1e308, 1e-20, 1e30])
def test_energy_numeric_failure_is_atomic(monkeypatch, duration):
    payload, calls = request(), []
    payload["segments"][1]["duration_s"] = duration
    original = m.sp.evaluate_solved_wrench_power

    def spy(value):
        calls.append(deepcopy(value))
        return original(value)

    def forbid(value):
        pytest.fail("Thermal evaluation must not run after invalid energy arithmetic")

    monkeypatch.setattr(m.sp, "evaluate_solved_wrench_power", spy)
    monkeypatch.setattr(m.th, "screen_thermal", forbid)
    result = m.evaluate_solved_wrench_electrothermal(payload)
    assert len(calls) == 2
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["Solved wrench electrothermal execution failed."]
    assert result["request_sha256"] == sha256_record(payload)
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []


@pytest.mark.parametrize("fraction", [0, 1])
def test_heat_fraction_endpoints_without_double_energy_charge(fraction):
    payload = request()
    payload.update(reserve_fraction=0, usable_energy_j=100000)
    for segment in payload["segments"]:
        segment["thermal"].update(
            conductance_w_k=0, heat_fraction_of_electrical_input=fraction)
    result = m.evaluate_solved_wrench_electrothermal(payload)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    energy, thermal = result["outputs"]["energy"], result["outputs"]["thermal"]
    total = math.fsum(row["power"]["total_electrical_power_w"] * row["duration_s"] for row in result["outputs"]["power_segments"])
    assert energy["total_energy_j"] == total
    assert total == pytest.approx(4727, rel=1e-3)
    assert energy["held_reserve_j"] == 0
    assert energy["mission_budget_j"] == 100000
    assert energy["remaining_budget_j"] == 100000 - total
    assert thermal["total_heat_input_j"] == fraction * total
    assert thermal["final_temperature_k"] == (300 if fraction == 0 else pytest.approx(300 + total / 1800))


def test_keyboard_interrupt_propagates(monkeypatch):
    def interrupt(value):
        raise KeyboardInterrupt()
    monkeypatch.setattr(m.sp, "evaluate_solved_wrench_power", interrupt)
    with pytest.raises(KeyboardInterrupt):
        m.evaluate_solved_wrench_electrothermal(request())
def _assert_preflight_rejection(payload, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Preflight invoked a model or hash function")
    monkeypatch.setattr(m.sp, "evaluate_solved_wrench_power", forbidden)
    monkeypatch.setattr(m.th, "screen_thermal", forbidden)
    monkeypatch.setattr(m, "sha256_record", forbidden)
    result = m.evaluate_solved_wrench_electrothermal(payload)
    assert result["status"] == "GRAPH_INVALID"
    assert "request_sha256" not in result
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []


@pytest.mark.parametrize("edits", [
    [(("reserve_fraction",), True)],
    [(("reserve_fraction",), 1e-20)],
    [(("reserve_fraction",), float("nan"))],
    [(("thermal_body", "mass_kg"), 1e308),
     (("thermal_body", "specific_heat_j_kg_k"), 1e308)],
    [(("segments", 1, "thermal", "heat_fraction_of_electrical_input"), True)],
    [(("segments", 1, "duration_s"), True)],
])
def test_strict_preflight_numbers(monkeypatch, edits):
    payload = request()
    for path, value in edits:
        parent = payload
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = value
    _assert_preflight_rejection(payload, monkeypatch)


def test_preflight_segment_count_boundary():
    payload = request()
    first = deepcopy(payload["segments"][0])
    first["solve"]["max_evaluations"] = 2
    payload["segments"] = [
        dict(deepcopy(first), id=str(i)) for i in range(1, 17)
    ]
    assert m._preflight(payload) == payload
    payload["segments"].append(dict(deepcopy(first), id="17"))
    with pytest.raises(ValueError):
        m._preflight(payload)


@pytest.mark.parametrize("location", ["root", "thermal_body", "late"])
def test_exact_json_precedes_deepcopy(monkeypatch, location):
    class PoisonDict(dict):
        def __deepcopy__(self, memo):
            raise AssertionError("Non-JSON object reached deepcopy")
    payload = request()
    if location == "root":
        payload = PoisonDict(payload)
    elif location == "late":
        payload["segments"][-1] = PoisonDict(payload["segments"][-1])
    else:
        payload[location] = PoisonDict(payload[location])
    _assert_preflight_rejection(payload, monkeypatch)
