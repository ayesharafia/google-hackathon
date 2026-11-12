"""Composition and boundary checks, not physical validation."""

from copy import deepcopy
from dataclasses import replace

import pytest

from physimesh.drone import model_graph_execution as graph
from physimesh.drone.fixed_wing import screen_fixed_wing
from physimesh.drone.hover_bemt_request import evaluate_hover_bemt
from physimesh.drone.provenance import sha256_record
from physimesh.drone.standard_atmosphere import standard_atmosphere


def hover():
    return {"evaluation": graph._HOVER, "radius_m": 0.5, "angular_speed_rad_s": 300.0,
                "density_kg_m3": 1.225, "blade_count": 2, "chord_m": 0.04,
                "lift_curve_slope_per_rad": 5.7, "profile_drag_coefficient": 0.01,
                "pitch_tip_rad": 0.12, "root_cutout_fraction": 0.2, "twist_law": "constant",
                "annuli": 8, "pitch_root_rad": None, "property_source": "Unverified supplier",
                "applicability_declaration": "Experimental isolated hover"}


def wing():
    return {"configuration": "fixed_wing", "evaluation": graph._WING,
                "density_kg_m3": 1.225, "airspeed_m_s": 50.0, "wing_area_m2": 10.0,
                "span_m": 10.0, "characteristic_length_m": 1.0, "dynamic_viscosity_pa_s": 1.8e-5,
                "speed_of_sound_m_s": 340.0, "lift_coefficient": 0.5,
                "zero_lift_drag_coefficient": 0.02, "span_efficiency": 0.8,
                "coefficient_source": "Synthetic unverified coefficients",
                "coefficient_envelope": {"mach_min": 0.0, "mach_max": 0.3, "reynolds_min": 1e5,
                                          "reynolds_max": 5e6, "lift_coefficient_min": -1.0,
                                          "lift_coefficient_max": 1.0}}


def node(name, model, inputs):
    return {"id": name, "model": model, "inputs": inputs}


def edge(a, ap, b, bp):
    return {"from_node": a, "from_port": ap, "to_node": b, "to_port": bp}


def target(name, port):
    return {"node": name, "port": port}


def request():
    h, w = hover(), wing()
    del h["density_kg_m3"], w["density_kg_m3"]
    return {"evaluation": graph.EVALUATION,
                "nodes": [node("a", graph._ATM, {"altitude_m": 1000, "altitude_kind": "geometric"}),
                       node("b", graph._ATM, {"altitude_m": 2000, "altitude_kind": "geopotential"}),
                       node("h", graph._HOVER, h), node("w", graph._WING, w),
                       node("unused", graph._HOVER, hover())],
                "connections": [edge("a", "density_kg_m3", "h", "density_kg_m3"),
                             edge("a", "density_kg_m3", "w", "density_kg_m3")],
                "targets": [target("h", "thrust_n"), target("w", "drag_n"), target("b", "pressure_pa")]}


def test_real_branch_multiple_atmospheres_closure_and_kernel_comparison(monkeypatch):
    calls = []
    original = graph.evaluate_hover_bemt

    def tracked(body):
        calls.append(deepcopy(body))
        return original(body)

    monkeypatch.setattr(graph, "evaluate_hover_bemt", tracked)
    body = request()
    result = graph.evaluate_model_graph(body)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["stage_order"] == ["a", "b", "h", "w"]
    assert len(calls) == 1
    atmosphere = standard_atmosphere(1000, altitude_kind="geometric")
    assert result["outputs"]["h"]["thrust_n"] == evaluate_hover_bemt(hover() | {"density_kg_m3": atmosphere.density_kg_m3})["outputs"]["thrust_n"]
    assert result["outputs"]["w"]["drag_n"] == screen_fixed_wing(wing() | {"density_kg_m3": atmosphere.density_kg_m3})["outputs"]["drag_n"]
    assert result["outputs"]["b"]["pressure_pa"] == standard_atmosphere(2000, altitude_kind="geopotential").pressure_pa
    assert result["output_units"] == {"h": {"thrust_n": "N"}, "w": {"drag_n": "N"}, "b": {"pressure_pa": "Pa"}}
    for transfer in result["transfers"]:
        producer = next(s for s in result["stages"] if s["node"] == transfer["from_node"])
        assert transfer["producer_result_sha256"] == producer["result_sha256"]
        assert transfer["value"] == producer["result"][transfer["from_port"]]
    assert result["evidence_level"] == "unverified"
    assert result["physical_validation"] == result["numerical_qualification"] == result["runtime_identity"] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is result["feasibility"] is None


def test_determinism_subset_and_data_hashes():
    body = request()
    before = deepcopy(body)
    first = graph.evaluate_model_graph(body)
    assert body == before
    assert first["request_sha256"] == sha256_record(before)
    body["nodes"].reverse()
    body["connections"].reverse()
    second = graph.evaluate_model_graph(body)
    for key in ("outputs", "output_units", "stage_order", "stages", "transfers"):
        assert first[key] == second[key]
    assert first["request_sha256"] != second["request_sha256"]  # admitted array order is data
    body["targets"] = [target("w", "lift_n")]
    subset = graph.evaluate_model_graph(body)
    assert subset["stage_order"] == ["a", "w"]
    assert set(subset["outputs"]) == {"w"} and set(subset["outputs"]["w"]) == {"lift_n"}
    for stage in first["stages"]:
        assert stage["inputs_sha256"] == sha256_record(stage["inputs"])
        assert stage["result_sha256"] == sha256_record(stage["result"])
    body["nodes"][0]["inputs"]["property_source"] = "Changed"
    assert first == graph.evaluate_model_graph(before)
    first["stages"][0]["result"]["density_kg_m3"] = -9
    assert graph.evaluate_model_graph(before)["outputs"] == second["outputs"]


def invalid_cases():
    cases = []

    def add(change):
        body = request()
        change(body)
        cases.append(body)

    add(lambda b: b.update(extra=1))
    add(lambda b: b["nodes"][0].update(model="caller.model"))
    add(lambda b: b["nodes"][0].update(id="bad-id"))
    add(lambda b: b["nodes"].append(deepcopy(b["nodes"][0])))
    add(lambda b: b["nodes"][4]["inputs"].pop("chord_m"))  # strict unused policy
    add(lambda b: b["nodes"][4]["inputs"].update(extra=1))
    add(lambda b: b["nodes"][2]["inputs"].update(density_kg_m3=1.2))
    add(lambda b: b["connections"].append(deepcopy(b["connections"][0])))
    for key, value in [("from_node", "missing"), ("from_port", "missing"),
                       ("from_port", "pressure_pa"), ("to_port", "missing"),
                       ("from_node", "h"), ("from_port", "thrust_n")]:
        add(lambda b, k=key, v=value: b["connections"][0].update({k: v}))
    add(lambda b: b["targets"].append(deepcopy(b["targets"][0])))
    add(lambda b: b["targets"][0].update(port="pitch_rad"))
    add(lambda b: b["targets"][0].update(node="missing"))
    add(lambda b: b["connections"].append(edge("h", "radial_fraction", "w", "lift_coefficient")))
    add(lambda b: b["connections"].append(edge("h", "annuli", "unused", "annuli")))
    for value in (True, float("nan"), float("inf"), 10**10000, "1", []):
        add(lambda b, v=value: b["nodes"][4]["inputs"].update(radius_m=v))
    for key, value in [("annuli", 2049), ("annuli", True), ("annuli", 8.0),
                       ("blade_count", 33), ("property_source", "x" * 2001)]:
        add(lambda b, k=key, v=value: b["nodes"][4]["inputs"].update({k: v}))
    deep = []
    for _ in range(11):
        deep = [deep]
    add(lambda b: b["nodes"][4]["inputs"].update(property_source=deep))
    add(lambda b: b["nodes"][4]["inputs"].update(property_source=[0] * 257))
    add(lambda b: b["nodes"][4]["inputs"].update(property_source=[[0] * 250 for _ in range(20)]))
    add(lambda b: b.update(nodes=b["nodes"] + [node(f"x{i}", graph._HOVER, hover()) for i in range(12)]))
    add(lambda b: b.update(connections=b["connections"] * 33))
    add(lambda b: b.update(targets=b["targets"] * 11))
    for key in ("nodes", "targets"):
        add(lambda b, k=key: b.update({k: []}))
    return cases


@pytest.mark.parametrize("body", invalid_cases())
def test_validation_failure_executes_nothing(body, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("adapter called before full graph validation")

    for name in ("standard_atmosphere", "evaluate_hover_bemt", "screen_fixed_wing"):
        monkeypatch.setattr(graph, name, forbidden)
    result = graph.evaluate_model_graph(body)
    assert result["status"] == "GRAPH_INVALID"
    assert result["stages"] == result["transfers"] == []
    assert result["outputs"] == result["output_units"] == {}


def test_global_cycle_and_annuli_budget(monkeypatch):
    bodies = []
    for selected in (True, False):
        body = request()
        for name in ("c", "d"):
            inputs = wing()
            del inputs["lift_coefficient"]
            body["nodes"].append(node(name, graph._WING, inputs))
        body["connections"] += [edge("c", "mach_number", "d", "lift_coefficient"),
                                edge("d", "mach_number", "c", "lift_coefficient")]
        if selected:
            body["targets"] = [target("c", "lift_n")]
        bodies.append(body)
    body = request()
    body["nodes"] += [node(f"x{i}", graph._HOVER, hover() | {"annuli": 2048}) for i in range(4)]
    bodies.append(body)
    for body in bodies:
        test_validation_failure_executes_nothing(body, monkeypatch)


@pytest.mark.parametrize("adapter", ["hover", "wing"])
@pytest.mark.parametrize("defect", ["unit", "nan", "model", "status", "extra", "refusal", "exception", "shape", "annuli"])
def test_fail_closed_after_prior_success(adapter, defect, monkeypatch):
    body = request()
    name = "h" if adapter == "hover" else "w"
    body["targets"] = [target(name, "thrust_n" if name == "h" else "drag_n"), target("a", "pressure_pa")]
    original = graph.evaluate_hover_bemt if name == "h" else graph.screen_fixed_wing

    def bad(inputs):
        if defect == "exception":
            raise RuntimeError("PRIVATE_SECRET_EXCEPTION")
        result = original(inputs)
        if defect == "unit":
            result["output_units"]["thrust_n" if name == "h" else "drag_n"] = "lbf"
        elif defect == "nan":
            result["outputs"]["thrust_n" if name == "h" else "drag_n"] = float("nan")
        elif defect == "model":
            result["model_id"] = "fake"
        elif defect == "status":
            result["status"] = "UNSUPPORTED_RESULT"
        elif defect == "extra":
            result["extra"] = True
        elif defect == "refusal":
            result.update(status="MODEL_INAPPLICABLE", reasons=["PRIVATE_SECRET_EXCEPTION"], outputs={}, output_units={})
        elif defect == "shape":
            if name == "h":
                result["outputs"]["radial_fraction"].pop()
            else:
                result["outputs"]["drag_n"] = [1]
        elif name == "h":
            result["outputs"]["annuli"] = 8.0
        else:
            result["source_metadata"]["urls"] = 1
        return result

    monkeypatch.setattr(graph, "evaluate_hover_bemt" if name == "h" else "screen_fixed_wing", bad)
    result = graph.evaluate_model_graph(body)
    assert result["status"] == "EXECUTION_FAILED" and result["failed_node"] == name
    assert result["stage_order"] == ["a"] and not result["diagnostics_complete"]
    assert result["outputs"] == result["output_units"] == {}
    assert "PRIVATE_SECRET_EXCEPTION" not in str(result)


@pytest.mark.parametrize("defect", ["type", "model", "evidence", "altitude", "kind", "nan", "bool"])
def test_atmosphere_boundary(defect, monkeypatch):
    original = standard_atmosphere

    def bad(**inputs):
        state = original(**inputs)
        changes = {"model": {"model_id": "fake"}, "evidence": {"evidence_status": "validated"},
                   "altitude": {"geopotential_altitude_m": -1}, "kind": {"altitude_kind": "other"},
                   "nan": {"density_kg_m3": float("nan")}, "bool": {"pressure_pa": True}}
        return {} if defect == "type" else replace(state, **changes[defect])

    monkeypatch.setattr(graph, "standard_atmosphere", bad)
    result = graph.evaluate_model_graph(request())
    assert result["status"] == "EXECUTION_FAILED"
    assert result["outputs"] == result["output_units"] == {} and result["stages"] == []


def test_actual_component_refusal_is_sanitized():
    body = request()
    body["nodes"][2]["inputs"]["radius_m"] = -1
    result = graph.evaluate_model_graph(body)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["stage_order"] == ["a", "b"]
    assert result["outputs"] == result["output_units"] == {}


def test_adapter_input_and_return_mutation_snapshots(monkeypatch):
    original = graph.screen_fixed_wing
    retained = []

    def mutate(inputs):
        result = original(inputs)
        inputs["coefficient_source"] = "adapter mutation"
        retained.append(result)
        return result

    monkeypatch.setattr(graph, "screen_fixed_wing", mutate)
    result = graph.evaluate_model_graph(request())
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    stage = next(s for s in result["stages"] if s["node"] == "w")
    assert stage["inputs"]["coefficient_source"] == wing()["coefficient_source"]
    retained[0]["outputs"]["drag_n"] = -1
    assert stage["result"]["outputs"]["drag_n"] == result["outputs"]["w"]["drag_n"]
    metadata = graph.adapter_metadata()
    metadata[graph._ATM]["inputs"]["altitude_m"]["unit"] = "ft"
    assert graph.adapter_metadata()[graph._ATM]["inputs"]["altitude_m"]["unit"] == "m"


def test_three_stage_chain_and_independent_density_branches():
    body = request()
    body["nodes"][1]["inputs"].pop("altitude_m")
    body["connections"] += [edge("a", "geopotential_altitude_m", "b", "altitude_m")]
    body["connections"][0]["from_node"] = "b"
    result = graph.evaluate_model_graph(body)
    assert result["stage_order"] == ["a", "b", "h", "w"]
    a = standard_atmosphere(1000, altitude_kind="geometric")
    b = standard_atmosphere(a.geopotential_altitude_m, altitude_kind="geopotential")
    assert result["outputs"]["h"]["thrust_n"] == evaluate_hover_bemt(hover() | {"density_kg_m3": b.density_kg_m3})["outputs"]["thrust_n"]
    assert result["outputs"]["w"]["drag_n"] == screen_fixed_wing(wing() | {"density_kg_m3": a.density_kg_m3})["outputs"]["drag_n"]
    assert {t["from_node"] for t in result["transfers"]} == {"a", "b"}


def test_annuli_upper_limits_admitted_and_selected_only(monkeypatch):
    body = {"evaluation": graph.EVALUATION,
                "nodes": [node(f"h{i}", graph._HOVER, hover() | {"annuli": 2048}) for i in range(4)],
                "connections": [], "targets": [target("h0", "shaft_power_w")]}
    original = graph.evaluate_hover_bemt
    calls = []

    def tracked(inputs):
        calls.append(inputs["annuli"])
        return original(inputs)

    monkeypatch.setattr(graph, "evaluate_hover_bemt", tracked)
    result = graph.evaluate_model_graph(body)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["stage_order"] == ["h0"] and calls == [2048]
    assert result["stages"][0]["result"]["outputs"]["annuli"] == 2048
    assert result["outputs"]["h0"]["shaft_power_w"] == original(hover() | {"annuli": 2048})["outputs"]["shaft_power_w"]


@pytest.mark.parametrize("field,value", [("unit", "kg/ft^3"), ("frame", "body")])
def test_caller_units_and_frames_are_not_accepted(field, value, monkeypatch):
    body = request()
    body["connections"][0][field] = value
    test_validation_failure_executes_nothing(body, monkeypatch)


def test_geometry_connections_remain_literal_only(monkeypatch):
    body = request()
    body["nodes"][2]["inputs"].pop("radius_m")
    body["connections"].append(edge("a", "geopotential_altitude_m", "h", "radius_m"))
    test_validation_failure_executes_nothing(body, monkeypatch)


@pytest.mark.parametrize("defect", ["hugeint", "bool", "deep", "size", "vector_bool", "annuli_count"])
def test_hover_result_resource_and_numeric_boundaries(defect, monkeypatch):
    original = graph.evaluate_hover_bemt

    def bad(inputs):
        result = original(inputs)
        if defect == "hugeint":
            result["outputs"]["thrust_n"] = 10**10000
        elif defect == "bool":
            result["outputs"]["thrust_n"] = True
        elif defect == "deep":
            nested = []
            for _ in range(11):
                nested = [nested]
            result["limitations"] = nested
        elif defect == "size":
            result["limitations"] = ["x"] * 2049
        elif defect == "vector_bool":
            result["outputs"]["radial_fraction"][0] = True
        else:
            result["outputs"]["annuli"] = inputs["annuli"] + 1
        return result

    monkeypatch.setattr(graph, "evaluate_hover_bemt", bad)
    result = graph.evaluate_model_graph(request())
    assert result["status"] == "EXECUTION_FAILED"
    assert result["outputs"] == result["output_units"] == {}
    assert result["stage_order"] == ["a", "b"]


def test_real_hover_force_cannot_bind_density(monkeypatch):
    body = request()
    body["connections"][1] = edge("h", "thrust_n", "w", "density_kg_m3")
    test_validation_failure_executes_nothing(body, monkeypatch)
