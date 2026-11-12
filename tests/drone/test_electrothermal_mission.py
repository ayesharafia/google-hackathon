from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from physimesh.drone import electrothermal_mission as em
from physimesh.drone.graph_mission import evaluate_graph_mission
from physimesh.drone.provenance import sha256_record
from physimesh.drone.thermal import screen_thermal

from .test_graph_mission import mission


def request():
    return {
        "evaluation": em.EVALUATION,
        "energy_mission": mission(),
        "thermal_body": {
            "mass_kg": 10,
            "specific_heat_j_kg_k": 500,
            "initial_temperature_k": 300,
            "lumped_biot_number": 0.01,
            "property_source": "Synthetic unverified body",
        },
        "thermal_segments": [
            {
                "id": n,
                "ambient_temperature_k": 280,
                "conductance_w_k": 10,
                "heat_fraction_of_electrical_input": 0.1,
                "heat_source": "Synthetic declared electrical heat fraction",
            }
            for n in ("loiter", "return")
        ],
    }


def test_actual_composition():
    supplied = request()
    original = deepcopy(supplied)
    actual = em.evaluate_electrothermal_mission(supplied)
    assert supplied == original
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    directenergy = evaluate_graph_mission(original["energy_mission"])
    assert actual["outputs"]["energy"] == directenergy["outputs"]
    source, transfers = em._thermal_request(original, directenergy)
    directthermal = screen_thermal(source)
    assert actual["outputs"]["thermal"] == directthermal["outputs"]
    segments = actual["outputs"]["thermal"]["segments"]
    assert segments[1]["start_temperature_k"] == segments[0]["end_temperature_k"]
    assert actual["output_units"] == {
        "energy": directenergy["output_units"],
        "thermal": directthermal["output_units"],
    }
    assert actual["request_sha256"] == sha256_record(original)
    assert actual["stages"] == [
        {
            "stage_id": "energy",
            "request_sha256": sha256_record(original["energy_mission"]),
            "result_sha256": sha256_record(directenergy),
        },
        {
            "stage_id": "thermal",
            "request_sha256": sha256_record(source),
            "result_sha256": sha256_record(directthermal),
        },
    ]
    assert actual["transfers"] == transfers
    assert all(
        result[key] == "NOT_ESTABLISHED"
        for result in (actual, directenergy)
        for key in ("physical_validation", "numerical_qualification", "runtime_identity")
    )
    assert all(result["feasibility"] is None for result in (actual, directenergy, directthermal))


def test_highprecision():
    b = request()
    a = em.evaluate_electrothermal_mission(b)
    with localcontext() as ctx:
        ctx.prec = 80
        temperature = Decimal(300)
        capacity = Decimal(5000)
        for transfer, spec, energysegment in zip(
            a["transfers"], b["thermal_segments"], b["energy_mission"]["segments"], strict=True
        ):
            q = Decimal.from_float(transfer["heat_input_w"])
            h = Decimal(spec["conductance_w_k"])
            dt = Decimal(energysegment["duration_s"])
            ambient = Decimal(spec["ambient_temperature_k"])
            equilibrium = ambient + q / h
            temperature = equilibrium + (temperature - equilibrium) * (-h * dt / capacity).exp()
    # Tolerance reflects scalar float rounding, not physical validity.
    assert a["outputs"]["thermal"]["final_temperature_k"] == pytest.approx(
        float(temperature), rel=3e-15, abs=0
    )


def test_zeroheat_equilibrium():
    b = request()
    b["thermal_body"]["initial_temperature_k"] = 280
    for spec in b["thermal_segments"]:
        spec["heat_fraction_of_electrical_input"] = 0
        spec["conductance_w_k"] = 0
    a = em.evaluate_electrothermal_mission(b)
    thermal = a["outputs"]["thermal"]
    assert a["status"] == "COMPUTED_EXPERIMENTAL"
    assert thermal["final_temperature_k"] == 280
    assert thermal["total_heat_input_j"] == 0
    assert all(s["start_temperature_k"] == s["end_temperature_k"] == 280 for s in thermal["segments"])
    assert all(t["heat_input_w"] == 0 for t in a["transfers"])


@pytest.mark.parametrize(
    "defect", ["id_order", "heat_bool", "heat_above_one", "negative_conductance", "invalid_biot"]
)
def test_invalid_thermal_preflight(monkeypatch, defect):
    b = deepcopy(request())
    thermal = b["thermal_segments"][-1]
    if defect == "id_order":
        thermal["id"] = "wrong"
    elif defect == "heat_bool":
        thermal["heat_fraction_of_electrical_input"] = True
    elif defect == "heat_above_one":
        thermal["heat_fraction_of_electrical_input"] = 1.1
    elif defect == "negative_conductance":
        thermal["conductance_w_k"] = -1
    else:
        b["thermal_body"]["lumped_biot_number"] = 0.2
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("Graph evaluation must not run")

    monkeypatch.setattr(em, "evaluate_graph_mission", forbidden)
    result = em.evaluate_electrothermal_mission(b)
    assert result["status"] == "GRAPH_INVALID"
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == calls == []


def test_thermal_failure(monkeypatch):
    def refuse(_):
        raise RuntimeError("PRIVATE")

    monkeypatch.setattr(em, "screen_thermal", refuse)
    result = em.evaluate_electrothermal_mission(request())
    assert result["status"] == "EXECUTION_FAILED"
    assert result["outputs"] == result["output_units"] == {}
    assert result["transfers"] == []
    assert len(result["stages"]) == 1
    assert result["diagnostics_complete"] is False
    assert "PRIVATE" not in str(result)
