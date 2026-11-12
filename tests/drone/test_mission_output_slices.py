from copy import deepcopy

import pytest

from . import test_solved_dc_electrothermal as mt
from . import test_solved_dc_power as pt

m = mt.m


def forbid_models(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Slice validation called an evaluator")
    monkeypatch.setattr(m.dp, "evaluate_solved_dc_power", forbidden)
    monkeypatch.setattr(m.th, "screen_thermal", forbidden)


def replace(value, path, replacement):
    parts = [int(key) if key.isdigit() else key for key in path.split(".")]
    for key in parts[:-1]:
        value = value[key]
    value[parts[-1]] = replacement


@pytest.fixture
def point():
    request = pt.bridge_request.__wrapped__()
    raw = m.dp.evaluate_solved_dc_power(request)
    assert raw["status"] == "COMPUTED_EXPERIMENTAL"
    return request, raw


@pytest.fixture
def heat():
    request = {"evaluation": "lumped_thermal_screening", "mass_kg": 2,
               "specific_heat_j_kg_k": 1000, "initial_temperature_k": 300,
               "lumped_biot_number": .05, "property_source": "Synthetic",
               "segments": [{"duration_s": 10, "ambient_temperature_k": 290,
                             "heat_input_w": 34.55, "conductance_w_k": 2}]}
    raw = m.th.screen_thermal(request)
    assert raw["status"] == "SCREENING_COMPUTED"
    return request, raw


def test_actual_point_equality_and_isolation(point, monkeypatch):
    request, raw = point
    saved = deepcopy(point)
    forbid_models(monkeypatch)
    rows, selected = m._point_output_values(raw["outputs"], raw["output_units"], request)
    assert rows == raw["outputs"]["power"]["motors"]
    assert selected == raw["outputs"]["solve"]["selected_candidate"]
    assert m._validated_point(raw, request) == raw
    rows[0]["motor"]["current_a"] = 999
    selected["angular_speeds_rad_s"][0] = 999
    assert point == saved


@pytest.mark.parametrize("path,value", [
    ("outputs.power.motors.0.angular_speed_rad_s", 999),
    ("outputs.power.motors.0.shaft_torque_nm", 999),
    ("outputs.power.motors.0.motor.current_a", True),
    ("output_units.power.motors.0.motor.current_a", "wrong"),
    ("outputs.power.motors.0.allocated_heat_w", 999),
    ("outputs.power.total_electrical_power_w", 999),
])
def test_point_slice_rejects_actual_value_forgeries(point, monkeypatch, path, value):
    request, raw = deepcopy(point)
    replace(raw, path, value)
    forbid_models(monkeypatch)
    with pytest.raises(ValueError):
        m._point_output_values(raw["outputs"], raw["output_units"], request)


@pytest.mark.parametrize("zero", [False, True])
def test_actual_heat_equality_zero_and_isolation(heat, monkeypatch, zero):
    request, raw = heat
    if zero:
        request["segments"][0].update(heat_input_w=0, conductance_w_k=0)
        raw = m.th.screen_thermal(request)
    saved = deepcopy((request, raw))
    forbid_models(monkeypatch)
    out = m._heat_output_values(raw["outputs"], raw["output_units"], request)
    assert out == raw["outputs"] and m._validated_heat(raw, request) == raw
    if zero:
        assert out["total_heat_input_j"] == 0 and out["final_temperature_k"] == 300
    out["segments"][0]["end_temperature_k"] = 999
    assert (request, raw) == saved


@pytest.mark.parametrize("defect", ["final", "index", "units", "mass", "conductance"])
def test_heat_slice_rejects_actual_forgeries(heat, monkeypatch, defect):
    request, raw = deepcopy(heat)
    if defect in ("mass", "conductance"):
        altered = deepcopy(request)
        replace(altered, "mass_kg" if defect == "mass" else "segments.0.conductance_w_k", 4)
        raw = m.th.screen_thermal(altered)
        assert m._validated_heat(raw, altered) == raw
    else:
        path, value = {"final": ("outputs.final_temperature_k", 999),
                       "index": ("outputs.segments.0.index", False),
                       "units": ("output_units.segments.heat_input_j", "wrong")}[defect]
        replace(raw, path, value)
    forbid_models(monkeypatch)
    with pytest.raises(ValueError):
        m._heat_output_values(raw["outputs"], raw["output_units"], request)
