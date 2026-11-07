"""Contract tests for the experimental rigid-body JSON adapter."""

import copy
import json
import sys

import pytest

from physimesh.drone.rigid_body import RigidBodyState, propagate_rigid_body
from physimesh.drone.rigid_body_request import evaluate_rigid_body

CANONICAL_JSON = r'''{
  "evaluation": "rigid_body_constant_wrench_experimental",
  "initial_state": {
    "position_enu_m": [1, 2, 3],
    "velocity_enu_m_s": [0.1, 0.2, 0.3],
    "quaternion_body_to_enu": [1, 0, 0, 0],
    "angular_velocity_body_rad_s": [0.1, 0.2, 0.3]
  },
  "mass_kg": 2,
  "inertia_body_kg_m2": [[2, 0.1, 0], [0.1, 3, 0], [0, 0, 4]],
  "force_body_n": [1, 2, 3],
  "moment_cg_body_nm": [0.1, 0.2, 0.3],
  "gravity_enu_m_s2": [0, 0, -9.81],
  "dt_s": 0.01,
  "steps": 2,
  "property_source": "Caller supplied numerical example; unverified.",
  "applicability_declaration": "Experimental constant body wrench calculation only."
}'''
DECLARATION_LIMITATIONS = [
    "Caller declarations are unverified and do not establish applicability or verification.",
    "The caller's property source is an unverified literal, not validation.",
]
ENVELOPE_KEYS = {
    "model_id", "status", "physical_validation", "evidence_level",
    "aircraft_status", "feasibility", "inertia_physical_admissibility",
    "reasons", "limitations", "sources", "outputs", "output_units",
}
STATE_FIELDS = (
    "position_enu_m", "velocity_enu_m_s", "quaternion_body_to_enu",
    "angular_velocity_body_rad_s",
)
VECTOR_FIELDS = ("force_body_n", "moment_cg_body_nm", "gravity_enu_m_s2")
NUMERIC_PATHS = [("mass_kg",), ("dt_s",)] + [
    ("initial_state", name, index)
    for name in STATE_FIELDS
    for index in range(4 if name == "quaternion_body_to_enu" else 3)
] + [(name, index) for name in VECTOR_FIELDS for index in range(3)] + [
    ("inertia_body_kg_m2", row, col) for row in range(3) for col in range(3)
]
LIST_PATHS = [("initial_state", name) for name in STATE_FIELDS] + [
    (name,) for name in VECTOR_FIELDS
] + [("inertia_body_kg_m2",)] + [
    ("inertia_body_kg_m2", index) for index in range(3)
]


def request():
    return json.loads(CANONICAL_JSON)


def replace(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def at(value, path):
    for key in path:
        value = value[key]
    return value


def core_result(value):
    state = value["initial_state"]
    return propagate_rigid_body(
        initial_state=RigidBodyState(**{key: tuple(state[key]) for key in STATE_FIELDS}),
        mass_kg=value["mass_kg"],
        inertia_body_kg_m2=tuple(tuple(row) for row in value["inertia_body_kg_m2"]),
        force_body_n=tuple(value["force_body_n"]),
        moment_cg_body_nm=tuple(value["moment_cg_body_nm"]),
        gravity_enu_m_s2=tuple(value["gravity_enu_m_s2"]),
        dt_s=value["dt_s"], steps=value["steps"],
    )


def envelope(result, status):
    assert set(result) == ENVELOPE_KEYS
    assert result["model_id"] == "rigid_body_constant_body_wrench_rk4_v1"
    assert result["status"] == status
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None
    assert result["inertia_physical_admissibility"] == "NOT_ASSESSED"
    assert result["limitations"][-2:] == DECLARATION_LIMITATIONS
    json.dumps(result, allow_nan=False)


def refused(value, status="MODEL_INAPPLICABLE", adapter=True):
    result = evaluate_rigid_body(value)
    envelope(result, status)
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["reasons"]
    invalid_domain = request()
    invalid_domain["mass_kg"] = 0
    core = core_result(invalid_domain)
    assert len(core["limitations"]) == 7
    assert len(core["sources"]) == 2
    assert result["sources"] == core["sources"]
    assert result["limitations"] == core["limitations"] + DECLARATION_LIMITATIONS
    if adapter:
        assert result["reasons"] == ["Request is outside the supported domain."]
        expected = {
            **core,
            "status": status,
            "reasons": ["Request is outside the supported domain."],
            "limitations": core["limitations"] + DECLARATION_LIMITATIONS,
        }
        assert result == expected
    return result


def parity(value, status):
    before = copy.deepcopy(value)
    expected = core_result(value)
    expected["limitations"] += DECLARATION_LIMITATIONS
    actual = evaluate_rigid_body(value)
    envelope(actual, status)
    assert actual == expected
    assert value == before
    return actual


class Malicious:
    def fail(self, *args, **kwargs):
        raise AssertionError("Untrusted object protocol was invoked")
    __float__ = __int__ = __index__ = __iter__ = __len__ = fail
    __bool__ = __eq__ = __str__ = __repr__ = __getitem__ = fail
    strip = keys = items = fail


class IntSubclass(int):
    pass


class FloatSubclass(float):
    pass


class StrSubclass(str):
    pass


class DictSubclass(dict):
    def __iter__(self):
        raise AssertionError("Untrusted dict iteration")


class ListSubclass(list):
    def __iter__(self):
        raise AssertionError("Untrusted list iteration")


BAD_NUMBERS = [True, False, None, "1", float("nan"), float("inf"),
               -float("inf"), 10 ** 1000, IntSubclass(1), FloatSubclass(1), Malicious()]


def test_canonical_json_and_core_output():
    value = request()
    assert json.loads(json.dumps(value, allow_nan=False)) == value
    result = parity(value, "COMPUTED_EXPERIMENTAL")
    assert result["reasons"] == []
    assert result["sources"]
    assert result["outputs"]["steps"] == 2
    assert result["outputs"]["elapsed_s"] == 0.02


@pytest.mark.parametrize("key", tuple(request()))
def test_each_top_level_key_required(key):
    value = request()
    del value[key]
    refused(value)


@pytest.mark.parametrize("key", STATE_FIELDS)
def test_each_state_key_required(key):
    value = request()
    del value["initial_state"][key]
    refused(value)


@pytest.mark.parametrize("path", [(), ("initial_state",)])
@pytest.mark.parametrize("key", ["extra", 42, False, StrSubclass("unexpected")])
def test_extra_keys(path, key):
    value = request()
    at(value, path)[key] = 1
    refused(value)


@pytest.mark.parametrize("path", [(), ("initial_state",)])
def test_subclass_keys_even_with_equal_spelling(path):
    value = request()
    target = at(value, path)
    key = next(iter(target))
    saved = target.pop(key)
    target[StrSubclass(key)] = saved
    refused(value)


@pytest.mark.parametrize("bad", [None, [], (), True, Malicious(), DictSubclass()])
def test_root_must_be_exact_dict(bad):
    refused(bad)


@pytest.mark.parametrize("bad", [None, [], (), True, Malicious(), DictSubclass()])
def test_state_must_be_exact_dict(bad):
    value = request()
    value["initial_state"] = bad
    refused(value)


@pytest.mark.parametrize("path", NUMERIC_PATHS)
@pytest.mark.parametrize("bad", BAD_NUMBERS, ids=lambda value: type(value).__name__)
def test_builtin_finite_numbers_only(path, bad):
    value = request()
    replace(value, path, bad)
    refused(value)


@pytest.mark.parametrize("path", LIST_PATHS)
@pytest.mark.parametrize("kind", ["tuple", "short", "long", "dict", "subclass", "object"])
def test_exact_list_type_and_shape(path, kind):
    value = request()
    original = at(value, path)
    bad = {"tuple": lambda: tuple(original), "short": lambda: original[:-1],
           "long": lambda: original + [0], "dict": lambda: {},
           "subclass": lambda: ListSubclass(original), "object": Malicious}[kind]()
    replace(value, path, bad)
    refused(value)


@pytest.mark.parametrize("bad", [True, False, 2.0, "2", None, IntSubclass(2), Malicious()])
def test_steps_must_be_builtin_int(bad):
    value = request()
    value["steps"] = bad
    refused(value)


@pytest.mark.parametrize("key", ["property_source", "applicability_declaration"])
@pytest.mark.parametrize("bad", [None, True, 12, [], {}, "", " \t\r\n", "x" * 2001,
                                  StrSubclass("source"), Malicious()])
def test_declaration_contract(key, bad):
    value = request()
    value[key] = bad
    refused(value)


@pytest.mark.parametrize("key", ["property_source", "applicability_declaration"])
@pytest.mark.parametrize("text", ["x", "x" * 2000, "  literal source  ", "é" * 2000])
def test_valid_declaration_boundaries_are_unverified(key, text):
    value = request()
    value[key] = text
    result = parity(value, "COMPUTED_EXPERIMENTAL")
    assert text not in result["sources"]


@pytest.mark.parametrize("bad", ["", "rigid_body", "RIGID_BODY_CONSTANT_WRENCH_EXPERIMENTAL",
                                  "rigid_body_constant_wrench_experimental "])
def test_unsupported_evaluation(bad):
    value = request()
    value["evaluation"] = bad
    refused(value, "SOLVER_UNSUPPORTED")


@pytest.mark.parametrize("bad", [None, True, 1, [], {}, StrSubclass("rigid_body_constant_wrench_experimental"), Malicious()])
def test_evaluation_requires_exact_string(bad):
    value = request()
    value["evaluation"] = bad
    refused(value)


CORE_INVALID = [
    (("mass_kg",), 0), (("mass_kg",), -1),
    (("dt_s",), 0), (("dt_s",), -0.1),
    (("steps",), 0), (("steps",), -1), (("steps",), 10001),
    (("steps",), 10 ** 1000),
    (("initial_state", "quaternion_body_to_enu"), [0, 0, 0, 0]),
    (("initial_state", "quaternion_body_to_enu"), [2, 0, 0, 0]),
    (("inertia_body_kg_m2",), [[0, 0, 0], [0, 0, 0], [0, 0, 0]]),
    (("inertia_body_kg_m2",), [[1, 0, 0], [0, -1, 0], [0, 0, 1]]),
    (("inertia_body_kg_m2",), [[1, 0.1, 0], [0, 1, 0], [0, 0, 1]]),
    (("inertia_body_kg_m2",), [[1, 0, 0], [0, 0, 0], [0, 0, 1]]),
    (("mass_kg",), sys.float_info.min / 2),
    (("initial_state", "position_enu_m", 0), sys.float_info.min / 2),
    (("dt_s",), sys.float_info.max),
]


@pytest.mark.parametrize("path,bad", CORE_INVALID)
def test_core_domain_refusal_matches_core_and_preserves_request(path, bad):
    value = request()
    replace(value, path, bad)
    result = parity(value, "MODEL_INAPPLICABLE")
    assert result["outputs"] == result["output_units"] == {}
    assert result["sources"]
    assert result["reasons"] == ["Input or numerical arithmetic is outside the supported domain."]


@pytest.mark.parametrize("moment", [[0, 0, 0], [0.1, 0.2, 0.3]])
def test_torque_free_and_forced_core_output(moment):
    value = request()
    value["moment_cg_body_nm"] = moment
    result = parity(value, "COMPUTED_EXPERIMENTAL")
    for key in ("torque_free_relative_energy_drift", "torque_free_relative_angular_momentum_drift"):
        assert (result["outputs"][key] is None) == any(moment)


def test_adapter_refusal_preserves_request():
    value = request()
    value["steps"] = 2.0
    before = copy.deepcopy(value)
    refused(value)
    assert value == before


def test_results_do_not_alias_request_or_later_results():
    value = request()
    before = copy.deepcopy(value)
    first = evaluate_rigid_body(value)
    first["outputs"]["initial_state"]["position_enu_m"][0] = 999
    first["limitations"].append("changed")
    first["sources"].clear()
    assert value == before
    assert evaluate_rigid_body(value) == evaluate_rigid_body(before)
    refusal = evaluate_rigid_body({})
    refusal["limitations"].clear()
    refusal["reasons"].clear()
    refused({})
