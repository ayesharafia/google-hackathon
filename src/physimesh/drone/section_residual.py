"""Experimental positive-branch local QPROP circulation residual; no root solve."""

import math
import sys
from copy import deepcopy

from . import section_load as _load
from .provenance import sha256_record
from .section_load import _guard_lookup as _guard_v132

EVALUATION = "section_residual_experimental"
SCHEMA_VERSION = "section_residual_v1"
_SECTION_KEYS = (
    "imposed_axial_velocity_m_s imposed_tangential_velocity_m_s psi_rad tip_radius_m "
    "chord_m radius_m density_kg_m3 dynamic_viscosity_pa_s speed_of_sound_m_s "
    "pitch_rad blade_count"
)

_LOAD_SECTION_KEYS = (
    "axial_velocity_m_s tangential_velocity_m_s chord_m radius_m density_kg_m3 "
    "dynamic_viscosity_pa_s speed_of_sound_m_s pitch_rad blade_count"
)


def _require(condition):
    if not condition:
        raise ValueError("Invalid section residual request")


def _checked(value):
    _require(type(value) is float and math.isfinite(value))
    _require(value == 0 or abs(value) >= sys.float_info.min)
    return value


def _product(a, b):
    value = _checked(a * b)
    _require(value != 0 or a == 0 or b == 0)
    return value


def _quotient(a, b):
    value = _checked(a / b)
    _require(value != 0 or a == 0)
    return value


def _sum(a, b):
    value = _checked(math.fsum((a, b)))
    _require(value != 0 or a == -b)
    return value


def _walk(value, *, output=False, child=False):
    remaining = 32768 if child or not output else 65536
    max_depth = 16 if child else (24 if output else 10)

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        _require(remaining >= 0 and depth <= max_depth)
        kind = type(item)
        if kind is str:
            _require(len(item) <= 2000)
            item.encode("utf-8", "strict")
        elif kind is int:
            _require(item.bit_length() <= 1023)
        elif kind is float:
            _require(math.isfinite(item))
        elif kind is dict:
            _require(len(item) <= 256)
            for key, nested in item.items():
                _require(type(key) is str)
                visit(key, depth + 1)
                visit(nested, depth + 1)
        elif kind is list:
            _require(len(item) <= 256)
            for nested in item:
                visit(nested, depth + 1)
        else:
            _require(kind is bool or item is None)

    visit(value, 1)


def _keys(value, keys):
    _require(type(value) is dict and set(value) == set(keys.split()))


def _exact(actual, expected):
    _require(type(actual) is type(expected))
    if type(expected) is dict:
        _require(actual.keys() == expected.keys())
        for key in expected:
            _exact(actual[key], expected[key])
    elif type(expected) is list:
        _require(len(actual) == len(expected))
        for left, right in zip(actual, expected, strict=True):
            _exact(left, right)
    else:
        _require(actual == expected)
        if type(expected) is float and expected == 0:
            _require(math.copysign(1, actual) == math.copysign(1, expected))


def _snapshot(value, *, output=False, child=False):
    _walk(value, output=output, child=child)
    result = deepcopy(value)
    _walk(result, output=output, child=child)
    _exact(result, value)
    return result


def _number(value, *, zero=False):
    _require(type(value) in (int, float))
    number = _checked(float(value))
    _require(number >= 0 if zero else number > 0)
    return number


def _preflight(request):
    _keys(request, "evaluation polar section")
    _require(type(request["evaluation"]) is str)
    section = request["section"]
    _keys(section, _SECTION_KEYS)
    for key in _SECTION_KEYS.split():
        if key == "blade_count":
            _require(type(section[key]) is int and 1 <= section[key] <= 64)
        else:
            _number(section[key], zero=key in ("imposed_axial_velocity_m_s", "pitch_rad"))
    _require(section["pitch_rad"] <= math.pi / 2)
    _require(section["tip_radius_m"] > section["radius_m"])
    _load._polar._preflight({"polar": request["polar"], "query": {
        "alpha_rad": 0, "reynolds_number": 1, "mach_number": 0,
    }})
    # Only after every static field and polar table has passed.
    _require(math.atan2(float(section["imposed_axial_velocity_m_s"]),
                        float(section["imposed_tangential_velocity_m_s"]))
             < float(section["psi_rad"]) < math.pi / 2)


def _velocity(section):
    ua = float(section["imposed_axial_velocity_m_s"])
    ut = float(section["imposed_tangential_velocity_m_s"])
    psi = float(section["psi_rad"])
    speed = _checked(math.hypot(ua, ut))
    sine, cosine = _checked(math.sin(psi)), _checked(math.cos(psi))
    wa = _sum(_product(0.5, ua), _product(_product(0.5, speed), sine))
    wt = _sum(_product(0.5, ut), _product(_product(0.5, speed), cosine))
    va, vt = _sum(wa, -ua), _sum(ut, -wt)
    _require(wa > 0 and wt > 0 and va > 0 and vt > 0)
    return {"imposed_axial_velocity_m_s": ua, "imposed_tangential_velocity_m_s": ut,
            "imposed_speed_m_s": speed, "axial_velocity_m_s": wa,
            "tangential_velocity_m_s": wt, "induced_axial_velocity_m_s": va,
            "induced_tangential_velocity_m_s": vt, "psi_rad": psi}


def evaluate_section_residual(request):
    """Evaluate one prescribed psi with exactly one guarded V133 child at most."""
    return _evaluate(request)


# Reuse only the accepted pure nested guard, never a child numerical helper.
_V133_CATALOG = _snapshot(_load.section_load_catalog(), child=True)
_CHILD_KEYS = frozenset(_V133_CATALOG) - frozenset((
    "required_fields", "input_units", "output_field_units", "request_contract",
    "formulas", "status_matrix", "hash_contract", "boundary_contract",
))
_JSON = {
    "max_nodes_including_keys": 32768, "max_depth": 10, "max_container_items": 256,
    "max_string_characters": 2000, "max_integer_bits": 1023, "root_depth": 1,
}
_LIMITS = {
    "input_json": _JSON,
    "output_json": {**_JSON, "max_nodes_including_keys": 65536, "max_depth": 24},
    "load_input_json": deepcopy(_V133_CATALOG["limits"]["input_json"]),
    "load_output_json": deepcopy(_V133_CATALOG["limits"]["output_json"]),
    "core_work": {"load_calls_max": 1, "blade_count_min": 1, "blade_count_max": 64},
}
_DRELA_URL = "https://web.mit.edu/drela/Public/web/qprop/qprop_theory.pdf"
_SOURCE_URLS = list(dict.fromkeys([_DRELA_URL, *_V133_CATALOG["source_urls"]]))
_LIMITATIONS = [
    "Experimental local prescribed-psi circulation residual only; no derivative or root claim.",
    "Ua and Ut exclude this rotor's own induction; only the positive induction branch is admitted.",
    "Tip, hub, windmill and reverse-flow operation are excluded.",
    ("Non-contracting constant-pitch helical wake assumption; "
     "strictly valid only for lightly-loaded Goldstein circulation."),
    "Modified Prandtl factor is empirical; no CFD, physical validation or numerical qualification.",
    "Caller polar source, classification, uncertainty and Mach applicability remain UNVERIFIED.",
    "No external dataset, source fetching, API, UI, rotor solver or integration.",
    ("Checked binary64 arithmetic can refuse representational extremes; "
     "no full-range promise or hidden F limit."),
    "Nested V132 guard is reused; V133 kinematics, loads and complete root are reconstructed independently.",
    "Counts mean fully guarded child results, including OOD; not attempts, physical evidence or attestation.",
    "Hashes bind full native JSON, not authenticity, runtime identity, physical validity or feasibility.",
    "Unexpected child failure is sanitized as LOAD_BOUNDARY_FAILED without trusting child failure causes.",
]
_VELOCITY_UNITS = {
    "imposed_axial_velocity_m_s": "m/s", "imposed_tangential_velocity_m_s": "m/s",
    "imposed_speed_m_s": "m/s", "axial_velocity_m_s": "m/s",
    "tangential_velocity_m_s": "m/s", "induced_axial_velocity_m_s": "m/s",
    "induced_tangential_velocity_m_s": "m/s", "psi_rad": "rad",
}
_CLOSURE_UNITS = {
    "radius_ratio": "1", "tip_gap": "1", "local_wake_lambda": "1", "f": "1",
    "exp_minus_f": "1", "acos_exp_minus_f_rad": "rad", "F": "1",
    "geometry_argument": "1", "geometry_factor": "1", "circulation_scale_m": "m",
    "gamma_lift_m2_s": "m^2/s", "gamma_induced_m2_s": "m^2/s",
}


def _query_kinematics(section):
    """Independent V133 reconstruction with the accepted operation order."""
    wa = float(section["axial_velocity_m_s"])
    wt = float(section["tangential_velocity_m_s"])
    phi = _checked(math.atan2(wa, wt))
    _require(phi != 0 or wa == 0)
    speed = _checked(math.hypot(wa, wt))
    alpha = _sum(float(section["pitch_rad"]), -phi)
    reynolds = _quotient(_product(_product(float(section["density_kg_m3"]), speed),
                                     float(section["chord_m"])), float(section["dynamic_viscosity_pa_s"]))
    mach = _quotient(speed, float(section["speed_of_sound_m_s"]))
    return {"phi_rad": phi, "relative_speed_m_s": speed}, {
        "alpha_rad": alpha, "reynolds_number": reynolds, "mach_number": mach,
    }


def _reconstruct_loads(section, kinematics, coefficients):
    speed = kinematics["relative_speed_m_s"]
    q = _product(_product(0.5, float(section["density_kg_m3"])), _product(speed, speed))
    scale = _product(_product(float(section["blade_count"]), q), float(section["chord_m"]))
    lift = _product(scale, float(coefficients["cl"]))
    drag = _product(scale, float(coefficients["cd"]))
    axial = _quotient(float(section["axial_velocity_m_s"]), speed)
    tangential = _quotient(float(section["tangential_velocity_m_s"]), speed)
    thrust = _sum(_product(lift, tangential), -_product(drag, axial))
    torque = _product(float(section["radius_m"]),
                      _sum(_product(lift, axial), _product(drag, tangential)))
    return {"dynamic_pressure_pa": q, "lift_density_n_m": lift, "drag_density_n_m": drag,
            "thrust_density_n_m": thrust, "torque_density_nm_m": torque}


def _guard_load(actual, request):
    """Pure complete V133 guard, reusing the accepted pure V132 nested guard."""
    _walk(actual, child=True)
    _walk(request)
    catalog = _snapshot(_load.section_load_catalog(), child=True)
    _exact(catalog, _V133_CATALOG)
    _require(type(actual) is dict and actual.keys() == _CHILD_KEYS)
    section = request["section"]
    kinematics, query = _query_kinematics(section)
    lookup_request = {"evaluation": _FROZEN_LOOKUP_EVALUATION,
                      "polar": deepcopy(request["polar"]), "query": query}
    _walk(lookup_request)
    output = actual["outputs"]
    _keys(output, "kinematics actual_lookup_request actual_lookup_result load_state loads")
    _exact(output["actual_lookup_request"], lookup_request)
    _guard_v132(output["actual_lookup_result"], lookup_request)
    ran = output["actual_lookup_result"]["status"] == "COMPUTED_EXPERIMENTAL"
    loads = (_reconstruct_loads(section, kinematics, output["actual_lookup_result"]["outputs"])
             if ran else None)
    expected = {key: deepcopy(catalog[key]) for key in _CHILD_KEYS}
    units = deepcopy(catalog["output_field_units"])
    if not ran:
        units["actual_lookup_result"]["outputs"] = {}
        units["loads"] = "not_applicable"
    expected.update(
        status="COMPUTED_EXPERIMENTAL", reasons=[], lookup_result_count=1,
        diagnostics_complete=True, request_sha256=sha256_record(request),
        outputs={"kinematics": kinematics, "actual_lookup_request": lookup_request,
                 "actual_lookup_result": deepcopy(output["actual_lookup_result"]),
                 "load_state": "COMPUTED" if ran else "NOT_RUN_OUT_OF_POLAR_DOMAIN", "loads": loads},
        output_units=units,
    )
    expected["evaluation_sha256"] = sha256_record({
        key: value for key, value in expected.items() if key != "evaluation_sha256"})
    _exact(actual, expected)


_FROZEN_LOOKUP_EVALUATION = _load._V132_CATALOG["evaluation"]


def _closure(section, velocity, load_result):
    r, tip = float(section["radius_m"]), float(section["tip_radius_m"])
    blades = float(section["blade_count"])
    ratio = _quotient(r, tip)
    _require(0 < ratio < 1)
    gap = _sum(1.0, -ratio)
    _require(gap > 0)
    wake = _product(ratio, _quotient(velocity["axial_velocity_m_s"],
                                     velocity["tangential_velocity_m_s"]))
    _require(wake > 0)
    f = _quotient(_product(_product(blades, 0.5), gap), wake)
    _require(f > 0)
    exponential = _checked(math.exp(-f))
    _require(0 < exponential < 1)
    angle = _checked(math.acos(exponential))
    _require(angle > 0)
    factor = _product(_quotient(2.0, math.pi), angle)
    _require(0 < factor < 1)
    numerator = _product(_product(4.0, wake), tip)
    denominator = _product(_product(math.pi, blades), r)
    argument = _quotient(numerator, denominator)
    _require(argument > 0)
    geometry = _checked(math.hypot(1.0, argument))
    scale = _quotient(_product(_product(4.0, math.pi), r), blades)
    induced = _product(_product(_product(velocity["induced_tangential_velocity_m_s"], scale),
                                  factor), geometry)
    _require(induced > 0)
    speed = load_result["outputs"]["kinematics"]["relative_speed_m_s"]
    cl = float(load_result["outputs"]["actual_lookup_result"]["outputs"]["cl"])
    lift = _product(_product(_product(0.5, speed), float(section["chord_m"])), cl)
    residual = _sum(induced, -lift)
    return {
        "radius_ratio": ratio, "tip_gap": gap, "local_wake_lambda": wake,
        "f": f, "exp_minus_f": exponential, "acos_exp_minus_f_rad": angle, "F": factor,
        "geometry_argument": argument, "geometry_factor": geometry, "circulation_scale_m": scale,
        "gamma_lift_m2_s": lift, "gamma_induced_m2_s": induced,
    }, residual


def _output_units(ran=True):
    return {
        "kinematics": deepcopy(_VELOCITY_UNITS),
        "actual_load_request": deepcopy(_V133_CATALOG["input_units"]),
        "actual_load_result": {"outputs": _load_result_units(ran)},
        "residual_state": "label", "closure": deepcopy(_CLOSURE_UNITS) if ran else "not_applicable",
        "residual_m2_s": "m^2/s" if ran else "not_applicable",
    }


def _load_result_units(ran):
    units = deepcopy(_V133_CATALOG["output_field_units"])
    if not ran:
        units["actual_lookup_result"]["outputs"] = {}
        units["loads"] = "not_applicable"
    return units


def _response(status, reasons, digest=None, count=0):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "reasons": list(reasons), "outputs": {}, "output_units": {},
        "load_result_count": count, "lookup_result_count": count, "diagnostics_complete": False,
        "physical_validation": "NOT_ESTABLISHED", "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED", "aircraft_status": None, "feasibility": None,
        "evidence_level": "unverified", "source_classification": "UNVERIFIED_CALLER_ASSERTION",
        "mach_interval_status": "UNVERIFIED_CALLER_APPLICABILITY_ONLY",
        "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS), "source_urls": list(_SOURCE_URLS),
        "request_sha256": digest, "evaluation_sha256": None,
    }


def _seal(response):
    for key in ("load_result_count", "lookup_result_count"):
        _require(type(response[key]) is int and 0 <= response[key] <= 1)
    _require(response["load_result_count"] == response["lookup_result_count"])
    _walk(response, output=True)
    if response["request_sha256"] is not None:
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"})
    _walk(response, output=True)
    return response


def _failure(reason, digest=None, count=0):
    try:
        return _seal(_response("EXECUTION_FAILED", [reason], digest, count))
    except Exception:  # noqa: BLE001 -- persistent export faults expose no payload or hashes.
        result = _response("EXECUTION_FAILED", [reason], count=count)
        _walk(result, output=True)
        return result


def _evaluate(request):
    try:
        snapshot = _snapshot(request)
        _keys(snapshot, "evaluation polar section")
        _require(type(snapshot["evaluation"]) is str)
    except Exception:  # noqa: BLE001 -- bounded exact builtins before any copy/hash hooks.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    if snapshot["evaluation"] != EVALUATION:
        return _seal(_response("SOLVER_UNSUPPORTED", ["UNSUPPORTED_EVALUATION"]))
    try:
        _preflight(snapshot)
    except Exception:  # noqa: BLE001 -- all static inputs precede velocity and child calls.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    digest, count = None, 0
    try:
        digest = sha256_record(snapshot)
        velocity = _velocity(snapshot["section"])
        section = {key: deepcopy(value) for key, value in snapshot["section"].items()
                   if key not in ("imposed_axial_velocity_m_s", "imposed_tangential_velocity_m_s",
                                  "psi_rad", "tip_radius_m")}
        section.update(axial_velocity_m_s=velocity["axial_velocity_m_s"],
                       tangential_velocity_m_s=velocity["tangential_velocity_m_s"])
        child_request = {"evaluation": _V133_CATALOG["evaluation"],
                         "polar": deepcopy(snapshot["polar"]), "section": section}
        _walk(child_request)
        _keys(section, _LOAD_SECTION_KEYS)
        _query_kinematics(section)
    except Exception:  # noqa: BLE001 -- no partial velocity or request on arithmetic failure.
        return _failure("SECTION_RESIDUAL_EXECUTION_FAILED", digest)
    try:
        actual = _load.evaluate_section_load(deepcopy(child_request))
        retained = _snapshot(actual, child=True)
        _guard_load(retained, child_request)
        count = 1
    except Exception:  # noqa: BLE001 -- all unexpected child statuses/shapes are atomic failures.
        return _failure("LOAD_BOUNDARY_FAILED", digest)
    try:
        ran = retained["outputs"]["load_state"] == "COMPUTED"
        closure, residual = _closure(snapshot["section"], velocity, retained) if ran else (None, None)
        response = _response("COMPUTED_EXPERIMENTAL", [], digest, count)
        response["outputs"] = {
            "kinematics": velocity, "actual_load_request": child_request, "actual_load_result": retained,
            "residual_state": "COMPUTED" if ran else "NOT_RUN_OUT_OF_POLAR_DOMAIN",
            "closure": closure, "residual_m2_s": residual,
        }
        response["output_units"] = _output_units(ran)
        response["diagnostics_complete"] = True
        return _seal(response)
    except Exception:  # noqa: BLE001 -- retain accepted count, clear all payload on closure/export failure.
        return _failure("SECTION_RESIDUAL_EXECUTION_FAILED", digest, count)


def section_residual_catalog():
    """Return fresh local metadata without an evaluator call or source access."""
    result = {
        **_response("RESEARCH_ONLY", []),
        "required_fields": ["evaluation", "polar", "section"],
        "input_units": {
            "evaluation": "label", "polar": deepcopy(_V133_CATALOG["input_units"]["polar"]),
            "section": {
                "imposed_axial_velocity_m_s": "m/s", "imposed_tangential_velocity_m_s": "m/s",
                "psi_rad": "rad", "tip_radius_m": "m", "chord_m": "m", "radius_m": "m",
                "density_kg_m3": "kg/m^3", "dynamic_viscosity_pa_s": "Pa*s",
                "speed_of_sound_m_s": "m/s", "pitch_rad": "rad", "blade_count": "1",
            },
        },
        "output_field_units": _output_units(),
        "request_contract": {
            "json": "exact bounded builtin JSON; exact evaluation/polar/section root; native request hashed",
            "polar": "exact accepted V132; all tables preflighted before velocity",
            "section": "Ua>=0, Ut>0, R>r>0; positive normal properties; pitch in [0,pi/2]; B int 1..64",
            "branch": (
                "atan2(Ua,Ut)<psi<pi/2 after static preflight; derived Wa,Wt,va,vt strictly "
                "positive normal"
            ),
        },
        "formulas": {
            "velocity": "U=hypot(Ua,Ut); Wa=.5Ua+.5U*sin(psi); Wt=.5Ut+.5U*cos(psi); va=Wa-Ua; vt=Ut-Wt",
            "wake": "lambda_w=(r/R)*(Wa/Wt); f=(B/2)*(1-r/R)/lambda_w; F=(2/pi)*acos(exp(-f))",
            "circulation": "Gamma=vt*(4*pi*r/B)*F*hypot(1,4*lambda_w*R/(pi*B*r)); Gamma_lift=.5*W*c*Cl",
            "residual": "Gamma-Gamma_lift in m^2/s; no Cd/Cl; drag retained in V133 loads",
            "arithmetic": (
                "checked normal-or-zero intermediates; nonzero underflow refused; rounded "
                "opposite contributions may cancel"
            ),
            "F_policy": "require 0<exp(-f)<1 and 0<F<1; no clamping, asymptote or hidden limit policy",
            "reference": "Drela QPROP original page 5, equations 17-32; no derivatives or root solver",
        },
        "boundary_contract": {
            "guard": (
                "fresh V133 catalog exact against frozen; independent full root/query/loads; "
                "accepted pure nested V132 guard reused"
            ),
            "count": (
                "both counts 0 until full child guarded, then 1 including OOD; not attempts or "
                "attestation"
            ),
            "failure": (
                "LOAD_BOUNDARY_FAILED count 0; subsequent closure/export failure count 1; empty "
                "payload"
            ),
            "ood": (
                "COMPUTED_EXPERIMENTAL with full child and velocities; closure/residual null; "
                "NOT_RUN_OUT_OF_POLAR_DOMAIN"
            ),
        },
        "status_matrix": {
            "RESEARCH_ONLY": "catalog only, counts zero, no hashes",
            "MODEL_INAPPLICABLE": "invalid input/static branch; counts zero, no hashes",
            "SOLVER_UNSUPPORTED": "exact bounded root with different string; counts zero, no hashes",
            "COMPUTED_EXPERIMENTAL": "one fully guarded V133 child; residual computed or retained OOD",
            "EXECUTION_FAILED": "sanitized arithmetic/export/boundary failure; no payload",
        },
        "hash_contract": {
            "request": (
                "SHA256 full original native snapshot; sorted compact UTF8 JSON; "
                "ensure_ascii=False, allow_nan=False"
            ),
            "evaluation": (
                "SHA256 full response excluding only evaluation_sha256; not authenticity or "
                "attestation"
            ),
            "exceptions": (
                "ordinary Exception sanitized; BaseException propagates; persistent hashing "
                "failure clears both hashes"
            ),
        },
    }
    _walk(result, output=True)
    return result
