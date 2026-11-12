"""Private V140 retained-deficit residual; no physical validation or integration."""

import json
import math
import sys
from copy import deepcopy

from . import section_load as _load
from .provenance import sha256_record
from .section_residual import _guard_load  # Accepted guard ONLY for actual V133 scope.

EVALUATION = "stable_section_residual_experimental"
SCHEMA_VERSION = "stable_section_residual_v1"
_POLICY = {"id": "stable_deficit_binary64_v1", "f_min": 2**-20, "f_max": 512}
_JSON = {"max_nodes_including_keys": 32768, "max_depth": 16,
         "max_container_items": 256, "max_string_characters": 2000,
         "max_integer_bits": 1023, "root_depth": 1, "max_serialized_bytes": 1048576}
_LIMITS = {"input_json": _JSON,
           "output_json": {**_JSON, "max_nodes_including_keys": 131072,
                           "max_depth": 28, "max_serialized_bytes": 4194304},
           "core_work": {"load_calls_max": 1, "lookup_calls_max": 1}}
_ENCODER = json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False)
_SECTION_KEYS = ("imposed_axial_velocity_m_s imposed_tangential_velocity_m_s psi_rad "
                 "tip_radius_m chord_m radius_m density_kg_m3 dynamic_viscosity_pa_s "
                 "speed_of_sound_m_s pitch_rad blade_count")


def _require(condition):
    if not condition:
        raise ValueError("Invalid stable section boundary")


def _keys(value, names):
    _require(type(value) is dict and value.keys() == set(names.split()))


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


def _walk(value, *, output=False, limits=None):
    """Bound native data first, then stream bytes before any copy/hash/model call."""
    budget = limits if limits is not None else _LIMITS["output_json" if output else "input_json"]
    remaining = budget["max_nodes_including_keys"]

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        _require(remaining >= 0 and depth <= budget["max_depth"])
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
    size = 0
    for chunk in _ENCODER.iterencode(value):
        size += len(chunk.encode("utf-8", "strict"))
        _require(size <= budget["max_serialized_bytes"])


def _snapshot(value, **options):
    _walk(value, **options)
    result = deepcopy(value)
    _walk(result, **options)
    _exact(result, value)
    return result


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


def _policy(value):
    _exact(value, _POLICY)


def _bound_scalar(value):
    """SOLE subnormal exception: tip_rounding_effect_bound_m2_s, in m^2/s."""
    _require(type(value) is float and math.isfinite(value) and value > 0)
    return value


def _effect_bound(f, prefactor):
    """Outward bound at fixed emitted K,f; underflow exception is confined here."""
    _require(_POLICY["f_min"] <= _checked(f) <= _POLICY["f_max"])
    _require(_checked(prefactor) > 0)
    raw = prefactor * (math.ldexp(1.0, -math.floor(f)) if f >= 1 else 1.0)
    return _bound_scalar(math.nextafter(raw, math.inf))


def _representation(f, prefactor):
    _require(_POLICY["f_min"] <= _checked(f) <= _POLICY["f_max"])
    _require(_checked(prefactor) > 0)
    exponential = _checked(math.exp(-f))
    _require(0 < exponential < 1)
    deficit = _product(_quotient(2.0, math.pi), _checked(math.asin(exponential)))
    _require(0 < deficit < 1)
    factor = _sum(1.0, -deficit)
    _require(0 < factor <= 1)
    correction = _product(prefactor, deficit)
    _require(correction > 0)
    gamma = _sum(prefactor, -correction)
    _require(gamma > 0)
    bound = _effect_bound(f, prefactor)
    return {"policy_id": _POLICY["id"], "f_domain_min": _POLICY["f_min"],
            "f_domain_max": _POLICY["f_max"], "f": f, "exp_minus_f": exponential,
            "deficit": deficit, "log_deficit": _checked(math.log(deficit)),
            "factor_rounded": factor,
            "representation_state": ("ROUNDED_ONE_WITH_POSITIVE_DEFICIT" if factor == 1.0
                                     else "INTERIOR_SCALAR"),
            "prefactor_m2_s": prefactor, "correction_m2_s": correction,
            "correction_rounds_away": gamma == prefactor,
            "tip_rounding_effect_bound_m2_s": bound}, gamma


def _response(status, reasons, digest=None, count=0):
    return {"evaluation": EVALUATION, "schema_version": SCHEMA_VERSION,
            "numerical_policy": deepcopy(_POLICY), "status": status, "reasons": list(reasons),
            "outputs": {}, "output_units": {}, "load_result_count": count,
            "lookup_result_count": count, "diagnostics_complete": False,
            "physical_validation": "NOT_ESTABLISHED", "numerical_qualification": "NOT_ESTABLISHED",
            "runtime_identity": "NOT_ESTABLISHED", "aircraft_status": None, "feasibility": None,
            "evidence_level": "unverified", "source_classification": "UNVERIFIED_CALLER_ASSERTION",
            "mach_interval_status": "UNVERIFIED_CALLER_APPLICABILITY_ONLY",
            "limits": deepcopy(_LIMITS), "limitations": list(_LIMITATIONS),
            "source_urls": list(_SOURCE_URLS), "request_sha256": digest, "evaluation_sha256": None}


_SOURCE_URLS = list(dict.fromkeys(["https://web.mit.edu/drela/Public/web/qprop/qprop_theory.pdf",
                                  *_load.section_load_catalog()["source_urls"]]))
_LIMITATIONS = ["Private experimental positive-induction isolated axial section; caller polars unverified.",
                "No physical validation, numerical qualification, API, UI, rotor or automatic fallback.",
                "Bound fixes emitted K,f; excludes libm, geometry, whole residual error and confidence intervals.",
                "Counts mean fully guarded children including OOD; hashes bind data, not authenticity.",
                "Rounded-one state retains a positive deficit; rounds-away is not loss-history proof."]


def _number(value, *, zero=False):
    _require(type(value) in (int, float))
    number = _checked(float(value))
    _require(number >= 0 if zero else number > 0)
    return number


def _preflight(request):
    """Independent new root/policy/section checks; only polar static checks delegated."""
    _keys(request, "evaluation numerical_policy polar section")
    _require(type(request["evaluation"]) is str)
    _policy(request["numerical_policy"])
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
        "alpha_rad": 0, "reynolds_number": 1, "mach_number": 0}})
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


def _wake(section, velocity):
    ratio = _quotient(float(section["radius_m"]), float(section["tip_radius_m"]))
    _require(0 < ratio < 1)
    gap = _sum(1.0, -ratio)
    _require(gap > 0)
    wake = _product(ratio, _quotient(velocity["axial_velocity_m_s"],
                                     velocity["tangential_velocity_m_s"]))
    _require(wake > 0)
    f = _quotient(_product(_product(float(section["blade_count"]), 0.5), gap), wake)
    _require(f > 0)
    return {"radius_ratio": ratio, "tip_gap": gap, "local_wake_lambda": wake}, f


def _closure(section, velocity, wake_fields, f, load_result):
    """Producer calculation, never an admission oracle for a consumed residual."""
    r, tip, blades = (float(section[key]) for key in ("radius_m", "tip_radius_m", "blade_count"))
    numerator = _product(_product(4.0, wake_fields["local_wake_lambda"]), tip)
    denominator = _product(_product(math.pi, blades), r)
    argument = _quotient(numerator, denominator)
    _require(argument > 0)
    geometry = _checked(math.hypot(1.0, argument))
    scale = _quotient(_product(_product(4.0, math.pi), r), blades)
    prefactor = _product(_product(velocity["induced_tangential_velocity_m_s"], scale), geometry)
    representation, gamma = _representation(f, prefactor)
    speed = load_result["outputs"]["kinematics"]["relative_speed_m_s"]
    cl = float(load_result["outputs"]["actual_lookup_result"]["outputs"]["cl"])
    lift = _product(_product(_product(0.5, speed), float(section["chord_m"])), cl)
    residual = _sum(gamma, -lift)
    return {**wake_fields, "geometry_argument": argument, "geometry_factor": geometry,
            "circulation_scale_m": scale, "gamma_lift_m2_s": lift,
            "gamma_induced_m2_s": gamma}, representation, residual


_V133_CATALOG = _snapshot(_load.section_load_catalog(), output=True)
_VELOCITY_UNITS = {key: ("rad" if key == "psi_rad" else "m/s") for key in ["imposed_axial_velocity_m_s", "imposed_tangential_velocity_m_s", "imposed_speed_m_s", "axial_velocity_m_s", "tangential_velocity_m_s", "induced_axial_velocity_m_s", "induced_tangential_velocity_m_s", "psi_rad"]}
_CLOSURE_UNITS = {"radius_ratio": "1", "tip_gap": "1", "local_wake_lambda": "1",
                  "geometry_argument": "1", "geometry_factor": "1", "circulation_scale_m": "m",
                  "gamma_lift_m2_s": "m^2/s", "gamma_induced_m2_s": "m^2/s"}
_FACTOR_UNITS = {"policy_id": "label", "f_domain_min": "1", "f_domain_max": "1", "f": "1",
                 "exp_minus_f": "1", "deficit": "1", "log_deficit": "1", "factor_rounded": "1",
                 "representation_state": "label", "prefactor_m2_s": "m^2/s",
                 "correction_m2_s": "m^2/s", "correction_rounds_away": "boolean",
                 "tip_rounding_effect_bound_m2_s": "m^2/s"}


def _output_units(ran=True):
    child_units = deepcopy(_V133_CATALOG["output_field_units"])
    if not ran:
        child_units["actual_lookup_result"]["outputs"] = {}
        child_units["loads"] = "not_applicable"
    return {"kinematics": deepcopy(_VELOCITY_UNITS),
            "actual_load_request": deepcopy(_V133_CATALOG["input_units"]),
            "actual_load_result": {"outputs": child_units}, "residual_state": "label",
            "closure": deepcopy(_CLOSURE_UNITS) if ran else "not_applicable",
            "factor_representation": deepcopy(_FACTOR_UNITS) if ran else "not_applicable",
            "residual_m2_s": "m^2/s" if ran else "not_applicable"}


def _check_export(response):
    """Local export schema checks, not an independent child admission oracle."""
    _policy(response["numerical_policy"])
    counts = [response[key] for key in ("load_result_count", "lookup_result_count")]
    _require(all(type(count) is int and 0 <= count <= 1 for count in counts))
    _require(counts[0] == counts[1])
    output = response["outputs"]
    if not output:
        _exact(response["output_units"], {})
        return
    _require(response["status"] == "COMPUTED_EXPERIMENTAL" and counts[0] == 1)
    _keys(output, "kinematics actual_load_request actual_load_result residual_state "
                  "closure factor_representation residual_m2_s")
    _keys(output["kinematics"], " ".join(_VELOCITY_UNITS))
    for value in output["kinematics"].values():
        _checked(value)
    ran = output["residual_state"] == "COMPUTED"
    _require(ran or output["residual_state"] == "NOT_RUN_OUT_OF_POLAR_DOMAIN")
    _exact(response["output_units"], _output_units(ran))
    if not ran:
        _require(output["closure"] is output["factor_representation"] is output["residual_m2_s"] is None)
        return
    closure, factor = output["closure"], output["factor_representation"]
    _keys(closure, " ".join(_CLOSURE_UNITS))
    _keys(factor, " ".join(_FACTOR_UNITS))
    for value in closure.values():
        _checked(value)
    _checked(output["residual_m2_s"])
    _exact(factor["policy_id"], _POLICY["id"])
    _exact(factor["f_domain_min"], _POLICY["f_min"])
    _exact(factor["f_domain_max"], _POLICY["f_max"])
    for key in ("f", "exp_minus_f", "deficit", "log_deficit", "factor_rounded",
                "prefactor_m2_s", "correction_m2_s"):
        _checked(factor[key])
    _require(_POLICY["f_min"] <= factor["f"] <= _POLICY["f_max"])
    _require(0 < factor["exp_minus_f"] < 1 and 0 < factor["deficit"] < 1)
    _require(0 < factor["factor_rounded"] <= 1)
    _require(factor["prefactor_m2_s"] > 0 and factor["correction_m2_s"] > 0)
    _require(closure["gamma_induced_m2_s"] > 0)
    state = ("ROUNDED_ONE_WITH_POSITIVE_DEFICIT" if factor["factor_rounded"] == 1.0
             else "INTERIOR_SCALAR")
    _exact(factor["representation_state"], state)
    _exact(factor["correction_rounds_away"],
           closure["gamma_induced_m2_s"] == factor["prefactor_m2_s"])
    _bound_scalar(factor["tip_rounding_effect_bound_m2_s"])


def _seal(response):
    _walk(response, output=True)
    _check_export(response)
    if response["request_sha256"] is not None:
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"})
    _walk(response, output=True)
    return response


def _failure(reason, digest=None, count=0):
    try:
        return _seal(_response("EXECUTION_FAILED", [reason], digest, count))
    except Exception:  # noqa: BLE001 -- persistent export/hash faults expose no child payload.
        result = _response("EXECUTION_FAILED", [reason], count=count)
        _walk(result, output=True)
        return result


def evaluate_stable_section_residual(request):
    """Evaluate one prescribed psi using at most one actual, fully guarded V133 child."""
    try:
        snapshot = _snapshot(request)
        _keys(snapshot, "evaluation numerical_policy polar section")
        _require(type(snapshot["evaluation"]) is str)
    except Exception:  # noqa: BLE001 -- exact bounded native JSON before copy/hash/calls.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    if snapshot["evaluation"] != EVALUATION:
        return _seal(_response("SOLVER_UNSUPPORTED", ["UNSUPPORTED_EVALUATION"]))
    try:
        _preflight(snapshot)
    except Exception:  # noqa: BLE001 -- every static field/polar checked before model calls.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    digest, count = None, 0
    try:
        digest = sha256_record(snapshot)
        velocity = _velocity(snapshot["section"])
        wake_fields, f = _wake(snapshot["section"], velocity)
        if not _POLICY["f_min"] <= f <= _POLICY["f_max"]:
            return _seal(_response("NUMERICAL_POLICY_REFUSED", ["F_OUTSIDE_NUMERICAL_POLICY"], digest))
        section = {key: deepcopy(value) for key, value in snapshot["section"].items()
                   if key not in ("imposed_axial_velocity_m_s", "imposed_tangential_velocity_m_s",
                                  "psi_rad", "tip_radius_m")}
        section.update(axial_velocity_m_s=velocity["axial_velocity_m_s"],
                       tangential_velocity_m_s=velocity["tangential_velocity_m_s"])
        child_request = {"evaluation": _V133_CATALOG["evaluation"],
                         "polar": deepcopy(snapshot["polar"]), "section": section}
        _walk(child_request)
        _load._walk(child_request)
        _load._preflight(child_request)
    except Exception:  # noqa: BLE001 -- no partial velocity/request on arithmetic/export failure.
        return _failure("STABLE_SECTION_RESIDUAL_EXECUTION_FAILED", digest)
    try:
        actual = _load.evaluate_section_load(deepcopy(child_request))
        retained = _snapshot(actual, output=True)
        _guard_load(retained, child_request)
        count = 1
    except Exception:  # noqa: BLE001 -- malformed child never counted or retained.
        return _failure("LOAD_BOUNDARY_FAILED", digest)
    try:
        ran = retained["outputs"]["load_state"] == "COMPUTED"
        closure, factor, residual = (_closure(snapshot["section"], velocity, wake_fields, f, retained)
                                     if ran else (None, None, None))
        response = _response("COMPUTED_EXPERIMENTAL", [], digest, count)
        response["outputs"] = {
            "kinematics": velocity, "actual_load_request": child_request,
            "actual_load_result": retained,
            "residual_state": "COMPUTED" if ran else "NOT_RUN_OUT_OF_POLAR_DOMAIN",
            "closure": closure, "factor_representation": factor, "residual_m2_s": residual}
        response["output_units"] = _output_units(ran)
        response["diagnostics_complete"] = True
        return _seal(response)
    except Exception:  # noqa: BLE001 -- accepted count survives; all partial payload is removed.
        return _failure("STABLE_SECTION_RESIDUAL_EXECUTION_FAILED", digest, count)


def stable_section_residual_catalog():
    """Fresh policy/schema metadata; no evaluator call, fetching or physical qualification."""
    result = {
        **_response("RESEARCH_ONLY", []),
        "required_fields": ["evaluation", "numerical_policy", "polar", "section"],
        "input_units": {
            "evaluation": "label", "numerical_policy": {"id": "label", "f_min": "1", "f_max": "1"},
            "polar": deepcopy(_V133_CATALOG["input_units"]["polar"]),
            "section": {"imposed_axial_velocity_m_s": "m/s", "imposed_tangential_velocity_m_s": "m/s",
                        "psi_rad": "rad", "tip_radius_m": "m", "chord_m": "m", "radius_m": "m",
                        "density_kg_m3": "kg/m^3", "dynamic_viscosity_pa_s": "Pa*s",
                        "speed_of_sound_m_s": "m/s", "pitch_rad": "rad", "blade_count": "1"}},
        "output_field_units": _output_units(),
        "request_contract": {
            "json": "Exact builtin bounded native JSON; exact keys, no defaults; bounds before copy/hash/calls.",
            "policy": "Exact numerical_policy dictionary; id str, f_min float 2**-20, f_max int 512.",
            "section": "Ua>=0, Ut>0, R>r>0; normal-or-zero binary64, pitch in [0,pi/2], B int 1..64.",
            "branch": "atan2(Ua,Ut)<psi<pi/2; derived Wa,Wt,va,vt positive normal.",
            "polar": "Actual accepted V133/V132 caller polar; every table statically checked.",
            "order": "Static preflight, hash, velocity/wake/f domain, derived V133 preflight, child, guard, closure."},
        "formulas": {
            "velocity": "U=hypot(Ua,Ut); Wa=.5Ua+.5U*sin(psi); Wt=.5Ut+.5U*cos(psi); va=Wa-Ua; vt=Ut-Wt",
            "wake": "ratio=r/R; gap=fsum(1,-ratio); wake=ratio*(Wa/Wt); f=((float(B)*.5)*gap)/wake",
            "factor": "x=exp(-f); deficit=(2/pi)*asin(x); log_deficit=log(deficit); factor_rounded=fsum(1,-deficit)",
            "circulation": "geometry=hypot(1,((4*wake)*R)/((pi*B)*r)); K=(vt*(((4*pi)*r)/B))*geometry",
            "residual": "correction=K*deficit; gamma=fsum(K,-correction); lift=((.5*V133_speed)*chord)*Cl; residual=fsum(gamma,-lift)",
            "bound": "nextafter(K*2**(-floor(f)),+inf) for f>=1, else nextafter(K,+inf); fixed emitted K,f only",
            "arithmetic": "Normal-or-zero checked intermediates; K/correction/gamma/exp/deficit positive normal; no scalar-factor multiplication."},
        "boundary_contract": {
            "guard": "Accepted pure _guard_load reused ONLY for complete actual V133 admission; no new evaluator as guard.",
            "count": "Exact int equal load/lookup counts: zero until full guard passes; one includes OOD.",
            "failure": "LOAD_BOUNDARY_FAILED count0; post-child arithmetic/export count1; sanitized empty payload.",
            "ood": "COMPUTED_EXPERIMENTAL; full child retained; closure/factor_representation/residual null and not_applicable units.",
            "subnormal_exception": {"field": "tip_rounding_effect_bound_m2_s", "unit": "m^2/s",
                                    "schema": "Only this derived field allows positive finite subnormal; separate _bound_scalar guard.",
                                    "arithmetic": "Only outward-bound product may underflow; nextafter(0,+inf) allowed; overflow refused."},
            "state": "ROUNDED_ONE_WITH_POSITIVE_DEFICIT iff rounded factor==1; rounds-away iff gamma==K with retained positive correction."},
        "status_matrix": {
            "RESEARCH_ONLY": "Catalog, zero counts and null hashes.",
            "MODEL_INAPPLICABLE": "INVALID_REQUEST; zero calls/counts, empty payload, null hashes.",
            "SOLVER_UNSUPPORTED": "UNSUPPORTED_EVALUATION; zero calls/counts, empty payload, null hashes.",
            "NUMERICAL_POLICY_REFUSED": "F_OUTSIDE_NUMERICAL_POLICY before child; count0, empty payload; validated request hashed.",
            "COMPUTED_EXPERIMENTAL": "One guarded V133 child; computed residual or retained OOD.",
            "EXECUTION_FAILED": "Sanitized arithmetic/export or LOAD_BOUNDARY_FAILED; empty payload; accepted counts retained."},
        "hash_contract": {
            "request": "SHA256 full native validated request including numerical_policy; sorted compact UTF8 ensure_ascii=False allow_nan=False.",
            "evaluation": "SHA256 full response including policy/units/counts/nulls excluding only evaluation_sha256; no authenticity claim.",
            "exceptions": "Ordinary Exception sanitized; BaseException propagates; persistent export/hash failure clears payload and both hashes."}}
    _walk(result, output=True)
    return result
