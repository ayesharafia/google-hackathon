import math
from copy import deepcopy

import pytest

from physimesh.drone import solved_wrench_power as m
from physimesh.drone.provenance import sha256_record

from .test_static_wrench_solve import request as solve_request


def request():
    return {
        "evaluation": m.EVALUATION,
        "solve": solve_request(),
        "conversion": {
            "rotors": [
                {"node": "r1", "conversion_efficiency": 0.8, "conversion_source": "Synthetic"},
                {"node": "r2", "conversion_efficiency": 0.5, "conversion_source": "Synthetic"},
            ],
            "auxiliary_power_w": 11,
            "auxiliary_source": "Synthetic",
        },
    }


def test_selected_solution_drives_power_graph(monkeypatch):
    calls = {"solve": [], "power_graph": []}

    def spy(stage, evaluate):
        def wrapped(actual_request):
            raw = evaluate(actual_request)
            calls[stage].append((deepcopy(actual_request), deepcopy(raw)))
            return raw
        return wrapped

    monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", spy("solve", m.ws.evaluate_static_wrench_solve))
    monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", spy("power_graph", m.rg.evaluate_reference_air_graph))
    req = request()
    original = deepcopy(req)
    result = m.evaluate_solved_wrench_power(req)
    assert req == original
    assert all(len(records) == 1 for records in calls.values())
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    out = result["outputs"]
    chosen = out["solve"]["selected_candidate"]["angular_speeds_rad_s"]
    assert any(omega != 240 for omega in chosen)
    graph_request, graph_raw = calls["power_graph"][0]
    nodes = {node["id"]: node for node in graph_request["nodes"]}
    graph_outputs = graph_raw["outputs"]
    rows = out["power"]["rotors"]
    for i, row in enumerate(rows):
        node = row["node"]
        omega = chosen[i]
        assert nodes[node]["inputs"]["angular_speed_rad_s"] == row["angular_speed_rad_s"] == omega
        assert row["shaft_power_w"] == graph_outputs[node]["shaft_power_w"]
        assert row["shaft_power_w"] == pytest.approx(row["shaft_torque_nm"] * omega)
        assert math.isfinite(row["electrical_power_w"])
        assert row["electrical_power_w"] == pytest.approx(row["shaft_power_w"] / {"r1": 0.8, "r2": 0.5}[node])
    assert out["power"]["total_electrical_power_w"] == pytest.approx(sum(row["electrical_power_w"] for row in rows) + 11)
    assert out["power_state"] == "COMPUTED_AT_RESIDUAL_MET_POINT"
    assert result["feasibility"] is None
    stages = {stage["stage_id"]: stage for stage in result["stages"]}
    assert set(stages) == {"solve", "power_graph"}
    for stage_id, [(actual_request, raw)] in calls.items():
        assert stages[stage_id]["request_sha256"] == sha256_record(actual_request)
        assert stages[stage_id]["result_sha256"] == sha256_record(raw)


def _forbid_evaluation(*args, **kwargs):
    pytest.fail("unexpected evaluator call")


@pytest.fixture
def power_request():
    return deepcopy(request())


def test_unmet_actual_solve_skips_power(monkeypatch, power_request):
    power_request["solve"].update(
        max_evaluations=2, required_net_force_body_n=[1e9, 0, 0]
    )
    monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", _forbid_evaluation)
    result = m.evaluate_solved_wrench_power(power_request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["power"] is None
    assert result["outputs"]["power_state"] == "NOT_RUN_RESIDUAL_UNMET"
    assert result["transfers"] == {}
    assert len(result["stages"]) == 1


@pytest.mark.parametrize(
    "edit", ["eta0", "etaTrue", "auxnegative", "sourceblank", "rootextra",
             "orderreversed", "work"]
)
def test_invalid_request_never_evaluates(monkeypatch, power_request, edit):
    conversion = power_request["conversion"]
    if edit in ("eta0", "etaTrue"):
        conversion["rotors"][0]["conversion_efficiency"] = 0 if edit == "eta0" else True
    elif edit == "auxnegative":
        conversion["auxiliary_power_w"] = -1
    elif edit == "sourceblank":
        conversion["auxiliary_source"] = " "
    elif edit == "rootextra":
        power_request["extra"] = 1
    elif edit == "orderreversed":
        conversion["rotors"].reverse()
    else:
        power_request["solve"]["max_evaluations"] = 64
        for node in power_request["solve"]["assembly_template"]["graph"]["nodes"]:
            if node["model"] == "isolated_hover_bemt_experimental":
                node["inputs"]["annuli"] = 256
    monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", _forbid_evaluation)
    monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", _forbid_evaluation)
    result = m.evaluate_solved_wrench_power(power_request)
    assert result["status"] == "GRAPH_INVALID"
    assert not result.get("request_sha256")
    assert result["outputs"] == {}


@pytest.mark.parametrize("tamper", ["units", "power", "gravity", "boolean", "raise"])
def test_late_graph_failure_is_sanitized(monkeypatch, power_request, tamper):
    original_hash = sha256_record(power_request)
    real = m.rg.evaluate_reference_air_graph

    def wrapped(*args, **kwargs):
        graph = deepcopy(real(*args, **kwargs))
        if tamper == "raise":
            raise ValueError("private runtime detail")
        if tamper == "units":
            graph["output_units"]["r1"]["shaft_power_w"] = "kg"
        elif tamper == "power":
            graph["outputs"]["r1"]["shaft_power_w"] *= 1.1
        elif tamper == "boolean":
            graph["outputs"]["r1"]["shaft_power_w"] = True
        else:
            air = graph["outputs"]["air"]
            key = next(k for k in air if "gravity" in k or k == "g_m_s2")
            air[key] *= 1.1
        return graph

    monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", wrapped)
    result = m.evaluate_solved_wrench_power(power_request)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == original_hash
    assert result["outputs"] == result["transfers"] == result["output_units"] == {}
    assert result["stages"] == []
    assert "private runtime detail" not in str(result["reasons"])
def test_asymmetric_selected_power():
    req = request()
    spec = req["solve"]
    spec["absolute_force_tolerance_n"] = 1e-9
    spec["absolute_moment_tolerance_nm"] = 1e-9
    spec["max_evaluations"] = 64
    target = m.ws.ra.evaluate_rotor_assembly(m.ws._assembly_input(spec, [300., 330.]))["outputs"]
    spec["required_net_force_body_n"] = deepcopy(target["net_force_body_n"])
    spec["required_net_moment_cg_body_nm"] = deepcopy(target["net_moment_cg_body_nm"])
    result = m.evaluate_solved_wrench_power(req)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    out = result["outputs"]
    assert out["solve"]["outcome"] == "RESIDUAL_MET"
    selected = out["solve"]["selected_candidate"]["angular_speeds_rad_s"]
    assert selected == pytest.approx([300., 330.], rel=0, abs=1e-5)
    rows = out["power"]["rotors"]
    assert [r["angular_speed_rad_s"] for r in rows] == selected
    for row in rows:
        assert row["shaft_power_w"] == pytest.approx(row["shaft_torque_nm"] * row["angular_speed_rad_s"])

def test_zero_auxiliary_unit_efficiency():
    req = request()
    req["conversion"]["auxiliary_power_w"] = 0
    for rotor in req["conversion"]["rotors"]:
        rotor["conversion_efficiency"] = 1
    result = m.evaluate_solved_wrench_power(req)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    power = result["outputs"]["power"]
    for row in power["rotors"]:
        assert row["electrical_power_w"] == pytest.approx(row["shaft_power_w"])
    assert power["total_electrical_power_w"] == pytest.approx(math.fsum(r["electrical_power_w"] for r in power["rotors"]))

@pytest.mark.parametrize("tamper", ["status", "outcome", "units", "stage_hash"])
def test_solver_tamper_blocks_power(monkeypatch, tamper):
    req = request()
    real = m.ws.evaluate_static_wrench_solve
    def wrapped(spec):
        raw = real(spec)
        assert raw["status"] == "COMPUTED_EXPERIMENTAL"
        assert raw["outputs"]["outcome"] == "RESIDUAL_MET"
        if tamper == "status": raw["status"] = "WRONG"
        elif tamper == "outcome": raw["outputs"]["outcome"] = "SOLVER_STOPPED"
        elif tamper == "units": raw["output_units"]["assembly"]["net_force_body_n"] = "kg"
        else: raw["stages"][0]["request_sha256"] = "0" * 64
        return raw
    def forbidden(*args, **kwargs):
        pytest.fail("power graph must not run")
    monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", wrapped)
    monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", forbidden)
    result = m.evaluate_solved_wrench_power(req)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == sha256_record(req)
    assert result["outputs"] == result["transfers"] == result["output_units"] == {}
    assert result["stages"] == []

def test_returned_power_has_no_caller_alias():
    req = request()
    original = deepcopy(req)
    result = m.evaluate_solved_wrench_power(req)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    expected = deepcopy(result["outputs"]["power"])
    result["outputs"]["power"]["rotors"][0]["shaft_power_w"] = -1
    again = m.evaluate_solved_wrench_power(req)
    assert again["status"] == "COMPUTED_EXPERIMENTAL"
    assert again["outputs"]["power"] == expected and req == original



def test_work_boundary_preflight(monkeypatch, power_request):
    monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", _forbid_evaluation)
    monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", _forbid_evaluation)
    valid = power_request
    rotors = [
        node
        for node in valid["solve"]["assembly_template"]["graph"]["nodes"]
        if node["model"] == "isolated_hover_bemt_experimental"
    ]
    assert len(rotors) == 2
    for node in rotors:
        node["inputs"]["annuli"] = 256
    aggregate = sum(node["inputs"]["annuli"] for node in rotors)
    assert aggregate == 512
    valid["solve"]["max_evaluations"] = 63
    assert aggregate * (valid["solve"]["max_evaluations"] + 1) == 32768
    assert m._preflight(valid) == valid

    overflow = deepcopy(valid)
    overflow["solve"]["max_evaluations"] = 64
    assert aggregate * (overflow["solve"]["max_evaluations"] + 1) > 32768
    assert m.ws._preflight(overflow["solve"]) == overflow["solve"]
    with pytest.raises(ValueError):
        m._preflight(overflow)


@pytest.mark.parametrize(
    "defect",
    [
        "none",
        "list",
        "string",
        "rootextra",
        "rootdepth",
        "container257",
        "string2001",
        "dict_subclass",
    ],
)
def test_deeply_invalid_request_never_evaluates(monkeypatch, power_request, defect):
    class NoDeepcopy(dict):
        def __deepcopy__(self, memo):
            raise AssertionError("Invalid JSON must be rejected before deepcopy")

    req = power_request
    if defect == "none":
        req = None
    elif defect == "list":
        req = []
    elif defect == "string":
        req = "invalid"
    elif defect == "rootextra":
        req["extra"] = 1
    elif defect == "rootdepth":
        nested = NoDeepcopy()
        for _ in range(11):
            nested = {"nested": nested}
        req["extra"] = nested
    elif defect == "container257":
        req["conversion"]["auxiliary_source"] = [None] * 257
    elif defect == "string2001":
        req["conversion"]["auxiliary_source"] = "x" * 2001
    else:
        req = NoDeepcopy(req)

    monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", _forbid_evaluation)
    monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", _forbid_evaluation)
    monkeypatch.setattr(m, "sha256_record", _forbid_evaluation)
    if defect == "rootdepth":
        with pytest.raises(ValueError, match="JSON depth"):
            m._preflight(req)
    else:
        with pytest.raises(ValueError):
            m._preflight(req)
    result = m.evaluate_solved_wrench_power(req)
    assert result["status"] == "GRAPH_INVALID"
    assert not result.get("request_sha256")
    assert result["outputs"] == result["transfers"] == result["output_units"] == {}
    assert result["stages"] == []


@pytest.mark.parametrize("port", ["thrust_n", "shaft_torque_nm"])
def test_graph_wrench_tamper_fails_atomically(monkeypatch, power_request, port):
    original_hash = sha256_record(power_request)
    real = m.rg.evaluate_reference_air_graph
    calls = []

    def wrapped(*args, **kwargs):
        raw = real(*args, **kwargs)
        assert raw["status"] == "COMPUTED_EXPERIMENTAL"
        graph = deepcopy(raw)
        graph["outputs"]["r1"][port] *= 1.1
        assert {
            key: value for key, value in graph.items() if key != "outputs"
        } == {
            key: value for key, value in raw.items() if key != "outputs"
        }
        calls.append(port)
        return graph

    monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", wrapped)
    result = m.evaluate_solved_wrench_power(power_request)
    assert calls == [port]
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == original_hash
    assert result["outputs"] == result["transfers"] == result["output_units"] == {}
    assert result["stages"] == []


@pytest.mark.parametrize("defect", ["eta_nan", "eta_subnormal", "aux_bool"])
def test_invalid_conversion_numbers_never_evaluate(
    monkeypatch, power_request, defect
):
    conversion = power_request["conversion"]
    if defect == "aux_bool":
        conversion["auxiliary_power_w"] = True
    else:
        conversion["rotors"][0]["conversion_efficiency"] = (
            float("nan") if defect == "eta_nan" else 1e-320
        )
    monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", _forbid_evaluation)
    monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", _forbid_evaluation)
    monkeypatch.setattr(m, "sha256_record", _forbid_evaluation)
    result = m.evaluate_solved_wrench_power(power_request)
    assert result["status"] == "GRAPH_INVALID"
    assert not result.get("request_sha256")
    assert result["outputs"] == result["transfers"] == result["output_units"] == {}
    assert result["stages"] == []



@pytest.mark.parametrize("defect", ["smallaux", "hugeaux", "tinyeta"])
def test_unrepresentable_power_contribution_fails_atomically(defect):
    req = request()
    if defect == "tinyeta":
        req["conversion"]["rotors"][0]["conversion_efficiency"] = 1e-30
    else:
        req["conversion"]["auxiliary_power_w"] = (
            1e-20 if defect == "smallaux" else 1e30
        )
    original_hash = sha256_record(req)
    result = m.evaluate_solved_wrench_power(req)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == original_hash
    assert result["outputs"] == result["transfers"] == result["output_units"] == {}
    assert result["stages"] == []


def test_power_sum_boundaries():
    assert m._power_sum([0, 0]) == 0
    assert m._power_sum([1, 2]) == 3
    for values in ([1, 1e-20], [1e30, 1], [1e-20, 1]):
        with pytest.raises(ValueError):
            m._power_sum(values)



@pytest.mark.parametrize("boundary", ["solve", "power_graph"])
@pytest.mark.parametrize("errorclass", [RuntimeError, AssertionError, LookupError])
def test_evaluator_exceptions_fail_atomically(monkeypatch, boundary, errorclass):
    req = request()
    original = deepcopy(req)
    original_hash = sha256_record(req)
    calls = []

    def raising(*args, **kwargs):
        calls.append(boundary)
        raise errorclass("private marker must never escape")

    if boundary == "solve":
        monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", raising)
    else:
        monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", raising)

    actual = m.evaluate_solved_wrench_power(req)

    assert calls == [boundary]
    assert actual["status"] == "EXECUTION_FAILED"
    assert actual["request_sha256"] == original_hash
    assert actual["outputs"] == actual["transfers"] == actual["output_units"] == {}
    assert actual["stages"] == []
    assert actual["diagnostics_complete"] is False
    assert actual["reasons"] == ["Solved wrench power execution failed."]
    assert "private marker must never escape" not in repr(actual)
    assert req == original
    assert sha256_record(req) == original_hash


def test_returned_contract_attribute_error_fails_atomically(monkeypatch):
    req = request()
    original = deepcopy(req)
    original_hash = sha256_record(req)
    real_graph = m.rg.evaluate_reference_air_graph
    graph_calls = []
    validation_calls = []

    def graph_spy(*args, **kwargs):
        raw = real_graph(*args, **kwargs)
        graph_calls.append(raw)
        return raw

    def invalid_power(raw, *args, **kwargs):
        validation_calls.append(raw)
        raise AttributeError("private returned-contract marker")

    monkeypatch.setattr(m.rg, "evaluate_reference_air_graph", graph_spy)
    monkeypatch.setattr(m, "_validated_power", invalid_power)

    actual = m.evaluate_solved_wrench_power(req)

    assert len(graph_calls) == 1
    assert len(validation_calls) == 1
    assert validation_calls[0] is graph_calls[0]
    assert graph_calls[0]["status"] == "COMPUTED_EXPERIMENTAL"
    assert actual["status"] == "EXECUTION_FAILED"
    assert actual["request_sha256"] == original_hash
    assert actual["outputs"] == actual["transfers"] == actual["output_units"] == {}
    assert actual["stages"] == []
    assert actual["diagnostics_complete"] is False
    assert actual["reasons"] == ["Solved wrench power execution failed."]
    assert "private returned-contract marker" not in repr(actual)
    assert req == original
    assert sha256_record(req) == original_hash
