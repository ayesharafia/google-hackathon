from copy import deepcopy
from unittest.mock import Mock

import pytest

from physimesh.drone import mass
from physimesh.drone import mass_ledger_request as m
from physimesh.drone.provenance import sha256_record


def request():
    items = [
        {"name": c, "category": c, "mass_kg": 2 if i < 2 else 0,
             "cg_body_m": [1 if i == 0 else -1 if i == 1 else 0, 0, 0],
             "inertia_own_cg_body_kgm2": [[int(i < 2 and r == s)
                                      for s in range(3)] for r in range(3)]}
        for i, c in enumerate(mass.CATEGORIES)
    ]
    return {"evaluation": "frozen_mass_ledger_experimental", "items": items,
                "property_source": "Declared fixed component properties; unverified."}


def metadata(result):
    assert result["evaluation"] == m.EVALUATION == request()["evaluation"]
    assert result["evidence_level"] == "unverified"
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[key] == "NOT_ESTABLISHED"
    for key in ("feasibility", "aircraft_status"):
        assert key in result and result[key] is None
    assert result["limitations"]


def test_real_composition(monkeypatch):
    value = request()
    before = deepcopy(value)
    items = [mass.MassItem(**{**i, "cg_body_m": tuple(i["cg_body_m"]),
             "inertia_own_cg_body_kgm2": tuple(map(tuple, i["inertia_own_cg_body_kgm2"]))})
             for i in value["items"]]
    core = mass.summarize(items, need_inertia=True)
    spy = Mock(wraps=mass.summarize)
    monkeypatch.setattr(mass, "summarize", spy)
    result = m.evaluate_mass_ledger(value)
    spy.assert_called_once_with(items, need_inertia=True)
    metadata(result)
    assert value == before and result["request_sha256"] == sha256_record(before)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["diagnostics_complete"] is True and result["reasons"] == []
    assert result["outputs"] == {"total_mass_kg": core.total_mass_kg,
        "cg_body_m": core.cg_body_m.tolist(), "inertia_cg_body_kgm2": core.inertia_cg_body_kgm2.tolist(),
        "payload_kg": core.payload_kg, "by_category_kg": core.by_category}
    assert result["outputs"] == {"total_mass_kg": 4, "cg_body_m": [0, 0, 0],
        "inertia_cg_body_kgm2": [[2, 0, 0], [0, 6, 0], [0, 0, 6]], "payload_kg": 2,
        "by_category_kg": {c: 2 if c in ("payload", "structure") else 0 for c in mass.CATEGORIES}}
    assert result["output_units"] == {"total_mass_kg": "kg", "cg_body_m": "m",
        "inertia_cg_body_kgm2": "kg*m^2", "payload_kg": "kg",
        "by_category_kg": dict.fromkeys(mass.CATEGORIES, "kg")}


@pytest.mark.parametrize("defect", ["boolmass", "missingownI", "tuplecg", "missingcategory",
                                   "duplicate", "unknownfield", "nonfinite", "too_many", "blanksource"])
def test_preflight_refuses_without_core(monkeypatch, defect):
    value = request()
    item = value["items"][0]
    if defect == "boolmass": item["mass_kg"] = True
    elif defect == "missingownI": del value["items"][-1]["inertia_own_cg_body_kgm2"]
    elif defect == "tuplecg": item["cg_body_m"] = tuple(item["cg_body_m"])
    elif defect == "missingcategory": value["items"].pop()
    elif defect == "duplicate": value["items"][1]["name"] = item["name"]
    elif defect == "unknownfield": item["state"] = "fixed"
    elif defect == "nonfinite": item["mass_kg"] = float("inf")
    elif defect == "too_many": value["items"] = [
        dict(deepcopy(value["items"][i % 6]), name=str(i)) for i in range(129)]
    elif defect == "blanksource": value["property_source"] = " \t"
    spy = Mock(wraps=mass.summarize)
    monkeypatch.setattr(mass, "summarize", spy)
    result = m.evaluate_mass_ledger(value)
    spy.assert_not_called()
    assert result["status"] == "GRAPH_INVALID" and "request_sha256" not in result
    assert result["outputs"] == result["output_units"] == {}
    assert result["diagnostics_complete"] is False and result["reasons"]


@pytest.mark.parametrize("late", [False, True])
def test_execution_failure_is_atomic(monkeypatch, late):
    value, original = request(), mass.summarize
    if not late: value["items"][0]["inertia_own_cg_body_kgm2"][0][0] = -1
    def run(items, *, need_inertia):
        summary = original(items, need_inertia=need_inertia)
        if late: raise RuntimeError("PRIVATE_SENTINEL")
        return summary
    spy = Mock(side_effect=run)
    monkeypatch.setattr(mass, "summarize", spy)
    result = m.evaluate_mass_ledger(value)
    spy.assert_called_once()
    assert spy.call_args.kwargs == {"need_inertia": True}
    metadata(result)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == sha256_record(value)
    assert result["outputs"] == result["output_units"] == {}
    assert result["diagnostics_complete"] is False and result["reasons"]
    assert "PRIVATE_SENTINEL" not in repr(result)
