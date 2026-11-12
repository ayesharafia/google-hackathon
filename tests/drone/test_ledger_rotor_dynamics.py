from copy import deepcopy

import pytest

from physimesh.drone import ledger_rotor_dynamics as m
from physimesh.drone.provenance import sha256_record

from .test_mass_ledger_request import request as ledger_request
from .test_rotor_fixed_load_dynamics import request as dynamics_request


def request():
    b = dynamics_request()
    a = b["assembly"]
    del a["mass_kg"]
    del a["cg_body_m"]
    return {
        "evaluation": m.EVALUATION,
        "ledger": ledger_request(),
        "assembly_template": a,
        "initial_state": b["initial_state"],
        "dt_s": 0.01,
        "steps": 10,
        "applicability_declaration": "Common body frame, synthetic fixed snapshot",
    }


def test_real_composition():
    body = request()
    original = deepcopy(body)
    result = m.evaluate_ledger_rotor_dynamics(body)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert body == original
    lr = m.ml.evaluate_mass_ledger(body["ledger"])
    assert result["outputs"]["ledger"] == lr["outputs"]
    canonical = m._dynamics_input(body, lr["outputs"])
    dr = m.fd.evaluate_rotor_fixed_load_dynamics(canonical)
    assert result["outputs"]["frozen_dynamics"] == dr["outputs"]
    transfer = result["transfers"]
    assert transfer["mass_kg"] == 4
    assert transfer["cg_body_m"] == [0, 0, 0]
    assert transfer["inertia_body_kg_m2"] == [[2, 0, 0], [0, 6, 0], [0, 0, 6]]
    assert result["request_sha256"] == sha256_record(body)
    stages = result["stages"]
    assert len(stages) == 2
    for stage, direct in zip(stages, (lr, dr)):
        assert stage["request_sha256"] == direct["request_sha256"]
        assert stage["result_sha256"] == sha256_record(direct)


@pytest.mark.parametrize("defect", [
    "rootinertia", "templatemass", "templatecg",
    "initialquat", "steps", "missingowninertia",
])
def test_preflight(monkeypatch, defect):
    body = request()
    calls = []
    if defect == "rootinertia":
        body["inertia_body_kg_m2"] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    elif defect == "templatemass":
        body["assembly_template"]["mass_kg"] = 4
    elif defect == "templatecg":
        body["assembly_template"]["cg_body_m"] = [0, 0, 0]
    elif defect == "initialquat":
        body["initial_state"]["quaternion_body_to_enu"] = [0, 1, 0, 0]
    elif defect == "steps":
        body["steps"] = 1001
    else:
        del body["ledger"]["items"][0]["inertia_own_cg_body_kgm2"]

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        raise RuntimeError("unexpected execution")

    monkeypatch.setattr(m.ml, "evaluate_mass_ledger", spy)
    monkeypatch.setattr(m.fd, "evaluate_rotor_fixed_load_dynamics", spy)
    response = m.evaluate_ledger_rotor_dynamics(body)
    assert response["status"] == "GRAPH_INVALID"
    assert "request_sha256" not in response
    assert response["outputs"] == response["output_units"] == {}
    assert calls == []


@pytest.mark.parametrize("defect", ["badowninertia", "singular"])
def test_admitted_failures(defect):
    body = request()
    if defect == "badowninertia":
        body["ledger"]["items"][0]["inertia_own_cg_body_kgm2"][0][0] = -1
    else:
        for item in body["ledger"]["items"]:
            item["inertia_own_cg_body_kgm2"] = [[0, 0, 0] for _ in range(3)]
            item["cg_body_m"] = [0, 0, 0]
    expected_hash = sha256_record(body)
    response = m.evaluate_ledger_rotor_dynamics(body)
    assert response["status"] == "EXECUTION_FAILED"
    assert response["request_sha256"] == expected_hash
    assert response["diagnostics_complete"] is False
    assert response["stages"] == []
    assert response["transfers"] == response["outputs"] == response["output_units"] == {}


@pytest.mark.parametrize("fault", [
    "ledger_units", "ledger_hash", "dynamics_units",
    "dynamics_quaternion", "dynamics_stage", "late_exception",
])
def test_downstream_faults_fail_closed(monkeypatch, fault):
    body = request()
    before = deepcopy(body)
    expected_hash = sha256_record(body)
    target = m.ml if fault.startswith("ledger_") else m.fd
    attribute = (
        "evaluate_mass_ledger" if target is m.ml
        else "evaluate_rotor_fixed_load_dynamics"
    )
    real = getattr(target, attribute)

    def wrapped(body):
        result = real(body)
        if fault == "ledger_units":
            result["output_units"]["cg_body_m"] = "cm"
        elif fault == "ledger_hash":
            result["request_sha256"] = "0" * 64
        elif fault == "dynamics_units":
            result["output_units"]["dynamics"]["elapsed_s"] = "ms"
        elif fault == "dynamics_quaternion":
            result["outputs"]["dynamics"]["final_state"]["quaternion_body_to_enu"] = [2, 0, 0, 0]
        elif fault == "dynamics_stage":
            result["stages"][1]["request_sha256"] = "0" * 64
        else:
            raise RuntimeError("PRIVATE_LATE_SENTINEL")
        return result

    monkeypatch.setattr(target, attribute, wrapped)
    result = m.evaluate_ledger_rotor_dynamics(body)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == expected_hash
    assert result["stages"] == []
    assert all(result[key] == {} for key in ("transfers", "outputs", "output_units"))
    assert result["diagnostics_complete"] is False
    assert "PRIVATE_LATE_SENTINEL" not in repr(result)
    assert body == before
