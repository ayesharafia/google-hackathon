"""Bounded experimental prescribed-annulus integration of actual V135 solves."""

import math
import sys
from copy import deepcopy

from . import section_solve as _solve
from .provenance import sha256_record

EVALUATION = "polar_rotor_experimental"
SCHEMA_VERSION = "polar_rotor_v1"


def _require(condition):
    if not condition:
        raise ValueError("Invalid polar rotor boundary")


def _walk(value, *, output=False, child=False):
    remaining = 33554432 if output else (2097152 if child else 262144)
    max_depth = 40 if output else (32 if child else 16)

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
    copied = deepcopy(value)
    _walk(copied, **options)
    _exact(copied, value)
    return copied


def _keys(value, names):
    _require(type(value) is dict and set(value) == set(names.split()))


def _checked(value):
    _require(type(value) is float and math.isfinite(value))
    _require(value == 0 or abs(value) >= sys.float_info.min)
    return value


def _positive(value):
    _require(type(value) in (int, float))
    number = _checked(float(value))
    _require(number > 0)
    return number


def _product(left, right):
    value = _checked(left * right)
    _require(value != 0 or left == 0 or right == 0)
    return value


def _sum(left, right):
    value = _checked(math.fsum((left, right)))
    _require(value != 0 or left == -right)
    return value


# Metadata snapshots are model-free and contain no caller polar data.
_V135_CATALOG = _snapshot(_solve.section_solve_catalog(), child=True)
_CHILD_KEYS = frozenset(_V135_CATALOG) - frozenset((
    "required_fields", "input_units", "output_field_units", "request_contract",
    "calculations", "status_matrix", "hash_contract", "boundary_contract",
))
_JSON = {"max_nodes_including_keys": 262144, "max_depth": 16,
         "max_container_items": 256, "max_string_characters": 2000,
         "max_integer_bits": 1023, "root_depth": 1}
_LIMITS = {
    "input_json": _JSON,
    "output_json": {**_JSON, "max_nodes_including_keys": 33554432, "max_depth": 40},
    "section_solve_input_json": deepcopy(_V135_CATALOG["limits"]["input_json"]),
    "section_solve_output_json": deepcopy(_V135_CATALOG["limits"]["output_json"]),
    "core_work": {"annuli_max": 8, "section_solve_calls_max": 8,
                  "residual_calls_max": 128, "load_calls_max": 128,
                  "lookup_calls_max": 128, "aggregate_table_rows_max": 128 * 8 * 256},
}
_LIMITATIONS = [
    "Experimental nonlinear isolated axial rotor with prescribed finite annuli only.",
    "Hub cutoff is explicit; no hub-loss model or radial/rotor interaction model.",
    "Midpoint quadrature has no discretization error estimate or numerical qualification.",
    "Signed thrust, torque and shaft power do not establish motor or DC/regen feasibility.",
    "No API, UI, dataset fetch, mission, motor, publication or rotor-data validation.",
    "Geometry and polar sources are unverified caller assertions; no redistribution claim.",
    "Counts admit only fully guarded whole section solves, including nonconverged/OOD solves.",
    "Hashes bind native JSON, not runtime identity, provenance authenticity or physical truth.",
    *_V135_CATALOG["limitations"],
]


def _preflight(request):
    _keys(request, "evaluation rotor annuli")
    rotor, annuli = request["rotor"], request["annuli"]
    _keys(rotor, "tip_radius_m hub_radius_m blade_count angular_speed_rad_s "
          "imposed_axial_velocity_m_s density_kg_m3 dynamic_viscosity_pa_s "
          "speed_of_sound_m_s geometry_source uncertainty_status")
    tip, hub = _positive(rotor["tip_radius_m"]), _positive(rotor["hub_radius_m"])
    _require(rotor["hub_radius_m"] < rotor["tip_radius_m"] and hub < tip)
    _require(type(rotor["blade_count"]) is int and 1 <= rotor["blade_count"] <= 64)
    omega = _positive(rotor["angular_speed_rad_s"])
    axial = rotor["imposed_axial_velocity_m_s"]
    _require(type(axial) in (int, float) and axial >= 0)
    _checked(float(axial))
    for key in ("density_kg_m3", "dynamic_viscosity_pa_s", "speed_of_sound_m_s"):
        _positive(rotor[key])
    for key in ("geometry_source", "uncertainty_status"):
        _require(type(rotor[key]) is str and 0 < len(rotor[key]) <= 2000
                 and bool(rotor[key].strip()))
    _require(type(annuli) is list and 1 <= len(annuli) <= 8)
    requests, geometry = [], []
    previous = rotor["hub_radius_m"]
    for annulus in annuli:
        _keys(annulus, "radial_inner_m radial_outer_m chord_m pitch_rad polar solve")
        inner, outer = annulus["radial_inner_m"], annulus["radial_outer_m"]
        _positive(inner)
        _positive(outer)
        _exact(inner, previous)
        _require(inner < outer and float(inner) < float(outer))
        width = _sum(float(outer), -float(inner))
        _require(width > 0)
        midpoint = _sum(float(inner), _product(0.5, width))
        _require(float(inner) < midpoint < float(outer))
        tangential = _product(omega, midpoint)
        _require(tangential > 0)
        _positive(annulus["chord_m"])
        pitch = annulus["pitch_rad"]
        _require(type(pitch) in (int, float) and 0 <= pitch <= math.pi / 2)
        _checked(float(pitch))
        section = {key: deepcopy(rotor[key]) for key in (
            "imposed_axial_velocity_m_s", "tip_radius_m", "density_kg_m3",
            "dynamic_viscosity_pa_s", "speed_of_sound_m_s", "blade_count")}
        section.update(imposed_tangential_velocity_m_s=tangential, radius_m=midpoint,
                       chord_m=deepcopy(annulus["chord_m"]), pitch_rad=deepcopy(pitch))
        actual = {"evaluation": _V135_CATALOG["evaluation"],
                  "residual_template": {"evaluation": _solve._V134_CATALOG["evaluation"],
                                        "polar": deepcopy(annulus["polar"]), "section": section},
                  "solve": deepcopy(annulus["solve"])}
        _solve._walk(actual)
        _solve._preflight(actual)
        requests.append(actual)
        geometry.append((midpoint, width))
        previous = outer
    _exact(previous, rotor["tip_radius_m"])
    _require(sum(actual["solve"]["max_evaluations"] for actual in requests) <= 128)
    return requests, geometry


def _guard_solve(actual, request):
    """Replay retained actual residuals independently of V135's bisection helpers."""
    _walk(actual, child=True)
    _exact(_snapshot(_solve.section_solve_catalog(), child=True), _V135_CATALOG)
    _require(type(actual) is dict and actual.keys() == _CHILD_KEYS)
    return _replay_solve(actual, request)


def _replay_solve(actual, request):
    """Consume exactly the retained calls demanded by the independent state engine."""
    output = actual["outputs"]
    _keys(output, "evaluations solve_state final_bracket solution")
    rows, solve = output["evaluations"], request["solve"]
    _require(type(rows) is list and 1 <= len(rows) <= solve["max_evaluations"] <= 16)
    # Guard every retained row before interpreting any solver claim or termination.
    seen = []
    for row in rows:
        _keys(row, "psi_rad request_sha256 result")
        _positive(row["psi_rad"])
        _require(all(row["psi_rad"] != psi for psi in seen))
        seen.append(row["psi_rad"])
        residual_request = deepcopy(request["residual_template"])
        residual_request["section"]["psi_rad"] = row["psi_rad"]
        _exact(row["request_sha256"], sha256_record(residual_request))
        _solve._guard_residual(row["result"], residual_request)
    consumed = 0

    def consume(psi):
        nonlocal consumed
        _require(consumed < len(rows))
        _exact(rows[consumed]["psi_rad"], psi)
        index = consumed
        consumed += 1
        return index

    def residual(index):
        return rows[index]["result"]["outputs"]["residual_m2_s"]

    def opposite(left, right):
        return left < 0 < right or right < 0 < left

    def bracket(lower, upper):
        width = _sum(float(rows[upper]["psi_rad"]), -float(rows[lower]["psi_rad"]))
        _require(width >= 0)
        return {"lower_evaluation_index": lower, "upper_evaluation_index": upper,
                "angle_width_rad": width}

    def solution(index):
        return {"evaluation_index": index, "psi_rad": rows[index]["psi_rad"],
                "residual_m2_s": residual(index)}

    def run():
        lower = consume(solve["psi_lower_rad"])
        if residual(lower) is None:
            return "NOT_RUN_OUT_OF_POLAR_DOMAIN", None, None
        upper = consume(solve["psi_upper_rad"])
        if residual(upper) is None:
            return "NOT_RUN_OUT_OF_POLAR_DOMAIN", None, None
        for index in (lower, upper):
            if residual(index) == 0:
                return "CONVERGED", bracket(index, index), solution(index)
        if not opposite(residual(lower), residual(upper)):
            return "NOT_BRACKETED", bracket(lower, upper), None
        while True:
            current = bracket(lower, upper)
            best = min((lower, upper), key=lambda index: (abs(residual(index)), index))
            if (current["angle_width_rad"] <= solve["angle_tolerance_rad"]
                    and abs(residual(best)) <= solve["residual_tolerance_m2_s"]):
                return "CONVERGED", current, solution(best)
            if consumed >= solve["max_evaluations"]:
                return "EVALUATION_BUDGET_EXHAUSTED", current, None
            lo, hi = float(rows[lower]["psi_rad"]), float(rows[upper]["psi_rad"])
            midpoint = _sum(lo, _product(0.5, current["angle_width_rad"]))
            if not lo < midpoint < hi:
                return "FLOAT_STAGNATION", current, None
            middle = consume(midpoint)
            value = residual(middle)
            if value is None:
                return "NOT_RUN_OUT_OF_POLAR_DOMAIN", current, None
            if value == 0:
                return "CONVERGED", bracket(middle, middle), solution(middle)
            if opposite(residual(lower), value):
                upper = middle
            else:
                _require(opposite(value, residual(upper)))
                lower = middle

    state, final_bracket, selected = run()
    _require(consumed == len(rows))
    units = {
        "evaluations": [{"psi_rad": "rad", "request_sha256": "sha256",
                         "result": {"outputs": deepcopy(row["result"]["output_units"])}}
                        for row in rows],
        "solve_state": "label",
        "final_bracket": {"lower_evaluation_index": "index", "upper_evaluation_index": "index",
                          "angle_width_rad": "rad"} if final_bracket is not None else "not_applicable",
        "solution": {"evaluation_index": "index", "psi_rad": "rad", "residual_m2_s": "m^2/s"}
        if selected is not None else "not_applicable",
    }
    expected = {key: deepcopy(_V135_CATALOG[key]) for key in _CHILD_KEYS}
    expected.update(
        status="COMPUTED_EXPERIMENTAL", reasons=[], diagnostics_complete=True,
        residual_result_count=len(rows), load_result_count=len(rows), lookup_result_count=len(rows),
        request_sha256=sha256_record(request), output_units=units,
        outputs={"evaluations": deepcopy(rows), "solve_state": state,
                 "final_bracket": final_bracket, "solution": selected},
    )
    expected["evaluation_sha256"] = sha256_record({
        key: value for key, value in expected.items() if key != "evaluation_sha256"})
    _exact(actual, expected)


def _response(status, reasons, digest=None, sections=0, residuals=0):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "reasons": list(reasons), "outputs": {}, "output_units": {},
        "section_solve_result_count": sections, "residual_result_count": residuals,
        "load_result_count": residuals, "lookup_result_count": residuals,
        "diagnostics_complete": False, "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "evidence_level": "unverified",
        "source_classification": "UNVERIFIED_CALLER_ASSERTION",
        "mach_interval_status": "UNVERIFIED_CALLER_APPLICABILITY_ONLY",
        "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
        "source_urls": deepcopy(_V135_CATALOG["source_urls"]),
        "request_sha256": digest, "evaluation_sha256": None,
    }


def _seal(response):
    sections = response["section_solve_result_count"]
    counts = [response[key] for key in (
        "residual_result_count", "load_result_count", "lookup_result_count")]
    _require(type(sections) is int and 0 <= sections <= 8)
    _require(all(type(count) is int and sections <= count <= 16 * sections for count in counts))
    _require(counts[0] == counts[1] == counts[2])
    _walk(response, output=True)
    if response["request_sha256"] is not None:
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"})
    _walk(response, output=True)
    return response


def _failure(reason, digest=None, sections=0, residuals=0):
    try:
        return _seal(_response("EXECUTION_FAILED", [reason], digest, sections, residuals))
    except Exception:  # noqa: BLE001 -- persistent export failure clears payload and both hashes.
        result = _response("EXECUTION_FAILED", [reason], sections=sections, residuals=residuals)
        _walk(result, output=True)
        return result


def _integrate(rows, omega):
    contributions = []
    for row in rows:
        output = row["solve_result"]["outputs"]
        selected = output["solution"]["evaluation_index"]
        loads = output["evaluations"][selected]["result"]["outputs"]["actual_load_result"][
            "outputs"]["loads"]
        thrust_density = loads["thrust_density_n_m"]
        torque_density = loads["torque_density_nm_m"]
        width = row["radial_width_m"]
        contributions.append({
            "annulus_index": row["annulus_index"], "selected_evaluation_index": selected,
            "thrust_density_n_m": thrust_density, "torque_density_nm_m": torque_density,
            "radial_width_m": width, "thrust_n": _product(thrust_density, width),
            "torque_nm": _product(torque_density, width),
        })
    thrust = _checked(math.fsum(row["thrust_n"] for row in contributions))
    torque = _checked(math.fsum(row["torque_nm"] for row in contributions))
    return {"integration_method": "MIDPOINT_PRESCRIBED_ANNULI", "contributions": contributions,
            "totals": {"thrust_n": thrust, "torque_nm": torque,
                       "shaft_power_w": _product(omega, torque)}}


_CONTRIBUTION_UNITS = {
    "annulus_index": "index", "selected_evaluation_index": "index",
    "thrust_density_n_m": "N/m", "torque_density_nm_m": "N*m/m",
    "radial_width_m": "m", "thrust_n": "N", "torque_nm": "N*m",
}
_INTEGRATED_UNITS = {
    "integration_method": "label", "contributions": _CONTRIBUTION_UNITS,
    "totals": {"thrust_n": "N", "torque_nm": "N*m", "shaft_power_w": "W"},
}


def _output_units(rows, integrated):
    return {
        "rotor_state": "label",
        "annuli": [{"annulus_index": "index", "radial_inner_m": "m", "radial_outer_m": "m",
                    "midpoint_radius_m": "m", "radial_width_m": "m",
                    "solve_result": {"outputs": deepcopy(row["solve_result"]["output_units"])}}
                   for row in rows],
        "integrated": {**deepcopy(_INTEGRATED_UNITS),
                       "contributions": [deepcopy(_CONTRIBUTION_UNITS) for _ in rows]}
        if integrated is not None else "not_applicable",
    }


def evaluate_polar_rotor(request):
    """Run one actual guarded V135 solve per annulus; integrate only all-converged traces."""
    try:
        snapshot = _snapshot(request)
        _keys(snapshot, "evaluation rotor annuli")
        _require(type(snapshot["evaluation"]) is str)
    except Exception:  # noqa: BLE001 -- bound exact builtins before copies, hashes or calls.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    if snapshot["evaluation"] != EVALUATION:
        return _seal(_response("SOLVER_UNSUPPORTED", ["UNSUPPORTED_EVALUATION"]))
    try:
        requests, geometry = _preflight(snapshot)
    except Exception:  # noqa: BLE001 -- all full endpoint preflights precede actual model work.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    digest, sections, residuals, rows = None, 0, 0, []
    try:
        digest = sha256_record(snapshot)
        for index, actual_request in enumerate(requests):
            try:
                actual = _solve.evaluate_section_solve(deepcopy(actual_request))
                retained = _snapshot(actual, child=True)
                _guard_solve(retained, actual_request)
            except Exception:  # noqa: BLE001 -- current child contributes no accepted counts.
                return _failure("SOLVE_BOUNDARY_FAILED", digest, sections, residuals)
            sections += 1
            residuals += retained["residual_result_count"]
            annulus = snapshot["annuli"][index]
            midpoint, width = geometry[index]
            rows.append({"annulus_index": index,
                         "radial_inner_m": deepcopy(annulus["radial_inner_m"]),
                         "radial_outer_m": deepcopy(annulus["radial_outer_m"]),
                         "midpoint_radius_m": midpoint, "radial_width_m": width,
                         "solve_result": retained})
        converged = all(row["solve_result"]["outputs"]["solve_state"] == "CONVERGED" for row in rows)
        integrated = _integrate(rows, float(snapshot["rotor"]["angular_speed_rad_s"])) if converged else None
        response = _response("COMPUTED_EXPERIMENTAL", [], digest, sections, residuals)
        response["outputs"] = {
            "rotor_state": "COMPUTED" if converged else "NOT_RUN_SECTION_NOT_CONVERGED",
            "annuli": rows, "integrated": integrated,
        }
        response["output_units"] = _output_units(rows, integrated)
        response["diagnostics_complete"] = True
        return _seal(response)
    except Exception:  # noqa: BLE001 -- atomic arithmetic/export failure keeps accepted counts only.
        return _failure("POLAR_ROTOR_EXECUTION_FAILED", digest, sections, residuals)


def polar_rotor_catalog():
    """Return fresh bounded metadata without invoking any model or fetching any data."""
    result = {
        **_response("RESEARCH_ONLY", []),
        "required_fields": ["evaluation", "rotor", "annuli"],
        "input_units": {
            "evaluation": "label",
            "rotor": {"tip_radius_m": "m", "hub_radius_m": "m", "blade_count": "1",
                      "angular_speed_rad_s": "rad/s", "imposed_axial_velocity_m_s": "m/s",
                      "density_kg_m3": "kg/m^3", "dynamic_viscosity_pa_s": "Pa*s",
                      "speed_of_sound_m_s": "m/s", "geometry_source": "text",
                      "uncertainty_status": "text"},
            "annuli": {"radial_inner_m": "m", "radial_outer_m": "m", "chord_m": "m",
                       "pitch_rad": "rad",
                       "polar": deepcopy(_V135_CATALOG["input_units"]["residual_template"]["polar"]),
                       "solve": deepcopy(_V135_CATALOG["input_units"]["solve"])},
        },
        "output_field_units": {
            "rotor_state": "label",
            "annuli": {"annulus_index": "index", "radial_inner_m": "m", "radial_outer_m": "m",
                       "midpoint_radius_m": "m", "radial_width_m": "m",
                       "solve_result": {"outputs": deepcopy(_V135_CATALOG["output_field_units"])}},
            "integrated": deepcopy(_INTEGRATED_UNITS),
        },
        "request_contract": {
            "schema": "exact evaluation/rotor/annuli; exact rotor and annulus fields; no defaults",
            "annuli": "1..8 contiguous full-native-exact boundaries from positive hub to tip",
            "geometry": "native and float inner<outer; checked dr and strict interior midpoint",
            "numbers": "builtin int/float, finite normal or zero; positive radii/chord/omega/properties",
            "branch": "V>=0, blade_count exact int 1..64, pitch in [0,pi/2]; V135 branch inherited",
            "sources": "nonblank unverified geometry_source/uncertainty_status <=2000 characters",
            "polar": "exact V132 polar contract; all applicability and source assertions unverified",
            "preflight": "all derived actual V135 requests, both endpoints, before any model call",
        },
        "calculations": {
            "geometry": "dr=fsum(outer,-inner); r=fsum(inner,.5*dr); Ut=omega*r; Ua=V",
            "integration": "selected actual all-blade V133 dT/dr and dQ/dr times dr, no extra blade factor",
            "totals": "math.fsum of ordered contributions; shaft_power_w=omega*total_torque_nm",
            "arithmetic": "checked binary64 finite normal or zero; refuse nonzero product underflow",
            "cancellation": "signed contributions allowed; fsum zero of rounded inputs allowed, "
                            "no physical claim",
            "source": "Drela QPROP equations 64-65; midpoint rule; Omega Q shaft-power denominator in eq. 66",
        },
        "boundary_contract": {
            "guard": "fresh frozen V135 catalog; full pure residual guards and "
                     "independent ordered trace replay",
            "calls": "one actual V135 call per annulus, immediate bounded copy; no model rerun by guard",
            "counts": "fully guarded whole children only, including OOD/nonconverged; never attempts",
            "failure": "SOLVE_BOUNDARY_FAILED clears all payload; counts omit entire current child",
            "nonconverged": "run all annuli; retain full traces; no integrated totals unless all CONVERGED",
            "binding": "native root hash; child request hash binds reconstructed full derived V135 request",
        },
        "status_matrix": {
            "RESEARCH_ONLY": "catalog; zero counts and null hashes",
            "MODEL_INAPPLICABLE": "invalid static request; no calls, zero counts and null hashes",
            "SOLVER_UNSUPPORTED": "bounded exact root with unsupported evaluation string; no calls",
            "COMPUTED_EXPERIMENTAL": "all guarded children; COMPUTED or NOT_RUN_SECTION_NOT_CONVERGED",
            "EXECUTION_FAILED": "atomic empty payload; prior accepted counts; hashes when export succeeds",
        },
        "hash_contract": deepcopy(_V135_CATALOG["hash_contract"]),
    }
    _walk(result, output=True)
    return result
