"""Bounded experimental bisection of actual, guarded V134 residuals only."""

import math
import sys
from copy import deepcopy

from . import section_residual as _res
from .provenance import sha256_record

EVALUATION = "section_solve_experimental"
SCHEMA_VERSION = "section_solve_v1"


def _require(condition):
    if not condition:
        raise ValueError("Invalid section solve boundary")


def _walk(value, *, output=False, child=False, request=False):
    """Bound exact native JSON before copy, hashing, or other traversal."""
    remaining = 2097152 if output else (65536 if child else 32768)
    max_depth = 32 if output else (24 if child else (10 if request else 12))

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


def _snapshot(value, **options):
    _walk(value, **options)
    result = deepcopy(value)
    _walk(result, **options)
    _exact(result, value)
    return result


def _keys(value, names):
    _require(type(value) is dict and set(value) == set(names.split()))


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


def _positive(value):
    _require(type(value) in (int, float))
    number = _checked(float(value))
    _require(number > 0)
    return number


def _actual_request(template, psi):
    result = deepcopy(template)
    result["section"]["psi_rad"] = psi
    _walk(result, request=True)
    return result


def _preflight(request):
    _keys(request, "evaluation residual_template solve")
    _require(type(request["evaluation"]) is str)
    template, solve = request["residual_template"], request["solve"]
    _keys(template, "evaluation polar section")
    _exact(template["evaluation"], _V134_CATALOG["evaluation"])
    _keys(template["section"], (
        "imposed_axial_velocity_m_s imposed_tangential_velocity_m_s tip_radius_m "
        "chord_m radius_m density_kg_m3 dynamic_viscosity_pa_s speed_of_sound_m_s "
        "pitch_rad blade_count"))
    _keys(solve, (
        "psi_lower_rad psi_upper_rad angle_tolerance_rad residual_tolerance_m2_s max_evaluations"))
    for key in ("psi_lower_rad", "psi_upper_rad", "angle_tolerance_rad", "residual_tolerance_m2_s"):
        _positive(solve[key])
    _require(type(solve["max_evaluations"]) is int and 2 <= solve["max_evaluations"] <= 16)
    lower, upper = solve["psi_lower_rad"], solve["psi_upper_rad"]
    _require(lower < upper and float(lower) < float(upper))
    endpoints = [_actual_request(template, psi) for psi in (lower, upper)]
    for endpoint in endpoints:
        _res._preflight(endpoint)
    return endpoints


# Freeze metadata only. Catalog access never invokes a model.
_V134_CATALOG = _snapshot(_res.section_residual_catalog(), child=True)
_V133_EVALUATION = _res._V133_CATALOG["evaluation"]
_CHILD_KEYS = frozenset(_V134_CATALOG) - frozenset((
    "required_fields", "input_units", "output_field_units", "request_contract",
    "formulas", "status_matrix", "hash_contract", "boundary_contract",
))
_JSON = {
    "max_nodes_including_keys": 32768, "max_depth": 12, "max_container_items": 256,
    "max_string_characters": 2000, "max_integer_bits": 1023, "root_depth": 1,
}
_LIMITS = {
    "input_json": _JSON,
    "output_json": {**_JSON, "max_nodes_including_keys": 2097152, "max_depth": 32},
    "residual_input_json": deepcopy(_V134_CATALOG["limits"]["input_json"]),
    "residual_output_json": deepcopy(_V134_CATALOG["limits"]["output_json"]),
    "core_work": {
        "residual_calls_max": 16, "load_calls_max": 16, "lookup_calls_max": 16,
        "aggregate_table_rows_max": 16 * 8 * 256,
    },
}
_LIMITATIONS = [
    "Experimental bounded local bisection of actual V134 residuals only.",
    "Numerical convergence requires residual tolerance and bracket width; no root error bound.",
    "Exact binary64 residual zero is not proof of an exact mathematical root.",
    "Sampled sign change does not establish continuity or continuous polar coverage.",
    "No interpolation of residuals, constant-Cl iteration, extrapolation or recovery from OOD.",
    "No blanket Ning convergence guarantee, feasibility claim or physical validation.",
    "No API, UI, dataset, publication, nonlinear rotor solver or rotor integration.",
    "Counts mean fully guarded accepted children including OOD, never attempts or attestation.",
    "Hashes bind native JSON; they do not authenticate data, runtime identity or physical claims.",
    "Unexpected V134 failures are RESIDUAL_BOUNDARY_FAILED without trusting their causes.",
    *_V134_CATALOG["limitations"],
]


def _velocity(section):
    """Independent V134 velocity reconstruction in its checked operation order."""
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


def _closure(section, velocity, load_result):
    """Independent checked reconstruction; never call V134 closure helpers."""
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


def _guard_residual(actual, request):
    """Pure complete V134 response guard; only the accepted nested guard is reused."""
    _walk(actual, child=True)
    _walk(request, request=True)
    catalog = _snapshot(_res.section_residual_catalog(), child=True)
    _exact(catalog, _V134_CATALOG)
    _require(type(actual) is dict and actual.keys() == _CHILD_KEYS)
    velocity = _velocity(request["section"])
    section = {key: deepcopy(value) for key, value in request["section"].items()
               if key not in ("imposed_axial_velocity_m_s", "imposed_tangential_velocity_m_s",
                              "psi_rad", "tip_radius_m")}
    section.update(axial_velocity_m_s=velocity["axial_velocity_m_s"],
                   tangential_velocity_m_s=velocity["tangential_velocity_m_s"])
    load_request = {
        "evaluation": _V133_EVALUATION,
        "polar": deepcopy(request["polar"]), "section": section,
    }
    _walk(load_request, request=True)
    output = actual["outputs"]
    _keys(output, "kinematics actual_load_request actual_load_result residual_state closure residual_m2_s")
    _exact(output["actual_load_request"], load_request)
    _res._guard_load(output["actual_load_result"], load_request)
    ran = output["actual_load_result"]["outputs"]["load_state"] == "COMPUTED"
    closure, residual = (_closure(request["section"], velocity, output["actual_load_result"])
                         if ran else (None, None))
    units = deepcopy(catalog["output_field_units"])
    if not ran:
        units["closure"] = units["residual_m2_s"] = "not_applicable"
        nested = units["actual_load_result"]["outputs"]
        nested["actual_lookup_result"]["outputs"] = {}
        nested["loads"] = "not_applicable"
    expected = {key: deepcopy(catalog[key]) for key in _CHILD_KEYS}
    expected.update(
        status="COMPUTED_EXPERIMENTAL", reasons=[], load_result_count=1, lookup_result_count=1,
        diagnostics_complete=True, request_sha256=sha256_record(request), output_units=units,
        outputs={"kinematics": velocity, "actual_load_request": load_request,
                 "actual_load_result": deepcopy(output["actual_load_result"]),
                 "residual_state": "COMPUTED" if ran else "NOT_RUN_OUT_OF_POLAR_DOMAIN",
                 "closure": closure, "residual_m2_s": residual},
    )
    expected["evaluation_sha256"] = sha256_record({
        key: value for key, value in expected.items() if key != "evaluation_sha256"})
    _exact(actual, expected)


def _response(status, reasons, digest=None, count=0):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "reasons": list(reasons), "outputs": {}, "output_units": {},
        "residual_result_count": count, "load_result_count": count, "lookup_result_count": count,
        "diagnostics_complete": False, "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "evidence_level": "unverified",
        "source_classification": "UNVERIFIED_CALLER_ASSERTION",
        "mach_interval_status": "UNVERIFIED_CALLER_APPLICABILITY_ONLY",
        "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
        "source_urls": deepcopy(_V134_CATALOG["source_urls"]),
        "request_sha256": digest, "evaluation_sha256": None,
    }


def _seal(response):
    counts = [response[key] for key in (
        "residual_result_count", "load_result_count", "lookup_result_count")]
    _require(all(type(count) is int and 0 <= count <= 16 for count in counts))
    _require(counts[0] == counts[1] == counts[2])
    _walk(response, output=True)
    if response["request_sha256"] is not None:
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"})
    _walk(response, output=True)
    return response


def _failure(reason, digest=None, count=0):
    try:
        return _seal(_response("EXECUTION_FAILED", [reason], digest, count))
    except Exception:  # noqa: BLE001 -- persistent export faults retain no payload or hashes.
        result = _response("EXECUTION_FAILED", [reason], count=count)
        _walk(result, output=True)
        return result


class _ResidualBoundaryFailed(Exception):
    """Internal sanitized stop; carries no child failure diagnosis."""


def _residual(rows, index):
    return rows[index]["result"]["outputs"]["residual_m2_s"]


def _opposite(left, right):
    return left < 0 < right or right < 0 < left


def _bracket(rows, lower, upper):
    width = _sum(float(rows[upper]["psi_rad"]), -float(rows[lower]["psi_rad"]))
    _require(width >= 0)
    return {"lower_evaluation_index": lower, "upper_evaluation_index": upper,
            "angle_width_rad": width}


def _solution(rows, index):
    return {"evaluation_index": index, "psi_rad": rows[index]["psi_rad"],
            "residual_m2_s": _residual(rows, index)}


def _bisect(rows, evaluate, endpoints, solve):
    lower = evaluate(endpoints[0])
    if _residual(rows, lower) is None:
        return "NOT_RUN_OUT_OF_POLAR_DOMAIN", None, None
    upper = evaluate(endpoints[1])
    if _residual(rows, upper) is None:
        return "NOT_RUN_OUT_OF_POLAR_DOMAIN", None, None
    # Both actual endpoint calls precede exact-zero and sign-change decisions.
    for index in (lower, upper):
        if _residual(rows, index) == 0:
            return "CONVERGED", _bracket(rows, index, index), _solution(rows, index)
    if not _opposite(_residual(rows, lower), _residual(rows, upper)):
        return "NOT_BRACKETED", _bracket(rows, lower, upper), None
    while True:
        bracket = _bracket(rows, lower, upper)
        best = min((lower, upper), key=lambda index: (abs(_residual(rows, index)), index))
        if (bracket["angle_width_rad"] <= solve["angle_tolerance_rad"]
                and abs(_residual(rows, best)) <= solve["residual_tolerance_m2_s"]):
            return "CONVERGED", bracket, _solution(rows, best)
        if len(rows) >= solve["max_evaluations"]:
            return "EVALUATION_BUDGET_EXHAUSTED", bracket, None
        lo, hi = float(rows[lower]["psi_rad"]), float(rows[upper]["psi_rad"])
        midpoint = _sum(lo, _product(0.5, bracket["angle_width_rad"]))
        if not lo < midpoint < hi:
            return "FLOAT_STAGNATION", bracket, None
        request = _actual_request(endpoints[0], midpoint)
        middle = evaluate(request)
        value = _residual(rows, middle)
        if value is None:
            return "NOT_RUN_OUT_OF_POLAR_DOMAIN", bracket, None
        if value == 0:
            return "CONVERGED", _bracket(rows, middle, middle), _solution(rows, middle)
        if _opposite(_residual(rows, lower), value):
            upper = middle
        else:
            _require(_opposite(value, _residual(rows, upper)))
            lower = middle


def _output_units(rows):
    return {
        "evaluations": [{"psi_rad": "rad", "request_sha256": "sha256",
                         "result": {"outputs": deepcopy(row["result"]["output_units"])}}
                        for row in rows],
        "solve_state": "label",
        "final_bracket": {"lower_evaluation_index": "index", "upper_evaluation_index": "index",
                          "angle_width_rad": "rad"},
        "solution": {"evaluation_index": "index", "psi_rad": "rad", "residual_m2_s": "m^2/s"},
    }


def evaluate_section_solve(request):
    """Bisect a caller interval with at most sixteen actual, fully guarded V134 calls."""
    try:
        snapshot = _snapshot(request)
        _keys(snapshot, "evaluation residual_template solve")
        _require(type(snapshot["evaluation"]) is str)
    except Exception:  # noqa: BLE001 -- exact bounded builtins precede copying and hashing.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    if snapshot["evaluation"] != EVALUATION:
        return _seal(_response("SOLVER_UNSUPPORTED", ["UNSUPPORTED_EVALUATION"]))
    try:
        endpoints = _preflight(snapshot)
    except Exception:  # noqa: BLE001 -- both complete endpoint requests preflight before models.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    digest, count, rows = None, 0, []

    def evaluate(actual_request):
        nonlocal count
        try:
            _require(len(rows) < snapshot["solve"]["max_evaluations"])
            psi = actual_request["section"]["psi_rad"]
            _require(all(row["psi_rad"] != psi for row in rows))
            request_hash = sha256_record(actual_request)
            actual = _res.evaluate_section_residual(deepcopy(actual_request))
            retained = _snapshot(actual, child=True)
            _guard_residual(retained, actual_request)
        except Exception:  # noqa: BLE001 -- no unguarded payload or claimed child numeric cause.
            raise _ResidualBoundaryFailed from None
        count += 1
        rows.append({"psi_rad": psi, "request_sha256": request_hash, "result": retained})
        return len(rows) - 1

    try:
        digest = sha256_record(snapshot)
        state, bracket, solution = _bisect(rows, evaluate, endpoints, snapshot["solve"])
        response = _response("COMPUTED_EXPERIMENTAL", [], digest, count)
        response["outputs"] = {"evaluations": rows, "solve_state": state,
                               "final_bracket": bracket, "solution": solution}
        units = _output_units(rows)
        if bracket is None:
            units["final_bracket"] = "not_applicable"
        if solution is None:
            units["solution"] = "not_applicable"
        response["output_units"] = units
        response["diagnostics_complete"] = True
        return _seal(response)
    except _ResidualBoundaryFailed:
        return _failure("RESIDUAL_BOUNDARY_FAILED", digest, count)
    except Exception:  # noqa: BLE001 -- atomic arithmetic/export failure, accepted counts retained.
        return _failure("SECTION_SOLVE_EXECUTION_FAILED", digest, count)


def section_solve_catalog():
    """Return fresh bounded metadata; never evaluate a residual or fetch a source."""
    template_units = deepcopy(_V134_CATALOG["input_units"])
    del template_units["section"]["psi_rad"]
    result = {
        **_response("RESEARCH_ONLY", []),
        "required_fields": ["evaluation", "residual_template", "solve"],
        "input_units": {
            "evaluation": "label", "residual_template": template_units,
            "solve": {"psi_lower_rad": "rad", "psi_upper_rad": "rad",
                      "angle_tolerance_rad": "rad", "residual_tolerance_m2_s": "m^2/s",
                      "max_evaluations": "1"},
        },
        "output_field_units": {
            "evaluations": {"psi_rad": "rad", "request_sha256": "sha256",
                            "result": {"outputs": deepcopy(_V134_CATALOG["output_field_units"])}},
            "solve_state": "label",
            "final_bracket": {"lower_evaluation_index": "index", "upper_evaluation_index": "index",
                              "angle_width_rad": "rad"},
            "solution": {"evaluation_index": "index", "psi_rad": "rad", "residual_m2_s": "m^2/s"},
        },
        "request_contract": {
            "template": "exact V134 evaluation/polar/section, psi_rad MUST be absent; no overrides",
            "solve": "exact five fields; positive normal builtin int/float angles and tolerances",
            "branch": "native and float lower<upper; atan2(Ua,Ut)<lower<upper<pi/2",
            "budget": "max_evaluations exact builtin int 2..16; both endpoints preflight before calls",
        },
        "calculations": {
            "midpoint": "checked lo + .5*(hi-lo); strict interior required before each actual call",
            "bracket": "opposite residual signs compared without multiplication; no extrapolation",
            "convergence": "width<=angle_tolerance and endpoint abs(residual)<=residual_tolerance",
            "selection": "smallest endpoint absolute residual, ties earlier evaluation index",
            "zero": "exact binary64 zero collapses bracket to that evaluation index, width zero",
        },
        "boundary_contract": {
            "guard": "fresh frozen V134 metadata; independent velocity/closure; pure _res._guard_load",
            "counts": "all three equal fully guarded results, including OOD, 0..16; not attempts",
            "failure": "unexpected V134 status/shape/arithmetic: RESIDUAL_BOUNDARY_FAILED; empty payload",
            "ood": "stop immediately; retain admitted rows and prior valid bracket, or null before both",
            "traces": "ordered unique actual psi rows; full child responses; bracket/solution index owners",
            "output_budget": "2Mi nodes covers 16*65536 child nodes plus bounded metadata and unit traces",
        },
        "status_matrix": {
            "RESEARCH_ONLY": "catalog only, zero counts, no hashes",
            "MODEL_INAPPLICABLE": "invalid bounded input/static preflight; zero counts, no hashes",
            "SOLVER_UNSUPPORTED": "bounded exact root with unsupported string; zero counts, no hashes",
            "COMPUTED_EXPERIMENTAL": "CONVERGED, NOT_BRACKETED, NOT_RUN_OUT_OF_POLAR_DOMAIN, "
                                     "EVALUATION_BUDGET_EXHAUSTED or FLOAT_STAGNATION",
            "EXECUTION_FAILED": "sanitized atomic failure; earlier accepted counts only, no payload",
        },
        "hash_contract": deepcopy(_V134_CATALOG["hash_contract"]),
    }
    _walk(result, output=True)
    return result
