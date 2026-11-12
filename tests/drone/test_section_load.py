"""Synthetic contract and arithmetic checks; no physical validation."""

import hashlib
import json
import math
from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from physimesh.drone import section_load as load
from physimesh.drone import section_polar as polar


@pytest.fixture
def request_data():
    tables = []
    for reynolds in (1000.0, 10000000.0):
        rows = []
        for alpha in (-1.5, 0.0, 1.5):
            rows.append({"alpha_rad": alpha,
                         "cl": 2 * alpha + 0.1 * math.log(reynolds / 1000),
                         "cd": 0.1 + 0.02 * (alpha + 1.5) + 0.01 * math.log(reynolds / 1000)})
        tables.append({"reynolds_number": reynolds, "rows": rows})
    return {
        "evaluation": load.EVALUATION,
        "polar": {"airfoil_id": "invented-synthetic", "source": "invented fixture, no dataset",
                  "source_kind": "synthetic", "uncertainty_status": "unknown",
                  "sampled_mach_number": 0.1, "declared_mach_interval": [0, 0.9],
                  "reynolds_tables": tables},
        "section": {"axial_velocity_m_s": 5, "tangential_velocity_m_s": 20,
                    "chord_m": 0.1, "radius_m": 0.4, "density_kg_m3": 1.2,
                    "dynamic_viscosity_pa_s": 1.8e-5, "speed_of_sound_m_s": 343,
                    "pitch_rad": 0.4, "blade_count": 2},
    }


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reseal(value):
    value["evaluation_sha256"] = _digest({key: item for key, item in value.items()
                                         if key != "evaluation_sha256"})


def _spy(monkeypatch):
    calls = []
    original = polar.evaluate_section_polar

    def evaluate(request):
        calls.append(deepcopy(request))
        return original(request)

    monkeypatch.setattr(polar, "evaluate_section_polar", evaluate)
    return calls, original


def test_actual_once_and_independent_child_identity(request_data, monkeypatch):
    original_request = deepcopy(request_data)
    calls, actual_evaluator = _spy(monkeypatch)
    result = load.evaluate_section_load(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["lookup_result_count"] == len(calls) == 1
    output = result["outputs"]
    assert output["actual_lookup_request"] == calls[0]
    # Independent comparison is outside the orchestration; no fallback evaluator.
    assert output["actual_lookup_result"] == actual_evaluator(calls[0])
    assert output["load_state"] == "COMPUTED"
    assert request_data == original_request
    assert result["physical_validation"] == result["numerical_qualification"] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is result["feasibility"] is None


def test_kinematics_and_decimal95_loads(request_data):
    result = load.evaluate_section_load(request_data)
    output, section = result["outputs"], request_data["section"]
    speed = math.hypot(5, 20)
    assert output["kinematics"] == {"phi_rad": math.atan2(5, 20), "relative_speed_m_s": speed}
    query = output["actual_lookup_request"]["query"]
    assert query == {"alpha_rad": 0.4 - math.atan2(5, 20),
                     "reynolds_number": 1.2 * speed * 0.1 / 1.8e-5, "mach_number": speed / 343}
    coefficients = output["actual_lookup_result"]["outputs"]
    with localcontext() as context:
        context.prec = 95
        d = Decimal
        w = d(speed)
        q = d("0.5") * d(section["density_kg_m3"]) * w * w
        scale = d(section["blade_count"]) * q * d(section["chord_m"])
        lift, drag = scale * d(coefficients["cl"]), scale * d(coefficients["cd"])
        thrust = (lift * d(20) - drag * d(5)) / w
        torque = d(section["radius_m"]) * (lift * d(5) + drag * d(20)) / w
        expected = dict(zip(output["loads"], (q, lift, drag, thrust, torque), strict=True))
        for key, value in expected.items():
            assert output["loads"][key] == pytest.approx(float(value), rel=3e-15, abs=1e-14)


@pytest.mark.parametrize("axis", ["alpha_rad", "reynolds_number", "mach_number", "all"])
def test_ood_retains_full_child(request_data, monkeypatch, axis):
    p = request_data["polar"]
    if axis in ("alpha_rad", "all"):
        for table in p["reynolds_tables"]:
            for row in table["rows"]:
                row["alpha_rad"] = row["alpha_rad"] / 100
    if axis in ("reynolds_number", "all"):
        p["reynolds_tables"][0]["reynolds_number"] = 1
        p["reynolds_tables"][1]["reynolds_number"] = 2
    if axis in ("mach_number", "all"):
        p["sampled_mach_number"] = 0
        p["declared_mach_interval"] = [0, 0]
    calls, original = _spy(monkeypatch)
    result = load.evaluate_section_load(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["lookup_result_count"] == len(calls) == 1
    assert result["outputs"]["load_state"] == "NOT_RUN_OUT_OF_POLAR_DOMAIN"
    assert result["outputs"]["loads"] is None
    assert result["outputs"]["actual_lookup_result"] == original(calls[0])
    axes = result["outputs"]["actual_lookup_result"]["out_of_domain_axes"]
    assert axes == (["alpha_rad", "reynolds_number", "mach_number"] if axis == "all" else [axis])
    assert result["feasibility"] is None


def test_native_request_and_response_hashes(request_data):
    request_data["polar"]["source"] = "invented α fixture"
    result = load.evaluate_section_load(request_data)
    assert result["request_sha256"] == _digest(request_data)
    assert result["evaluation_sha256"] == _digest({key: value for key, value in result.items()
                                                  if key != "evaluation_sha256"})
    changed = deepcopy(request_data)
    changed["section"]["axial_velocity_m_s"] = 5.0
    assert load.evaluate_section_load(changed)["request_sha256"] != result["request_sha256"]


@pytest.mark.parametrize(
    "case", ["late_table", "empty_tables", "blade_bool", "zero_wt", "subnormal", "extra"]
)
def test_static_preflight_before_child(request_data, monkeypatch, case):
    request_data["polar"]["declared_mach_interval"] = [0, 0.001]
    request_data["polar"]["sampled_mach_number"] = 0
    if case == "late_table":
        request_data["polar"]["reynolds_tables"][-1]["rows"][-1]["cd"] = -1
    elif case == "empty_tables":
        request_data["polar"]["reynolds_tables"] = []
    elif case == "blade_bool":
        request_data["section"]["blade_count"] = True
    elif case == "zero_wt":
        request_data["section"]["tangential_velocity_m_s"] = 0
    elif case == "subnormal":
        request_data["section"]["pitch_rad"] = math.nextafter(0.0, 1.0)
    else:
        request_data["section"]["extra"] = 1
    calls, _ = _spy(monkeypatch)
    result = load.evaluate_section_load(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["lookup_result_count"] == len(calls) == 0
    assert result["request_sha256"] is result["evaluation_sha256"] is None


@pytest.mark.parametrize("path,value", [
    (("status",), "EXECUTION_FAILED"), (("physical_validation",), "ESTABLISHED"),
    (("output_units", "cl"), "N"), (("outputs", "cl"), 90),
    (("outputs", "query", "alpha_rad"), 0),
    (("outputs", "interpolation", "alpha_indices", 0), True),
    (("outputs", "interpolation", "source_rows", 0, "cl"), 13),
    (("outputs", "interpolation", "source_rows", 0, "weight"), 0),
    (("source_urls", 0), "https://invalid.example/private"),
    (("request_sha256",), "0" * 64), (("limits", "input_json", "max_depth"), 99),
])
def test_rehashed_child_tampering_rejected(request_data, monkeypatch, path, value):
    original = polar.evaluate_section_polar

    def tampered(request):
        child = original(request)
        target = child
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        _reseal(child)
        return child

    monkeypatch.setattr(polar, "evaluate_section_polar", tampered)
    result = load.evaluate_section_load(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["LOOKUP_BOUNDARY_FAILED"]
    assert result["lookup_result_count"] == 0
    assert result["outputs"] == result["output_units"] == {}


@pytest.mark.parametrize("key,value", [
    ("axial_velocity_m_s", -1), ("axial_velocity_m_s", math.nextafter(0.0, 1.0)),
    ("tangential_velocity_m_s", 0), ("chord_m", -1), ("radius_m", 0),
    ("density_kg_m3", math.inf), ("dynamic_viscosity_pa_s", math.nan),
    ("speed_of_sound_m_s", True), ("pitch_rad", -1), ("pitch_rad", math.pi / 2 + 1e-10),
    ("blade_count", 0), ("blade_count", 65), ("blade_count", 2.0), ("blade_count", True),
    ("chord_m", 1 << 1023), ("pitch_rad", "0"), ("radius_m", None),
])
def test_section_numeric_contract(request_data, monkeypatch, key, value):
    request_data["section"][key] = value
    calls, _ = _spy(monkeypatch)
    result = load.evaluate_section_load(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["lookup_result_count"] == len(calls) == 0


@pytest.mark.parametrize("path", [(), ("section",), ("polar",),
                                  ("polar", "reynolds_tables", 1),
                                  ("polar", "reynolds_tables", 1, "rows", 2)])
@pytest.mark.parametrize("mode", ["missing", "extra"])
def test_exact_schema_keys(request_data, monkeypatch, path, mode):
    target = request_data
    for key in path:
        target = target[key]
    if mode == "missing":
        target.pop(next(iter(target)))
    else:
        target["unexpected"] = 0
    calls, _ = _spy(monkeypatch)
    assert load.evaluate_section_load(request_data)["status"] == "MODEL_INAPPLICABLE"
    assert calls == []


def test_signed_zero_child_tamper_rehashed(request_data, monkeypatch):
    original = polar.evaluate_section_polar

    def tampered(request):
        child = original(request)
        child["outputs"]["interpolation"]["source_rows"][0]["alpha_rad"] = -0.0
        _reseal(child)
        return child

    monkeypatch.setattr(polar, "evaluate_section_polar", tampered)
    result = load.evaluate_section_load(request_data)
    assert result["reasons"] == ["LOOKUP_BOUNDARY_FAILED"]
    assert result["lookup_result_count"] == 0
    assert result["outputs"] == result["output_units"] == {}


@pytest.mark.parametrize("cl", [0, -2])
def test_zero_cl_and_signed_loads(request_data, cl):
    for table in request_data["polar"]["reynolds_tables"]:
        for row in table["rows"]:
            row.update(cl=cl, cd=0.1)
    result = load.evaluate_section_load(request_data)
    values = result["outputs"]["loads"]
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert values["thrust_density_n_m"] < 0
    assert values["torque_density_nm_m"] > 0 if cl == 0 else values["torque_density_nm_m"] < 0
    assert values["lift_density_n_m"] == 0 if cl == 0 else values["lift_density_n_m"] < 0


def test_native_exact_knot_large_cl(request_data):
    request_data["section"].update(axial_velocity_m_s=0, pitch_rad=0,
                                    density_kg_m3=1, chord_m=1, dynamic_viscosity_pa_s=0.02)
    for table in request_data["polar"]["reynolds_tables"]:
        table["rows"][1]["cl"] = 2**53 + 1
    result = load.evaluate_section_load(request_data)
    child = result["outputs"]["actual_lookup_result"]["outputs"]
    assert type(child["cl"]) is int and child["cl"] == 2**53 + 1
    assert child["interpolation"]["alpha_indices"] == [1, 1]
    assert child["interpolation"]["reynolds_indices"] == [0, 0]
    assert type(result["outputs"]["loads"]["lift_density_n_m"]) is float


def test_guard_uses_no_child_numerical_helpers(request_data, monkeypatch):
    original = polar.evaluate_section_polar

    def forbidden(*args, **kwargs):
        raise AssertionError("guard must independently reconstruct")

    def actual_once(request):
        child = original(request)
        for name in ("_lookup", "_mix", "_weight", "_bracket", "_response", "_seal"):
            monkeypatch.setattr(polar, name, forbidden)
        return child

    monkeypatch.setattr(polar, "evaluate_section_polar", actual_once)
    # The fresh catalog normally uses _response: preserve only that metadata path.
    catalog = polar.section_polar_catalog()
    monkeypatch.setattr(polar, "section_polar_catalog", lambda: deepcopy(catalog))
    result = load.evaluate_section_load(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["lookup_result_count"] == 1


@pytest.mark.parametrize("case", ["cycle", "depth", "container", "string", "utf8", "subclass"])
def test_bounded_before_copy_hooks(request_data, monkeypatch, case):
    hooks = []

    class Foreign(dict):
        def __deepcopy__(self, memo):
            hooks.append("copy")
            raise RuntimeError("PRIVATE foreign hook")

    if case == "cycle":
        request_data["section"] = request_data
    elif case == "depth":
        nested = 0
        for _ in range(10):
            nested = [nested]
        request_data["section"]["chord_m"] = nested
    elif case == "container":
        request_data["section"]["chord_m"] = [0] * 257
    elif case == "string":
        request_data["polar"]["source"] = "x" * 2001
    elif case == "utf8":
        request_data["polar"]["source"] = "\ud800"
    else:
        request_data["section"] = Foreign(request_data["section"])
    calls, _ = _spy(monkeypatch)
    result = load.evaluate_section_load(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert hooks == calls == []
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("output", [False, True])
def test_exact_walk_limits(output):
    nodes = [[0] * 255 for _ in range(128)]
    nodes[-1].pop()
    load._walk(nodes, output=output)
    nodes[-1].append(0)
    with pytest.raises(ValueError):
        load._walk(nodes, output=output)
    nested = 0
    for _ in range(15 if output else 9):
        nested = [nested]
    load._walk(nested, output=output)
    with pytest.raises(ValueError):
        load._walk([nested], output=output)


@pytest.mark.parametrize("field", ["status_matrix", "source_urls", "limits", "output_field_units"])
def test_fresh_child_catalog_tampering(request_data, monkeypatch, field):
    original = polar.section_polar_catalog

    def tampered():
        catalog = original()
        catalog[field] = []
        return catalog

    monkeypatch.setattr(polar, "section_polar_catalog", tampered)
    result = load.evaluate_section_load(request_data)
    assert result["reasons"] == ["LOOKUP_BOUNDARY_FAILED"]
    assert result["lookup_result_count"] == 0 and result["outputs"] == {}


@pytest.mark.parametrize("point", [1, 2, 3, 4, "persistent"])
def test_hash_faults_atomic(request_data, monkeypatch, point):
    original = load.sha256_record
    calls = 0

    def faulty(value):
        nonlocal calls
        calls += 1
        if point == "persistent" or point == calls:
            raise RuntimeError("PRIVATE hash fault")
        return original(value)

    monkeypatch.setattr(load, "sha256_record", faulty)
    result = load.evaluate_section_load(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["outputs"] == result["output_units"] == {}
    assert result["lookup_result_count"] == (1 if point == 4 else 0)
    if point in (1, "persistent"):
        assert result["request_sha256"] is result["evaluation_sha256"] is None
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("point", ["child", "loads", "hash"])
def test_base_exception_propagates(request_data, monkeypatch, point):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt("stop")

    module, name = ((polar, "evaluate_section_polar") if point == "child" else
                    (load, "_loads" if point == "loads" else "sha256_record"))
    monkeypatch.setattr(module, name, interrupt)
    with pytest.raises(KeyboardInterrupt):
        load.evaluate_section_load(request_data)


def test_parent_catalog_fresh_no_evaluator(request_data, monkeypatch):
    def forbidden(*args):
        raise AssertionError("catalog must not evaluate")

    monkeypatch.setattr(polar, "evaluate_section_polar", forbidden)
    first = load.section_load_catalog()
    first["source_urls"].clear()
    first["limits"]["output_json"]["max_depth"] = 0
    first["output_field_units"]["loads"].clear()
    fresh = load.section_load_catalog()
    assert len(fresh["source_urls"]) == 2
    assert fresh["limits"]["output_json"]["max_depth"] == 16
    assert fresh["output_field_units"]["loads"]["torque_density_nm_m"] == "N*m/m"


@pytest.mark.parametrize("stage", ["kinematics", "load_overflow", "load_underflow"])
def test_arithmetic_failure_counts_no_payload(request_data, monkeypatch, stage):
    section = request_data["section"]
    if stage == "kinematics":
        section["density_kg_m3"] = 1e308
    elif stage == "load_overflow":
        section["radius_m"] = 1e308
    else:
        section["radius_m"] = 2.2250738585072014e-308
        for table in request_data["polar"]["reynolds_tables"]:
            for row in table["rows"]:
                row.update(cl=0, cd=0.001)
    calls, _ = _spy(monkeypatch)
    result = load.evaluate_section_load(request_data)
    expected_count = 0 if stage == "kinematics" else 1
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["SECTION_LOAD_EXECUTION_FAILED"]
    assert result["lookup_result_count"] == len(calls) == expected_count
    assert result["outputs"] == result["output_units"] == {}


def test_persistent_root_seal_hash_failure(request_data, monkeypatch):
    original = load.sha256_record

    def faulty(value):
        if value.get("evaluation") == load.EVALUATION and "request_sha256" in value:
            raise RuntimeError("PRIVATE persistent response hash fault")
        return original(value)

    monkeypatch.setattr(load, "sha256_record", faulty)
    result = load.evaluate_section_load(request_data)
    assert result["status"] == "EXECUTION_FAILED" and result["lookup_result_count"] == 1
    assert result["request_sha256"] is result["evaluation_sha256"] is None
    assert result["outputs"] == result["output_units"] == {}
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("mode", ["exception", "numeric_failure", "hidden_subclass"])
def test_child_failure_is_atomic_before_hooks(request_data, monkeypatch, mode):
    hooks = []
    original = polar.evaluate_section_polar

    class Hidden(dict):
        def __deepcopy__(self, memo):
            hooks.append("copy")
            raise RuntimeError("PRIVATE foreign hook")

    if mode == "numeric_failure":
        for table in request_data["polar"]["reynolds_tables"]:
            for row in table["rows"]:
                row["cd"] = 2.2250738585072014e-308

    def child(request):
        if mode == "exception":
            raise RuntimeError("PRIVATE child failure")
        result = original(request)
        if mode == "hidden_subclass":
            result["hidden"] = Hidden()
        return result

    monkeypatch.setattr(polar, "evaluate_section_polar", child)
    result = load.evaluate_section_load(request_data)
    assert result["reasons"] == ["LOOKUP_BOUNDARY_FAILED"]
    assert result["lookup_result_count"] == 0 and hooks == []
    assert result["outputs"] == result["output_units"] == {}
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("path,value", [
    (("outputs", "cl"), True), (("diagnostics_complete",), 1),
    (("outputs", "interpolation", "source_rows", 0, "table_index"), 0.0),
    (("output_units", "query", "reynolds_number"), "kg"),
    (("output_units", "interpolation", "source_rows", "cd"), "N"),
    (("limits", "input_json", "max_nodes_including_keys"), 32768.0),
])
def test_full_child_units_and_types(request_data, monkeypatch, path, value):
    original = polar.evaluate_section_polar

    def tampered(request):
        result = original(request)
        target = result
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        _reseal(result)
        return result

    monkeypatch.setattr(polar, "evaluate_section_polar", tampered)
    result = load.evaluate_section_load(request_data)
    assert result["reasons"] == ["LOOKUP_BOUNDARY_FAILED"] and result["lookup_result_count"] == 0
    assert result["outputs"] == result["output_units"] == {}


def test_full_result_detached_from_child_and_caller(request_data, monkeypatch):
    original = polar.evaluate_section_polar
    children = []

    def child(request):
        result = original(request)
        children.append(result)
        return result

    monkeypatch.setattr(polar, "evaluate_section_polar", child)
    result = load.evaluate_section_load(request_data)
    frozen = deepcopy(result)
    children[0]["outputs"]["interpolation"]["source_rows"][0]["cl"] = 999
    request_data["polar"]["reynolds_tables"].clear()
    assert result == frozen


@pytest.mark.parametrize("maximum", [False, True])
def test_section_endpoints_and_maximum_polar(request_data, monkeypatch, maximum):
    request_data["section"].update(axial_velocity_m_s=0, pitch_rad=math.pi / 2)
    if maximum:
        rows = [{"alpha_rad": -3.0 + 6.0 * index / 255, "cl": 0, "cd": 0.1}
                for index in range(256)]
        request_data["polar"]["reynolds_tables"] = [
            {"reynolds_number": 1000 + index * 1e6, "rows": deepcopy(rows)} for index in range(8)
        ]
    else:
        for table in request_data["polar"]["reynolds_tables"]:
            table["rows"][-1]["alpha_rad"] = math.pi / 2
    calls, _ = _spy(monkeypatch)
    result = load.evaluate_section_load(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL" and len(calls) == 1
    output = result["outputs"]
    assert output["load_state"] == "COMPUTED" and output["kinematics"]["phi_rad"] == 0
    corners = output["actual_lookup_result"]["outputs"]["interpolation"]["source_rows"]
    assert len(corners) in (1, 2, 4) and all(row["weight"] > 0 for row in corners)
