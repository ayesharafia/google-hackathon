from copy import deepcopy

import numpy as np
import pytest

from physimesh.drone import wrench_sensitivity as m
from physimesh.drone.provenance import sha256_record

from .test_rotor_assembly import request as assembly_request


def request():
    assembly = assembly_request()
    return {
        "evaluation": m.EVALUATION,
        "assembly": assembly,
        "perturbations": [
            {
                "node": rotor["node"],
                "half_step_rad_s": 1.0,
                "speed_scale_rad_s": 300.0,
            } for rotor in assembly["rotors"]
        ],
        "force_scale_n": 100.0,
        "moment_scale_nm": 100.0,
        "relative_singular_value_cutoff": 1e-8,
    }


def test_actual_probe_hashes(monkeypatch):
    body = request()
    saved = deepcopy(body)
    actual = m.ra.evaluate_rotor_assembly
    calls = []

    def spy(reqdict):
        actual_request = deepcopy(reqdict)
        raw = actual(reqdict)
        calls.append((actual_request, deepcopy(raw)))
        return raw

    monkeypatch.setattr(m.ra, "evaluate_rotor_assembly", spy)
    result = m.evaluate_wrench_sensitivity(body)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert body == saved
    assert result["request_sha256"] == sha256_record(saved)
    stages = result["stages"]
    assert len(stages) == len(calls) == 13
    assert stages[0]["stage_id"] == "nominal"
    assert stages[-1]["stage_id"] == "level_2_rotor_r2_minus"
    assert result["outputs"]["nominal_assembly"] == calls[0][1]["outputs"]
    assert result["outputs"]["evaluations_used"] == 13
    for stage, (actual_request, actual_raw) in zip(stages, calls):
        assert stage["request_sha256"] == sha256_record(actual_request)
        assert stage["result_sha256"] == sha256_record(actual_raw)
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["numerical_qualification"] == "NOT_ESTABLISHED"
    assert result["runtime_identity"] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None


def test_actual_central_derivatives(monkeypatch):
    calls = []
    actual = m.ra.evaluate_rotor_assembly

    def spy(reqdict):
        raw = actual(reqdict)
        calls.append(deepcopy(raw))
        return raw

    def wrench(raw):
        assert raw["status"] == "COMPUTED_EXPERIMENTAL"
        outputs = raw["outputs"]
        return np.concatenate((outputs["net_force_body_n"],
                               outputs["net_moment_cg_body_nm"]))

    monkeypatch.setattr(m.ra, "evaluate_rotor_assembly", spy)
    result = m.evaluate_wrench_sensitivity(request())
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    outputs = result["outputs"]
    assert outputs["evaluations_used"] == len(calls) == 13
    assert len(outputs["levels"]) == 3
    assert len(outputs["changes"]) == 2
    assert all(raw["status"] == "COMPUTED_EXPERIMENTAL" for raw in calls)
    actual_levels = []
    for k, level in enumerate(outputs["levels"]):
        h = 1 / 2**k
        assert level["half_steps_rad_s"] == pytest.approx([h, h])
        jac = np.column_stack([
            (wrench(calls[1 + 4*k + 2*j]) -
             wrench(calls[2 + 4*k + 2*j])) / (2*h)
            for j in range(2)])
        actual_levels.append(jac)
        dim = jac * 300 / 100
        np.testing.assert_allclose(level["force_jacobian_n_per_rad_s"], jac[:3])
        np.testing.assert_allclose(level["moment_jacobian_nm_per_rad_s"], jac[3:])
        np.testing.assert_allclose(level["dimensionless_jacobian"], dim)
        singular = np.linalg.svd(dim, compute_uv=False)
        np.testing.assert_allclose(level["singular_values"], singular)
        cutoff = 1e-8 * singular[0]
        assert level["rank_cutoff"] == pytest.approx(cutoff)
        assert level["numerical_rank"] == np.count_nonzero(singular > cutoff)
    for k, change in enumerate(outputs["changes"]):
        delta = actual_levels[k + 1] - actual_levels[k]
        for name, values in (("force", delta[:3]), ("moment", delta[3:]),
                             ("dimensionless", delta * 300 / 100)):
            reported = [v for key, v in change.items()
                        if name in key and "max_abs" in key]
            assert reported == pytest.approx([float(np.max(np.abs(values)))])


@pytest.mark.parametrize("defect", [
    "order", "hzero", "hboolean", "hcollision", "hnegativeomega",
    "scalebool", "cutoffone", "annuli", "extra",
])
def test_invalid_zero_models(monkeypatch, defect):
    body = request()
    if defect == "order":
        body["perturbations"].reverse()
    elif defect in {"hzero", "hboolean", "hcollision", "hnegativeomega"}:
        body["perturbations"][0]["half_step_rad_s"] = {
            "hzero": 0, "hboolean": True,
            "hcollision": 1e-20, "hnegativeomega": 301,
        }[defect]
    elif defect == "scalebool":
        body["force_scale_n"] = True
    elif defect == "cutoffone":
        body["relative_singular_value_cutoff"] = 1
    elif defect == "annuli":
        for node in body["assembly"]["graph"]["nodes"]:
            if "hover" in node["model"]:
                node["inputs"]["annuli"] = 513
    else:
        body["unexpected"] = 1
    before = deepcopy(body)
    calls = []
    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Invalid input must fail before model evaluation")
    monkeypatch.setattr(m.ra, "evaluate_rotor_assembly", forbidden)
    result = m.evaluate_wrench_sensitivity(body)
    assert calls == []
    assert body == before
    assert result["status"] == "GRAPH_INVALID"
    assert "request_sha256" not in result
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == []


@pytest.mark.parametrize("fault", ["private", "units", "request_hash", "netforce", "later"])
def test_atomic(monkeypatch, fault):
    body = request()
    expected_hash = sha256_record(body)
    original = m.ra.evaluate_rotor_assembly
    calls = 0

    def wrapped(actual):
        nonlocal calls
        calls += 1
        if fault == "private":
            raise RuntimeError("PRIVATE_SENSITIVITY")
        raw = deepcopy(original(actual))
        if fault == "later" and calls == 5:
            raise RuntimeError("PRIVATE_SENSITIVITY")
        if fault == "units":
            raw["output_units"]["net_force_body_n"] = "wrong"
        elif fault == "request_hash":
            raw["request_sha256"] = "0" * 64
        elif fault == "netforce":
            raw["outputs"]["net_force_body_n"][0] += 1
        return raw

    monkeypatch.setattr(m.ra, "evaluate_rotor_assembly", wrapped)
    result = m.evaluate_wrench_sensitivity(body)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == expected_hash
    assert result["stages"] == []
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["diagnostics_complete"] is False
    assert "PRIVATE_SENSITIVITY" not in repr(result)
    assert calls == (5 if fault == "later" else 1)


def test_zero_derivative_allowed():
    body = request()
    raw = {
        "outputs": {
            "net_force_body_n": [0., 0., 0.],
            "net_moment_cg_body_nm": [0., 0., 0.],
        }
    }
    pairs = [(deepcopy(raw), deepcopy(raw)) for _ in range(2)]
    level = m._level(body, pairs, [1., 1.])
    np.testing.assert_array_equal(
        level["dimensionless_jacobian"], np.zeros((6, 2))
    )
    np.testing.assert_array_equal(level["singular_values"], [0., 0.])
    assert level["numerical_rank"] == 0
    assert level["rank_cutoff"] == 0.
    changes = m._changes([level, deepcopy(level), deepcopy(level)])
    assert len(changes) == 2
    for change in changes:
        deltas = [
            value for key, value in change.items()
            if "delta" in key or "change" in key
        ]
        assert deltas
        assert all(np.all(np.asarray(delta) == 0.) for delta in deltas)


def test_aggregate_probe_budget(monkeypatch):
    body = request()
    graph = body["assembly"]["graph"]
    hover = next(
        node for node in graph["nodes"]
        if node["model"] == "isolated_hover_bemt_experimental"
    )
    for node_id in ("r3", "r4"):
        node = deepcopy(hover)
        node["id"] = node_id
        graph["nodes"].append(node)
        graph["connections"].append({
            "from_node": "air", "from_port": "density_kg_m3",
            "to_node": node_id, "to_port": "density_kg_m3",
        })
        graph["targets"].extend(
            {"node": node_id, "port": port}
            for port in ("thrust_n", "shaft_torque_nm")
        )
        rotor = deepcopy(body["assembly"]["rotors"][0])
        rotor["node"] = node_id
        body["assembly"]["rotors"].append(rotor)
        perturbation = deepcopy(body["perturbations"][0])
        perturbation["node"] = node_id
        body["perturbations"].append(perturbation)
    rotors = [node for node in graph["nodes"] if node["model"] == hover["model"]]
    assert len(rotors) == 4
    calls = []
    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("preflight must reject before model evaluation")
    monkeypatch.setattr(m.ra, "evaluate_rotor_assembly", forbidden)
    for node in rotors:
        node["inputs"]["annuli"] = 327
    m._preflight(body)
    for node in rotors:
        node["inputs"]["annuli"] = 328
    result = m.evaluate_wrench_sensitivity(body)
    assert result["status"] == "GRAPH_INVALID"
    assert "request_sha256" not in result
    assert calls == []


def test_actual_local_rank_reduction():
    body = request()
    for rotor in body["assembly"]["rotors"]:
        rotor.update(center_body_m=[0, 0, 0], axis_body=[0, 0, 1], rotation_sign=1)
    result = m.evaluate_wrench_sensitivity(body)
    assert result["outputs"]["evaluations_used"] == 13
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["levels"]
    for level in result["outputs"]["levels"]:
        assert level["numerical_rank"] == 1
        assert level["rank_cutoff"] > 0
        assert level["singular_values"][1] <= level["rank_cutoff"]
        for key in ("force_jacobian_n_per_rad_s", "moment_jacobian_nm_per_rad_s"):
            assert [row[0] for row in level[key]] == pytest.approx([row[1] for row in level[key]])
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None
