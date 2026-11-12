import math
from copy import deepcopy

import pytest

from physimesh.drone import solved_dc_electrothermal as m
from physimesh.drone.provenance import sha256_record

from . import test_solved_dc_power as point_tests


@pytest.fixture
def point_request():
    return point_tests.bridge_request.__wrapped__()


@pytest.fixture
def mission_request(point_request):
    point_request["auxiliary"].update(power_w=20, heat_fraction=.5)
    return {
        "evaluation": m.EVALUATION, "usable_energy_j": 100000, "reserve_fraction": .1,
        "thermal_body": {"mass_kg": 2, "specific_heat_j_kg_k": 1000,
                         "initial_temperature_k": 300, "lumped_biot_number": .05,
                         "property_source": "Synthetic"},
        "segments": [{"id": name, "duration_s": duration, "point": deepcopy(point_request),
                      "thermal": {"ambient_temperature_k": 290, "conductance_w_k": conductance}}
                     for name, duration, conductance in (("first", 10, 2), ("second", 20, 4))],
    }


@pytest.fixture
def observed(monkeypatch, mission_request):
    calls = {key: [] for key in ("point", "solve", "motor", "thermal")}

    def spy(key, original):
        def wrapped(payload):
            saved = deepcopy(payload)
            raw = original(payload)
            calls[key].append((saved, raw))
            return raw
        return wrapped

    for key, owner, name in (("point", m.dp, "evaluate_solved_dc_power"),
                             ("solve", m.dp.sp.ws, "evaluate_static_wrench_solve"),
                             ("motor", m.dp.dc, "evaluate_dc_motor"),
                             ("thermal", m.th, "screen_thermal")):
        monkeypatch.setattr(owner, name, spy(key, getattr(owner, name)))
    return mission_request, calls


def test_actual_energy_heat_chronology_provenance_and_isolation(observed):
    request, calls = observed
    before = deepcopy(request)
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert request == before
    assert {key: len(value) for key, value in calls.items()} == {
        "point": 2, "solve": 2, "motor": 4, "thermal": 1}
    out, units = result["outputs"], result["output_units"]
    assert out["mission_state"] == "COMPUTED_FROM_RESIDUAL_MET_SEGMENTS"
    thermalreq, thermalraw = calls["thermal"][0]
    energies, heats = [], []
    for i, (segment, (pointreq, raw)) in enumerate(zip(request["segments"], calls["point"], strict=True)):
        power, duration = raw["outputs"]["power"], segment["duration_s"]
        p, h = power["total_electrical_power_w"], power["total_allocated_heat_w"]
        energies.append(p * duration)
        heats.append(h * duration)
        assert 0 < h < p
        assert power["auxiliary_electrical_power_w"] == 20 and power["auxiliary_heat_w"] == 10
        assert power["total_unallocated_motor_loss_w"] > 0
        assert out["power_segments"][i] == {"segment_id": segment["id"], "duration_s": duration,
                                           **raw["outputs"]}
        assert units["power_segments"][i] == {"segment_id": "not_applicable", "duration_s": "s",
                                             **raw["output_units"]}
        assert thermalreq["segments"][i] == {"duration_s": duration, "ambient_temperature_k": 290,
                                             "heat_input_w": h, "conductance_w_k": (2, 4)[i]}
        assert out["energy"]["segments"][i]["cumulative_energy_j"] == math.fsum(energies)
        assert result["transfers"][i] == {"segment_id": segment["id"], "electrical_power_w": p,
                                          "heat_input_w": h, "source": "validated_dc_power_loss_allocation"}
        assert result["stages"][i] == {"stage_id": f"point_{i}",
                                       "request_sha256": sha256_record(pointreq),
                                       "result_sha256": sha256_record(raw), "stages": raw["stages"]}
    energy = out["energy"]
    assert energy["total_energy_j"] == math.fsum(energies)
    assert energy["total_energy_wh"] == energy["total_energy_j"] / 3600
    assert (energy["mission_budget_j"], energy["held_reserve_j"]) == (90000, 10000)
    assert energy["remaining_budget_j"] == 90000 - math.fsum(energies)
    assert energy["elapsed_s"] == out["thermal"]["elapsed_s"] == 30
    assert out["thermal"] == thermalraw["outputs"] and units["thermal"] == thermalraw["output_units"]
    assert out["thermal"]["total_heat_input_j"] == math.fsum(heats)
    first, second = out["thermal"]["segments"]
    assert first["start_temperature_k"] == 300
    assert second["start_temperature_k"] == first["end_temperature_k"]
    assert (first["cumulative_elapsed_s"], second["cumulative_elapsed_s"]) == (10, 30)
    assert result["request_sha256"] == sha256_record(before)
    assert result["stages"][-1] == {"stage_id": "thermal", "request_sha256": sha256_record(thermalreq),
                                    "result_sha256": sha256_record(thermalraw)}
    saved = deepcopy(result)
    request["segments"][0]["point"]["auxiliary"]["power_w"] = 999
    calls["point"][0][1]["outputs"]["power"]["motors"][0]["motor"]["current_a"] = 999
    thermalraw["outputs"]["segments"][0]["end_temperature_k"] = 999
    assert result == saved
    out["power_segments"][1]["power"]["motors"][0]["motor"]["current_a"] = 999
    assert calls["point"][1][1]["outputs"]["power"]["motors"][0]["motor"]["current_a"] != 999


def test_actual_unmet_stops_with_reached_prefix(observed):
    request, calls = observed
    request["segments"].append({**deepcopy(request["segments"][1]), "id": "third"})
    request["segments"][1]["point"]["solve"].update(
        max_evaluations=2, required_net_force_body_n=[1e9, 0, 0])
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert {key: len(value) for key, value in calls.items()} == {
        "point": 2, "solve": 2, "motor": 2, "thermal": 0}
    out, units = result["outputs"], result["output_units"]
    assert out["mission_state"] == "STOPPED_AT_UNMET_SEGMENT" and result["transfers"] == []
    assert [row["segment_id"] for row in out["power_segments"]] == ["first", "second"]
    assert out["power_segments"][-1]["solve"] == calls["point"][-1][1]["outputs"]["solve"]
    assert out["power_segments"][-1]["power"] is units["power_segments"][-1]["power"] is None
    assert out["energy"] is out["thermal"] is units["energy"] is units["thermal"] is None
    assert len(result["stages"]) == 2


def test_invalid_last_segment_preflights_entire_schedule(observed):
    request, calls = observed
    request["segments"].append({**deepcopy(request["segments"][1]), "id": "third"})
    request["segments"][-1]["thermal"]["ambient_temperature_k"] = True
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "GRAPH_INVALID" and "request_sha256" not in result
    assert all(not records for records in calls.values())
    assert result["stages"] == result["transfers"] == []
    assert result["outputs"] == result["output_units"] == {}


@pytest.mark.parametrize("ideal", (True, False))
def test_zero_conductance_equilibrium_or_positive_heating(observed, ideal):
    request, calls = observed
    for segment in request["segments"]:
        segment["thermal"]["conductance_w_k"] = 0
        if ideal:
            segment["point"]["auxiliary"].update(power_w=0, heat_fraction=0)
            for motor in segment["point"]["motors"]:
                motor["parameters"].update(terminal_resistance_ohm=0, zero_torque_current_a=0)
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL" and len(calls["thermal"]) == 1
    out = result["outputs"]
    if ideal:
        assert all(row["power"]["total_allocated_heat_w"] == 0 for row in out["power_segments"])
        assert out["thermal"]["final_temperature_k"] == 300
    else:
        assert out["thermal"]["final_temperature_k"] == pytest.approx(
            300 + out["thermal"]["total_heat_input_j"] / 2000)
        assert out["thermal"]["final_temperature_k"] > 300


def test_negative_budget_is_a_screen_not_feasibility(observed):
    request, _ = observed
    request.update(usable_energy_j=1, reserve_fraction=.25)
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["energy"]["remaining_budget_j"] < 0
    assert result["outputs"]["energy"]["budget_status"] == "EXCEEDS_DECLARED_ENERGY"
    assert result["feasibility"] is result["aircraft_status"] is None
    assert result["evidence_level"] == "unverified"
    assert all(result[key] == "NOT_ESTABLISHED" for key in (
        "physical_validation", "numerical_qualification", "runtime_identity"))


def test_excessive_mission_depth_rejected_before_models(observed):
    request, calls = observed
    nested = 0
    for _ in range(13):
        nested = [nested]
    request["segments"][-1]["thermal"]["conductance_w_k"] = nested
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "GRAPH_INVALID" and "request_sha256" not in result
    assert all(not records for records in calls.values())
    assert result["stages"] == result["transfers"] == []
    assert result["outputs"] == result["output_units"] == {}


def test_cyclic_mission_rejected_before_models(observed):
    request, calls = observed
    request["segments"][-1]["point"]["solve"]["assembly_template"]["graph"]["nodes"].append(request)
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "GRAPH_INVALID" and "request_sha256" not in result
    assert all(not records for records in calls.values())
    assert result["stages"] == result["transfers"] == []
    assert result["outputs"] == result["output_units"] == {}


@pytest.mark.parametrize("path,value", [
    ("reserve_fraction", True), ("reserve_fraction", 1), ("reserve_fraction", -1),
    ("reserve_fraction", 5e-324), ("usable_energy_j", 0), ("usable_energy_j", float("inf")),
    ("thermal_body.mass_kg", True), ("thermal_body.mass_kg", 0),
    ("thermal_body.specific_heat_j_kg_k", float("nan")),
    ("thermal_body.lumped_biot_number", .11), ("thermal_body.property_source", " "),
    ("segments.1.duration_s", 0), ("segments.1.duration_s", True),
    ("segments.1.duration_s", 5e-324),
    ("segments.1.thermal.conductance_w_k", -1),
    ("segments.1.thermal.conductance_w_k", True),
    ("segments.1.thermal.ambient_temperature_k", 0),
    ("segments.1.thermal.heat_input_w", 1),
    ("segments.1.point.motors.0.heat_fraction_of_motor_loss", True),
    ("segments.1.point.auxiliary.power_w", -1), ("extra", 0),
])
def test_invalid_preflight_values_never_call_models(observed, path, value):
    request, calls = observed
    parts = [int(part) if part.isdigit() else part for part in path.split(".")]
    parent = request
    for part in parts[:-1]:
        parent = parent[part]
    parent[parts[-1]] = value
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "GRAPH_INVALID" and result["diagnostics_complete"] is False
    assert "request_sha256" not in result and all(not records for records in calls.values())
    assert result["stages"] == result["transfers"] == []
    assert result["outputs"] == result["output_units"] == {}


@pytest.mark.parametrize("variant", ("empty", "seventeen", "duplicate", "global_work", "elapsed_loss"))
def test_invalid_schedule_structure_and_budgets_never_call_models(observed, variant):
    request, calls = observed
    if variant == "empty":
        request["segments"] = []
    elif variant == "seventeen":
        request["segments"] = [{**deepcopy(request["segments"][0]), "id": f"segment_{i}"}
                               for i in range(17)]
    elif variant == "duplicate":
        request["segments"][1]["id"] = request["segments"][0]["id"]
    elif variant == "global_work":
        work = 0
        for segment in request["segments"]:
            point = segment["point"]
            point["solve"]["max_evaluations"] = 64
            for node in point["solve"]["assembly_template"]["graph"]["nodes"]:
                if node["model"] == "isolated_hover_bemt_experimental":
                    node["inputs"]["annuli"] = 128
                    work += 128 * 65
            m.dp._preflight(deepcopy(point))
        assert work > 32768
    else:
        request["segments"][0]["duration_s"] = 1e100
        request["segments"][1]["duration_s"] = 1
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "GRAPH_INVALID" and result["diagnostics_complete"] is False
    assert "request_sha256" not in result and all(not records for records in calls.values())
    assert result["stages"] == result["transfers"] == []
    assert result["outputs"] == result["output_units"] == {}


@pytest.mark.parametrize("target_index", (0, 1))
@pytest.mark.parametrize("defect", (
    "raise", "hash", "qualifier", "diagnostics", "motorcurrent", "motorvalue",
    "rowomega", "torque", "heat", "unallocated", "totalP", "totalH", "units",
    "motorrequesthash", "nestedrequesthash", "transfersauxheat", "transferfraction",
))
def test_actual_point_forgery_fails_atomically(observed, monkeypatch, target_index, defect):
    request, calls = observed
    request["segments"].append({**deepcopy(request["segments"][1]), "id": "third"})
    original = m.dp.evaluate_solved_dc_power
    attempts = []
    private = "PRIVATE point runtime failure detail"

    def corrupt(payload):
        index = len(attempts)
        attempts.append(deepcopy(payload))
        raw = deepcopy(original(payload))
        if index != target_index:
            return raw
        if defect == "raise":
            raise RuntimeError(private)
        power = raw["outputs"]["power"]
        row = power["motors"][0]
        if defect == "hash":
            raw["request_sha256"] = "0" * 64
        elif defect == "qualifier":
            raw["physical_validation"] = "ESTABLISHED"
        elif defect == "diagnostics":
            raw["diagnostics_complete"] = 1
        elif defect == "motorcurrent":
            row["motor"]["current_a"] = True
        elif defect == "motorvalue":
            row["motor"]["current_a"] += 1
        elif defect == "rowomega":
            row["angular_speed_rad_s"] += 1
        elif defect == "torque":
            row["shaft_torque_nm"] *= 1.1
        elif defect == "heat":
            row["allocated_heat_w"] += 1
        elif defect == "unallocated":
            row["unallocated_loss_w"] += 1
        elif defect == "totalP":
            power["total_electrical_power_w"] += 1
        elif defect == "totalH":
            power["total_allocated_heat_w"] += 1
        elif defect == "units":
            raw["output_units"]["power"]["motors"][0]["motor"]["current_a"] = "W"
        elif defect == "motorrequesthash":
            raw["stages"][1]["request_sha256"] = "0" * 64
        elif defect == "nestedrequesthash":
            raw["stages"][0]["stages"][0]["request_sha256"] = "0" * 64
        elif defect == "transfersauxheat":
            raw["transfers"]["auxiliary"]["heat_w"] += 1
        elif defect == "transferfraction":
            raw["transfers"]["motors"][0]["heat_fraction_of_motor_loss"] = True
        return raw

    monkeypatch.setattr(m.dp, "evaluate_solved_dc_power", corrupt)
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "EXECUTION_FAILED" and result["diagnostics_complete"] is False
    assert result["request_sha256"] == sha256_record(request)
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert private not in repr(result)
    assert len(attempts) == len(calls["point"]) == len(calls["solve"]) == target_index + 1
    assert len(calls["motor"]) == 2 * (target_index + 1) and calls["thermal"] == []
    assert all(raw["status"] == "COMPUTED_EXPERIMENTAL" for _, raw in calls["point"])


def test_point_system_exit_propagates(observed, monkeypatch):
    request, calls = observed
    original = m.dp.evaluate_solved_dc_power
    attempts = []

    def interrupt(payload):
        attempts.append(deepcopy(payload))
        original(payload)
        raise SystemExit("point interrupted")

    monkeypatch.setattr(m.dp, "evaluate_solved_dc_power", interrupt)
    with pytest.raises(SystemExit, match="point interrupted"):
        m.evaluate_solved_dc_electrothermal(request)
    assert len(attempts) == len(calls["point"]) == len(calls["solve"]) == 1
    assert len(calls["motor"]) == 2 and calls["thermal"] == []


@pytest.mark.parametrize("defect", (
    "raise", "status", "evidence", "feasibility", "heatinput", "finaltemperature",
    "boolindex", "booltemperature", "units", "coherent_mass", "coherent_conductance",
))
def test_actual_thermal_forgery_fails_atomically(observed, monkeypatch, defect):
    request, calls = observed
    original = m.th.screen_thermal
    attempts = []
    coherent_accepted = []
    private = "PRIVATE thermal runtime failure detail"

    def corrupt(payload):
        attempts.append(deepcopy(payload))
        altered = deepcopy(payload)
        if defect == "coherent_mass":
            altered["mass_kg"] *= 2
        elif defect == "coherent_conductance":
            altered["segments"][0]["conductance_w_k"] *= 2
        raw = deepcopy(original(altered))
        assert raw["status"] == "SCREENING_COMPUTED"
        if defect.startswith("coherent_"):
            m.em._validated_thermal(raw, payload)
            coherent_accepted.append(True)
        if defect == "raise":
            raise RuntimeError(private)
        if defect == "status":
            raw["status"] = "MODEL_INAPPLICABLE"
        elif defect == "evidence":
            raw["evidence_level"] = "verified"
        elif defect == "feasibility":
            raw["feasibility"] = True
        elif defect == "heatinput":
            raw["outputs"]["segments"][0]["heat_input_j"] += 1
        elif defect == "finaltemperature":
            raw["outputs"]["final_temperature_k"] += 1
        elif defect == "boolindex":
            raw["outputs"]["segments"][0]["index"] = False
        elif defect == "booltemperature":
            raw["outputs"]["segments"][0]["end_temperature_k"] = True
        elif defect == "units":
            raw["output_units"]["final_temperature_k"] = "degC"
        return raw

    monkeypatch.setattr(m.th, "screen_thermal", corrupt)
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "EXECUTION_FAILED" and result["diagnostics_complete"] is False
    assert result["request_sha256"] == sha256_record(request)
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == [] and private not in repr(result)
    assert len(calls["point"]) == len(calls["solve"]) == 2 and len(calls["motor"]) == 4
    assert len(attempts) == len(calls["thermal"]) == 1
    assert coherent_accepted == ([True] if defect.startswith("coherent_") else [])


def test_thermal_keyboard_interrupt_propagates(observed, monkeypatch):
    request, calls = observed
    original = m.th.screen_thermal
    attempts = []

    def interrupt(payload):
        attempts.append(deepcopy(payload))
        original(payload)
        raise KeyboardInterrupt("thermal interrupted")

    monkeypatch.setattr(m.th, "screen_thermal", interrupt)
    with pytest.raises(KeyboardInterrupt, match="thermal interrupted"):
        m.evaluate_solved_dc_electrothermal(request)
    assert len(calls["point"]) == len(calls["solve"]) == 2 and len(calls["motor"]) == 4
    assert len(attempts) == len(calls["thermal"]) == 1


@pytest.mark.parametrize("defect,status,point_count,thermal_count", (
    ("energy_overflow", "EXECUTION_FAILED", 1, 0),
    ("temperature_resolution", "EXECUTION_FAILED", 2, 1),
    ("reserve_resolution", "GRAPH_INVALID", 0, 0),
))
def test_actual_unsupported_arithmetic_is_rejected(observed, defect, status, point_count, thermal_count):
    request, calls = observed
    if defect == "energy_overflow":
        request["segments"] = request["segments"][:1]
        request["segments"][0]["duration_s"] = 1e308
    elif defect == "temperature_resolution":
        request["thermal_body"].update(mass_kg=1, specific_heat_j_kg_k=1e300)
    else:
        request["reserve_fraction"] = 1e-200
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == status and result["diagnostics_complete"] is False
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert len(calls["point"]) == len(calls["solve"]) == point_count
    assert len(calls["motor"]) == 2 * point_count and len(calls["thermal"]) == thermal_count
    if status == "GRAPH_INVALID":
        assert "request_sha256" not in result
    else:
        assert result["request_sha256"] == sha256_record(request)


def test_zero_reserve_and_full_declared_heat_capture(observed):
    request, calls = observed
    request["reserve_fraction"] = 0
    for segment in request["segments"]:
        segment["point"]["auxiliary"]["heat_fraction"] = 1
        for motor in segment["point"]["motors"]:
            motor["heat_fraction_of_motor_loss"] = 1
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    energy = result["outputs"]["energy"]
    assert energy["held_reserve_j"] == 0
    assert energy["mission_budget_j"] == request["usable_energy_j"]
    for index, row in enumerate(result["outputs"]["power_segments"]):
        power = row["power"]
        assert power["total_unallocated_motor_loss_w"] == 0
        assert power["total_allocated_motor_heat_w"] == power["total_motor_loss_w"]
        assert power["auxiliary_heat_w"] == power["auxiliary_electrical_power_w"] == 20
        assert power["total_allocated_heat_w"] == power["total_motor_loss_w"] + 20
        assert calls["thermal"][0][0]["segments"][index]["heat_input_w"] == power["total_allocated_heat_w"]
        assert power["total_electrical_power_w"] == power["total_motor_electrical_power_w"] + 20
    assert len(calls["point"]) == 2 and len(calls["thermal"]) == 1


def test_first_segment_unmet_retains_only_first_point(observed):
    request, calls = observed
    request["segments"][0]["point"]["solve"].update(
        max_evaluations=2, required_net_force_body_n=[1e9, 0, 0])
    result = m.evaluate_solved_dc_electrothermal(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(calls["point"]) == len(calls["solve"]) == 1
    assert calls["motor"] == calls["thermal"] == []
    out, units = result["outputs"], result["output_units"]
    assert out["mission_state"] == "STOPPED_AT_UNMET_SEGMENT"
    assert len(out["power_segments"]) == len(units["power_segments"]) == len(result["stages"]) == 1
    assert out["power_segments"][0]["segment_id"] == "first"
    assert out["power_segments"][0]["solve"] == calls["point"][0][1]["outputs"]["solve"]
    assert out["power_segments"][0]["power"] is units["power_segments"][0]["power"] is None
    assert out["energy"] is out["thermal"] is units["energy"] is units["thermal"] is None
    assert result["transfers"] == []
