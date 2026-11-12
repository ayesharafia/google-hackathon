"""Private V140 solve boundary; independent stable residual reconstruction."""

import math
import sys
from copy import deepcopy

from . import section_load as _load
from . import stable_section_residual as _res
from .provenance import sha256_record
from .section_residual import _guard_load  # Reuse ONLY actual V133 admission.
from .stable_section_residual import _exact, _keys
from .stable_section_residual import _walk as _native_walk

EVALUATION = "stable_section_solve_experimental"
SCHEMA_VERSION = "stable_section_solve_v1"
_POLICY = {"id": "stable_deficit_binary64_v1", "f_min": 2**-20, "f_max": 512}
_JSON = {"max_nodes_including_keys": 65536, "max_depth": 18,
         "max_container_items": 256, "max_string_characters": 2000,
         "max_integer_bits": 1023, "root_depth": 1, "max_serialized_bytes": 2097152}
_LIMITS = {"input_json": _JSON,
           "output_json": {**_JSON, "max_nodes_including_keys": 4194304,
                           "max_depth": 36, "max_serialized_bytes": 134217728},
           "core_work": {"residual_calls_max": 32, "load_calls_max": 32, "lookup_calls_max": 32}}
_CHILD_LIMITS = {**_JSON, "max_nodes_including_keys": 131072,
                 "max_depth": 28, "max_serialized_bytes": 4194304}


def _require(condition):
    if not condition:
        raise ValueError("Invalid stable solve boundary")


def _walk(value, *, output=False, child=False):
    budget = _CHILD_LIMITS if child else _LIMITS["output_json" if output else "input_json"]
    _native_walk(value, limits=budget)


def _snapshot(value, **options):
    _walk(value, **options)
    result = deepcopy(value)
    _walk(result, **options)
    _exact(result, value)
    return result


# Freeze exact top shape, metadata, policy, units and residual resource limits.
_RESIDUAL_CATALOG = _snapshot(_res.stable_section_residual_catalog(), child=True)
_CHILD_KEYS = frozenset(_RESIDUAL_CATALOG) - frozenset((
    "required_fields", "input_units", "output_field_units", "request_contract",
    "formulas", "boundary_contract", "status_matrix", "hash_contract"))
_V133_EVALUATION = "section_load_experimental"
_LIMITS["residual_input_json"] = deepcopy(_RESIDUAL_CATALOG["limits"]["input_json"])
_LIMITS["residual_output_json"] = deepcopy(_RESIDUAL_CATALOG["limits"]["output_json"])


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


def _velocity(section):
    """Independent request reconstruction; no residual producer math helper."""
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


def _reconstruct(section, velocity, load_result):
    """Reconstruct all stable math from request and admitted actual V133 fields."""
    r, tip, blades = (float(section[key]) for key in ("radius_m", "tip_radius_m", "blade_count"))
    ratio = _quotient(r, tip)
    _require(0 < ratio < 1)
    gap = _sum(1.0, -ratio)
    _require(gap > 0)
    wake = _product(ratio, _quotient(velocity["axial_velocity_m_s"],
                                     velocity["tangential_velocity_m_s"]))
    _require(wake > 0)
    f = _quotient(_product(_product(blades, 0.5), gap), wake)
    _require(_POLICY["f_min"] <= f <= _POLICY["f_max"])
    exponential = _checked(math.exp(-f))
    _require(0 < exponential < 1)
    deficit = _product(_quotient(2.0, math.pi), _checked(math.asin(exponential)))
    _require(0 < deficit < 1)
    rounded = _sum(1.0, -deficit)
    _require(0 < rounded <= 1)
    argument = _quotient(_product(_product(4.0, wake), tip),
                         _product(_product(math.pi, blades), r))
    _require(argument > 0)
    geometry = _checked(math.hypot(1.0, argument))
    scale = _quotient(_product(_product(4.0, math.pi), r), blades)
    prefactor = _product(_product(velocity["induced_tangential_velocity_m_s"], scale), geometry)
    _require(prefactor > 0)
    correction = _product(prefactor, deficit)
    _require(correction > 0)
    gamma = _sum(prefactor, -correction)
    _require(gamma > 0)
    raw_bound = prefactor * (math.ldexp(1.0, -math.floor(f)) if f >= 1 else 1.0)
    bound = math.nextafter(raw_bound, math.inf)
    # Separate schema exception for ONLY tip_rounding_effect_bound_m2_s, m^2/s.
    _require(type(bound) is float and math.isfinite(bound) and bound > 0)
    speed = load_result["outputs"]["kinematics"]["relative_speed_m_s"]
    cl = float(load_result["outputs"]["actual_lookup_result"]["outputs"]["cl"])
    lift = _product(_product(_product(0.5, speed), float(section["chord_m"])), cl)
    closure = {"radius_ratio": ratio, "tip_gap": gap, "local_wake_lambda": wake,
               "geometry_argument": argument, "geometry_factor": geometry, "circulation_scale_m": scale,
               "gamma_lift_m2_s": lift, "gamma_induced_m2_s": gamma}
    factor = {"policy_id": _POLICY["id"], "f_domain_min": _POLICY["f_min"],
              "f_domain_max": _POLICY["f_max"], "f": f, "exp_minus_f": exponential,
              "deficit": deficit, "log_deficit": _checked(math.log(deficit)), "factor_rounded": rounded,
              "representation_state": ("ROUNDED_ONE_WITH_POSITIVE_DEFICIT" if rounded == 1.0
                                       else "INTERIOR_SCALAR"),
              "prefactor_m2_s": prefactor, "correction_m2_s": correction,
              "correction_rounds_away": gamma == prefactor,
              "tip_rounding_effect_bound_m2_s": bound}
    return closure, factor, _sum(gamma, -lift)


def _guard_residual(actual, request):
    """Full native exact child guard; evaluator/closure/representation never its oracle."""
    _walk(actual, child=True)
    _native_walk(request, limits=_LIMITS["residual_input_json"])
    _keys(request, "evaluation numerical_policy polar section")
    _exact(request["evaluation"], _RESIDUAL_CATALOG["evaluation"])
    _exact(request["numerical_policy"], _POLICY)
    _section_preflight(request["section"], request["polar"])
    catalog = _snapshot(_res.stable_section_residual_catalog(), child=True)
    _exact(catalog, _RESIDUAL_CATALOG)
    _require(type(actual) is dict and actual.keys() == _CHILD_KEYS)
    velocity = _velocity(request["section"])
    # The producer refuses this domain BEFORE V133, including an otherwise OOD query.
    ratio = _quotient(float(request["section"]["radius_m"]), float(request["section"]["tip_radius_m"]))
    _require(0 < ratio < 1)
    wake = _product(ratio, _quotient(velocity["axial_velocity_m_s"], velocity["tangential_velocity_m_s"]))
    f = _quotient(_product(_product(float(request["section"]["blade_count"]), 0.5),
                                      _sum(1.0, -ratio)), wake)
    _require(_POLICY["f_min"] <= f <= _POLICY["f_max"])
    section = {key: deepcopy(value) for key, value in request["section"].items()
               if key not in ("imposed_axial_velocity_m_s", "imposed_tangential_velocity_m_s",
                              "psi_rad", "tip_radius_m")}
    section.update(axial_velocity_m_s=velocity["axial_velocity_m_s"],
                   tangential_velocity_m_s=velocity["tangential_velocity_m_s"])
    load_request = {"evaluation": _V133_EVALUATION, "polar": deepcopy(request["polar"]), "section": section}
    _walk(load_request)
    output = actual["outputs"]
    _keys(output, "kinematics actual_load_request actual_load_result residual_state "
                  "closure factor_representation residual_m2_s")
    _exact(output["actual_load_request"], load_request)
    _guard_load(output["actual_load_result"], load_request)
    ran = output["actual_load_result"]["outputs"]["load_state"] == "COMPUTED"
    closure, factor, residual = (_reconstruct(request["section"], velocity, output["actual_load_result"])
                                 if ran else (None, None, None))
    units = deepcopy(catalog["output_field_units"])
    if not ran:
        units["closure"] = units["factor_representation"] = units["residual_m2_s"] = "not_applicable"
        nested = units["actual_load_result"]["outputs"]
        nested["actual_lookup_result"]["outputs"] = {}
        nested["loads"] = "not_applicable"
    expected = {key: deepcopy(catalog[key]) for key in _CHILD_KEYS}
    expected.update(status="COMPUTED_EXPERIMENTAL", reasons=[], load_result_count=1, lookup_result_count=1,
                    diagnostics_complete=True, request_sha256=sha256_record(request), output_units=units,
                    outputs={"kinematics": velocity, "actual_load_request": load_request,
                             "actual_load_result": output["actual_load_result"],
                             "residual_state": "COMPUTED" if ran else "NOT_RUN_OUT_OF_POLAR_DOMAIN",
                             "closure": closure, "factor_representation": factor, "residual_m2_s": residual})
    expected["evaluation_sha256"] = sha256_record({
        key: value for key, value in expected.items() if key != "evaluation_sha256"})
    _exact(actual, expected)


_SECTION_KEYS = ("imposed_axial_velocity_m_s imposed_tangential_velocity_m_s psi_rad "
                 "tip_radius_m chord_m radius_m density_kg_m3 dynamic_viscosity_pa_s "
                 "speed_of_sound_m_s pitch_rad blade_count")


def _positive(value, *, zero=False):
    _require(type(value) in (int, float))
    number = _checked(float(value))
    _require(number >= 0 if zero else number > 0)
    return number


def _section_preflight(section, polar):
    """Independent static section checks; only accepted polar preflight is reused."""
    _keys(section, _SECTION_KEYS)
    for key in _SECTION_KEYS.split():
        if key == "blade_count":
            _require(type(section[key]) is int and 1 <= section[key] <= 64)
        else:
            _positive(section[key], zero=key in ("imposed_axial_velocity_m_s", "pitch_rad"))
    _require(section["pitch_rad"] <= math.pi / 2)
    _require(section["tip_radius_m"] > section["radius_m"])
    _load._polar._preflight({"polar": polar, "query": {
        "alpha_rad": 0, "reynolds_number": 1, "mach_number": 0}})
    _require(math.atan2(float(section["imposed_axial_velocity_m_s"]),
                        float(section["imposed_tangential_velocity_m_s"]))
             < float(section["psi_rad"]) < math.pi / 2)


def _actual_request(template, psi):
    request = deepcopy(template)
    request["section"]["psi_rad"] = psi
    _native_walk(request, limits=_LIMITS["residual_input_json"])
    return request


def _preflight(request):
    _keys(request, "evaluation numerical_policy residual_template solve")
    _require(type(request["evaluation"]) is str)
    _exact(request["numerical_policy"], _POLICY)
    template, solve = request["residual_template"], request["solve"]
    _keys(template, "evaluation numerical_policy polar section")
    _exact(template["evaluation"], _RESIDUAL_CATALOG["evaluation"])
    _exact(template["numerical_policy"], _POLICY)
    _keys(template["section"], " ".join(key for key in _SECTION_KEYS.split() if key != "psi_rad"))
    _keys(solve, "psi_lower_rad psi_upper_rad angle_tolerance_rad residual_tolerance_m2_s max_evaluations")
    for key in ("psi_lower_rad", "psi_upper_rad", "angle_tolerance_rad", "residual_tolerance_m2_s"):
        _positive(solve[key])
    _require(type(solve["max_evaluations"]) is int and 2 <= solve["max_evaluations"] <= 32)
    lower, upper = solve["psi_lower_rad"], solve["psi_upper_rad"]
    _require(lower < upper and float(lower) < float(upper))
    endpoints = [_actual_request(template, psi) for psi in (lower, upper)]
    for endpoint in endpoints:
        _section_preflight(endpoint["section"], endpoint["polar"])
    return endpoints


def _residual(rows, index):
    return rows[index]["result"]["outputs"]["residual_m2_s"]


def _opposite(left, right):
    return left < 0 < right or right < 0 < left


def _bracket(rows, lower, upper):
    width = _sum(float(rows[upper]["psi_rad"]), -float(rows[lower]["psi_rad"]))
    _require(width >= 0)
    return {"lower_evaluation_index": lower, "upper_evaluation_index": upper, "angle_width_rad": width}


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
        middle = evaluate(_actual_request(endpoints[0], midpoint))
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


_LIMITATIONS = [
    "Private experimental bisection of actual guarded stable residuals; no physical validation.",
    "Convergence requires BOTH width and residual criteria; no root error bound or continuity proof.",
    "No tolerance loosening, hidden retry, extrapolation, API, UI or rotor integration.",
    "Counts are fully guarded children including OOD; policy refusals are boundary failures.",
    "Failed child payloads are never retained; only earlier fully guarded rows may survive failure.",
    *_RESIDUAL_CATALOG["limitations"]]


def _response(status, reasons, digest=None, count=0):
    return {"evaluation": EVALUATION, "schema_version": SCHEMA_VERSION,
            "numerical_policy": deepcopy(_POLICY), "status": status, "reasons": list(reasons),
            "outputs": {}, "output_units": {}, "residual_result_count": count,
            "load_result_count": count, "lookup_result_count": count, "diagnostics_complete": False,
            "physical_validation": "NOT_ESTABLISHED", "numerical_qualification": "NOT_ESTABLISHED",
            "runtime_identity": "NOT_ESTABLISHED", "aircraft_status": None, "feasibility": None,
            "evidence_level": "unverified", "source_classification": "UNVERIFIED_CALLER_ASSERTION",
            "mach_interval_status": "UNVERIFIED_CALLER_APPLICABILITY_ONLY",
            "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
            "source_urls": list(_RESIDUAL_CATALOG["source_urls"]),
            "request_sha256": digest, "evaluation_sha256": None}


def _output_units(rows, bracket, solution):
    return {"evaluations": [{"psi_rad": "rad", "request_sha256": "sha256",
                             "result": {"outputs": deepcopy(row["result"]["output_units"])}}
                            for row in rows],
            "solve_state": "label",
            "final_bracket": ({"lower_evaluation_index": "index", "upper_evaluation_index": "index",
                               "angle_width_rad": "rad"} if bracket is not None else "not_applicable"),
            "solution": ({"evaluation_index": "index", "psi_rad": "rad", "residual_m2_s": "m^2/s"}
                         if solution is not None else "not_applicable")}


def _check_export(response):
    _exact(response["numerical_policy"], _POLICY)
    counts = [response[key] for key in ("residual_result_count", "load_result_count", "lookup_result_count")]
    _require(all(type(count) is int and 0 <= count <= 32 for count in counts))
    _require(counts[0] == counts[1] == counts[2])
    output = response["outputs"]
    if not output:
        _exact(response["output_units"], {})
        return
    _keys(output, "evaluations solve_state final_bracket solution")
    rows, bracket, solution = output["evaluations"], output["final_bracket"], output["solution"]
    _require(type(rows) is list and len(rows) == counts[0])
    for index, row in enumerate(rows):
        _keys(row, "psi_rad request_sha256 result")
        _positive(row["psi_rad"])
        _require(all(previous["psi_rad"] != row["psi_rad"] for previous in rows[:index]))
        _walk(row["result"], child=True)
        _require(row["result"].keys() == _CHILD_KEYS)
        _exact(row["request_sha256"], row["result"]["request_sha256"])
        _exact(row["result"]["load_result_count"], 1)
        _exact(row["result"]["lookup_result_count"], 1)
    _exact(response["output_units"], _output_units(rows, bracket, solution))
    state = output["solve_state"]
    _require(type(state) is str and state in (
        "CONVERGED", "NOT_BRACKETED", "NOT_RUN_OUT_OF_POLAR_DOMAIN",
        "EVALUATION_BUDGET_EXHAUSTED", "FLOAT_STAGNATION", "EXECUTION_FAILED"))
    if state == "EXECUTION_FAILED":
        _require(response["status"] == "EXECUTION_FAILED" and bracket is None and solution is None)
        _exact(response["diagnostics_complete"], False)
    else:
        _require(response["status"] == "COMPUTED_EXPERIMENTAL")
        _exact(response["diagnostics_complete"], True)
    if bracket is not None:
        _keys(bracket, "lower_evaluation_index upper_evaluation_index angle_width_rad")
        lo, hi = bracket["lower_evaluation_index"], bracket["upper_evaluation_index"]
        _require(type(lo) is int and type(hi) is int and 0 <= lo < len(rows) and 0 <= hi < len(rows))
        _require(_residual(rows, lo) is not None and _residual(rows, hi) is not None)
        _exact(bracket, _bracket(rows, lo, hi))
    if solution is not None:
        _keys(solution, "evaluation_index psi_rad residual_m2_s")
        index = solution["evaluation_index"]
        _require(type(index) is int and 0 <= index < len(rows) and state == "CONVERGED")
        _require(bracket is not None and index in (bracket["lower_evaluation_index"], bracket["upper_evaluation_index"]))
        _exact(solution, _solution(rows, index))
    _require((solution is not None) == (state == "CONVERGED"))


def _seal(response):
    _walk(response, output=True)
    _check_export(response)
    if response["request_sha256"] is not None:
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"})
    _walk(response, output=True)
    return response


def _failure(reason, digest=None, rows=None):
    rows = [] if rows is None else rows
    try:
        response = _response("EXECUTION_FAILED", [reason], digest, len(rows))
        response["outputs"] = {"evaluations": rows, "solve_state": "EXECUTION_FAILED",
                               "final_bracket": None, "solution": None}
        response["output_units"] = _output_units(rows, None, None)
        return _seal(response)
    except Exception:  # noqa: BLE001 -- persistent export/hash failure drops all payload and hashes.
        response = _response("EXECUTION_FAILED", [reason], count=len(rows))
        _walk(response, output=True)
        return response


class _ResidualBoundaryFailed(Exception):
    """Internal sanitized boundary stop; contains no malformed child payload."""


def evaluate_stable_section_solve(request):
    """Deterministic bisection with 2..32 explicit-budget actual guarded children."""
    try:
        snapshot = _snapshot(request)
        _keys(snapshot, "evaluation numerical_policy residual_template solve")
        _require(type(snapshot["evaluation"]) is str)
    except Exception:  # noqa: BLE001 -- native bounds precede copy, hash and every model call.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    if snapshot["evaluation"] != EVALUATION:
        return _seal(_response("SOLVER_UNSUPPORTED", ["UNSUPPORTED_EVALUATION"]))
    try:
        endpoints = _preflight(snapshot)
    except Exception:  # noqa: BLE001 -- both endpoints fully statically preflighted before calls.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    digest, rows = None, []

    def evaluate(actual_request):
        try:
            _require(len(rows) < snapshot["solve"]["max_evaluations"])
            psi = actual_request["section"]["psi_rad"]
            _require(all(row["psi_rad"] != psi for row in rows))
            request_hash = sha256_record(actual_request)
            actual = _res.evaluate_stable_section_residual(deepcopy(actual_request))
            retained = _snapshot(actual, child=True)
            _guard_residual(retained, actual_request)
        except Exception:  # noqa: BLE001 -- noncomputed/refused/forged children never count.
            raise _ResidualBoundaryFailed from None
        rows.append({"psi_rad": psi, "request_sha256": request_hash, "result": retained})
        return len(rows) - 1

    try:
        digest = sha256_record(snapshot)
        state, bracket, solution = _bisect(rows, evaluate, endpoints, snapshot["solve"])
        response = _response("COMPUTED_EXPERIMENTAL", [], digest, len(rows))
        response["outputs"] = {"evaluations": rows, "solve_state": state,
                               "final_bracket": bracket, "solution": solution}
        response["output_units"] = _output_units(rows, bracket, solution)
        response["diagnostics_complete"] = True
        return _seal(response)
    except _ResidualBoundaryFailed:
        return _failure("RESIDUAL_BOUNDARY_FAILED", digest, rows)
    except Exception:  # noqa: BLE001 -- prior guarded trace only; no partial bracket/solution.
        return _failure("STABLE_SECTION_SOLVE_EXECUTION_FAILED", digest, rows)


def stable_section_solve_catalog():
    """Fresh exact solve contract metadata, without evaluator calls or source access."""
    template_units = deepcopy(_RESIDUAL_CATALOG["input_units"])
    del template_units["section"]["psi_rad"]
    result = {
        **_response("RESEARCH_ONLY", []),
        "required_fields": ["evaluation", "numerical_policy", "residual_template", "solve"],
        "input_units": {
            "evaluation": "label", "numerical_policy": {"id": "label", "f_min": "1", "f_max": "1"},
            "residual_template": template_units,
            "solve": {"psi_lower_rad": "rad", "psi_upper_rad": "rad", "angle_tolerance_rad": "rad",
                      "residual_tolerance_m2_s": "m^2/s", "max_evaluations": "1"}},
        "output_field_units": {
            "evaluations": {"psi_rad": "rad", "request_sha256": "sha256",
                            "result": {"outputs": deepcopy(_RESIDUAL_CATALOG["output_field_units"])}},
            "solve_state": "label",
            "final_bracket": {"lower_evaluation_index": "index", "upper_evaluation_index": "index",
                              "angle_width_rad": "rad"},
            "solution": {"evaluation_index": "index", "psi_rad": "rad", "residual_m2_s": "m^2/s"}},
        "request_contract": {
            "json": "Exact bounded builtin JSON before copy/hash/calls; no defaults or foreign hooks.",
            "policy": "Both root and template exact frozen policy; id str, f_min float 2**-20, f_max int 512.",
            "template": "Exact stable residual evaluation/numerical_policy/polar/section; psi_rad MUST be absent.",
            "solve": "Exact five fields; positive normal builtin int/float angles/tolerances; exact int budget 2..32.",
            "branch": "Native and float lower<upper; atan2(Ua,Ut)<lower<upper<pi/2; both static endpoints before calls.",
            "native": "Endpoints keep original native numbers; actual midpoints are checked binary64 floats."},
        "calculations": {
            "midpoint": "Checked fsum(lo,.5*fsum(hi,-lo)); strict interior; no repeated actual psi calls.",
            "bracket": "Compare opposite signs without product; no extrapolation or hidden retry.",
            "convergence": "BOTH bracket width<=angle_tolerance AND best endpoint abs(residual)<=residual_tolerance.",
            "selection": "Minimum endpoint absolute residual; ties use earlier evaluation index.",
            "zero": "After actual endpoint calls, exact binary64 zero collapses bracket to that index; not mathematical-root proof.",
            "scope": "No continuity, root error, physical validation or numerical qualification claim."},
        "boundary_contract": {
            "guard": "Full frozen residual shape/metadata/policy/units/counts/hash; independently reconstructed stable math from actual guarded V133.",
            "oracle": "No residual evaluator/representation/closure/numerical helper used by guard; native boundary utilities shared.",
            "counts": "Exact int equal residual/load/lookup counts = fully guarded rows 0..32, including OOD; not attempts.",
            "traces": "Ordered unique actual psi rows, full child result and native request digest; all nested output units retained.",
            "failure": "Any other child status including numerical-policy refusal => RESIDUAL_BOUNDARY_FAILED; bad payload/count discarded.",
            "retention": "EXECUTION_FAILED retains only previous guarded rows; solve_state EXECUTION_FAILED, null bracket/solution and not_applicable units.",
            "export_failure": "Persistent export/hash fault clears outputs/units/both hashes while preserving accepted count.",
            "ood": "Stop immediately; retain OOD row and prior valid bracket, or null bracket before both valid endpoints.",
            "limits": "At most32 nested actual results; streaming byte caps plus nodes/depth enforced before copies and on exports.",
            "bound_exception": "Only nested tip_rounding_effect_bound_m2_s permits positive finite subnormal; unit m^2/s; independently checked."},
        "status_matrix": {
            "RESEARCH_ONLY": "Catalog only, zero counts, null hashes.",
            "MODEL_INAPPLICABLE": "INVALID_REQUEST; zero counts/calls, empty payload and null hashes.",
            "SOLVER_UNSUPPORTED": "UNSUPPORTED_EVALUATION; zero counts/calls, empty payload and null hashes.",
            "COMPUTED_EXPERIMENTAL": "CONVERGED, NOT_BRACKETED, NOT_RUN_OUT_OF_POLAR_DOMAIN, EVALUATION_BUDGET_EXHAUSTED or FLOAT_STAGNATION.",
            "EXECUTION_FAILED": "Sanitized failure with prior guarded rows only, unless persistent export/hash failure clears payload."},
        "hash_contract": {
            "request": "SHA256 full native validated request including both policies; sorted compact UTF8 ensure_ascii=False allow_nan=False.",
            "evaluation": "SHA256 full response including policy/units/counts/nulls excluding only evaluation_sha256; no authenticity claim.",
            "exceptions": "Ordinary Exception sanitized; BaseException propagates; persistent export/hash fault clears payload/hashes, keeps count."}}
    _walk(result, output=True)
    return result
