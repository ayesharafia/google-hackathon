"""Private V141 composition boundaries; authoring only, acceptance pending."""

import json
import math
import sys
from copy import deepcopy

from . import section_polar as _polar
from . import stable_section_solve as _solve
from .provenance import sha256_record

EVALUATION = "stable_polar_rotor_experimental"
SCHEMA_VERSION = "stable_polar_rotor_v1"
_POLICY = {"id": "stable_deficit_binary64_v1", "f_min": 2**-20, "f_max": 512}
_NATIVE = {"max_container_items": 256, "max_string_characters": 2000,
           "max_integer_bits": 1023, "root_depth": 1}
_INPUT_LIMITS = {**_NATIVE, "max_nodes_including_keys": 262144,
                 "max_depth": 18, "max_serialized_bytes": 8 * 1024**2}
_OUTPUT_LIMITS = {**_NATIVE, "max_nodes_including_keys": 16777216,
                  "max_depth": 40, "max_serialized_bytes": 128 * 1024**2}
_CHILD_LIMITS = {**_NATIVE, "max_nodes_including_keys": 4194304,
                 "max_depth": 36, "max_serialized_bytes": 128 * 1024**2}
_CHILD_BYTES_MAX = 64 * 1024**2
_CHILD_NODES_MAX = 8388608
_ENCODER = json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False)


class _ResourceBudgetExceeded(Exception):
    """Current whole raw child exceeds remaining composition quota; no payload."""


def _require(condition):
    if not condition:
        raise ValueError("Invalid stable rotor native boundary")


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


def _measure_native(value, limits, *, remaining_bytes=None, remaining_nodes=None):
    """Validate native shape, then stream canonical bytes; never fully serialize to count."""
    nodes, max_depth = 0, 0

    def visit(item, depth):
        nonlocal nodes, max_depth
        nodes += 1
        max_depth = max(max_depth, depth)
        # Intrinsic invalidity is a boundary error; a remaining-quota crossing is distinct.
        _require(nodes <= limits["max_nodes_including_keys"] and depth <= limits["max_depth"])
        if remaining_nodes is not None and nodes > remaining_nodes:
            raise _ResourceBudgetExceeded
        kind = type(item)
        if kind is str:
            _require(len(item) <= limits["max_string_characters"])
            item.encode("utf-8", "strict")
        elif kind is int:
            _require(item.bit_length() <= limits["max_integer_bits"])
        elif kind is float:
            _require(math.isfinite(item))
        elif kind is dict:
            _require(len(item) <= limits["max_container_items"])
            for key, nested in item.items():
                _require(type(key) is str)
                visit(key, depth + 1)
                visit(nested, depth + 1)
        elif kind is list:
            _require(len(item) <= limits["max_container_items"])
            for nested in item:
                visit(nested, depth + 1)
        else:
            _require(kind is bool or item is None)

    visit(value, 1)
    size = 0
    for chunk in _ENCODER.iterencode(value):
        size += len(chunk.encode("utf-8", "strict"))
        _require(size <= limits["max_serialized_bytes"])
        if remaining_bytes is not None and size > remaining_bytes:
            raise _ResourceBudgetExceeded
    return {"nodes": nodes, "serialized_bytes": size, "depth": max_depth}


class _ChildQuota:
    """Committed WHOLE child objects only, including their units/metadata/hashes."""

    def __init__(self):
        self.bytes_used = 0
        self.nodes_used = 0

    def measure(self, value):
        return _measure_native(value, _CHILD_LIMITS,
                               remaining_bytes=_CHILD_BYTES_MAX - self.bytes_used,
                               remaining_nodes=_CHILD_NODES_MAX - self.nodes_used)

    def commit(self, measurement):
        # Caller must first finish snapshot comparison and the independent whole-solve guard.
        _require(type(measurement) is dict and measurement.keys() == {"nodes", "serialized_bytes", "depth"})
        _require(all(type(value) is int and value > 0 for value in measurement.values()))
        if (measurement["serialized_bytes"] > _CHILD_BYTES_MAX - self.bytes_used
                or measurement["nodes"] > _CHILD_NODES_MAX - self.nodes_used):
            raise _ResourceBudgetExceeded
        self.bytes_used += measurement["serialized_bytes"]
        self.nodes_used += measurement["nodes"]


def _snapshot_child(raw, quota):
    """Raw admission FIRST; child already allocated/hashed upstream before this call.

    Returns an uncommitted snapshot. Independent guard/count/commit belong to the caller.
    A raw quota refusal invokes NO parent copy/hash/guard on that child.
    """
    measured = quota.measure(raw)
    snapshot = deepcopy(raw)
    copied_measurement = quota.measure(snapshot)
    _exact(copied_measurement, measured)
    _exact(snapshot, raw)
    return snapshot, measured


def _snapshot_native(value, *, output=False):
    limits = _OUTPUT_LIMITS if output else _INPUT_LIMITS
    measured = _measure_native(value, limits)
    snapshot = deepcopy(value)
    _exact(_measure_native(snapshot, limits), measured)
    _exact(snapshot, value)
    return snapshot


_SOLVE_CATALOG = _snapshot_native(_solve.stable_section_solve_catalog())
_exact(_SOLVE_CATALOG["limits"]["output_json"], _CHILD_LIMITS)
_SOLVE_INPUT_LIMITS = deepcopy(_SOLVE_CATALOG["limits"]["input_json"])
_SOLVE_KEYS = frozenset(_SOLVE_CATALOG) - frozenset((
    "required_fields", "input_units", "output_field_units", "request_contract",
    "calculations", "boundary_contract", "status_matrix", "hash_contract"))
_ROTOR_KEYS = ("tip_radius_m hub_radius_m blade_count angular_speed_rad_s "
               "imposed_axial_velocity_m_s density_kg_m3 dynamic_viscosity_pa_s "
               "speed_of_sound_m_s geometry_source uncertainty_status")
_SECTION_KEYS = ("imposed_axial_velocity_m_s imposed_tangential_velocity_m_s tip_radius_m "
                 "chord_m radius_m density_kg_m3 dynamic_viscosity_pa_s speed_of_sound_m_s "
                 "pitch_rad blade_count")


def _keys(value, names):
    _require(type(value) is dict and value.keys() == set(names.split()))


def _checked(value):
    _require(type(value) is float and math.isfinite(value))
    _require(value == 0 or abs(value) >= sys.float_info.min)
    return value


def _positive(value, *, zero=False):
    _require(type(value) in (int, float))
    result = _checked(float(value))
    _require(result >= 0 if zero else result > 0)
    return result


def _product(left, right):
    result = _checked(left * right)
    _require(result != 0 or left == 0 or right == 0)
    return result


def _sum(left, right):
    result = _checked(math.fsum((left, right)))
    _require(result != 0 or left == -right)
    return result


def _residual_request(template, psi):
    request = deepcopy(template)
    request["section"]["psi_rad"] = psi
    _measure_native(request, _SOLVE_CATALOG["limits"]["residual_input_json"])
    return request


def _solve_preflight(request):
    """Independent static child request checks; no V140 solve implementation oracle."""
    _measure_native(request, _SOLVE_INPUT_LIMITS)
    _keys(request, "evaluation numerical_policy residual_template solve")
    _exact(request["evaluation"], "stable_section_solve_experimental")
    _exact(request["numerical_policy"], _POLICY)
    template, solve = request["residual_template"], request["solve"]
    _keys(template, "evaluation numerical_policy polar section")
    _exact(template["evaluation"], "stable_section_residual_experimental")
    _exact(template["numerical_policy"], _POLICY)
    section = template["section"]
    _keys(section, _SECTION_KEYS)
    for key in _SECTION_KEYS.split():
        if key == "blade_count":
            _require(type(section[key]) is int and 1 <= section[key] <= 64)
        else:
            _positive(section[key], zero=key in ("imposed_axial_velocity_m_s", "pitch_rad"))
    _require(section["pitch_rad"] <= math.pi / 2 and section["tip_radius_m"] > section["radius_m"])
    _polar._preflight({"polar": template["polar"], "query": {
        "alpha_rad": 0, "reynolds_number": 1, "mach_number": 0}})
    _keys(solve, "psi_lower_rad psi_upper_rad angle_tolerance_rad residual_tolerance_m2_s max_evaluations")
    for key in ("psi_lower_rad", "psi_upper_rad", "angle_tolerance_rad", "residual_tolerance_m2_s"):
        _positive(solve[key])
    _require(type(solve["max_evaluations"]) is int and 2 <= solve["max_evaluations"] <= 32)
    lo, hi = solve["psi_lower_rad"], solve["psi_upper_rad"]
    _require(lo < hi and float(lo) < float(hi))
    branch = math.atan2(float(section["imposed_axial_velocity_m_s"]),
                        float(section["imposed_tangential_velocity_m_s"]))
    _require(branch < float(lo) < float(hi) < math.pi / 2)
    return [_residual_request(template, psi) for psi in (lo, hi)]


def _preflight(request):
    """Validate every annulus/polar/endpoint before the eventual first actual solve call."""
    _keys(request, "evaluation numerical_policy rotor annuli")
    _require(type(request["evaluation"]) is str)
    _exact(request["numerical_policy"], _POLICY)
    rotor, annuli = request["rotor"], request["annuli"]
    _keys(rotor, _ROTOR_KEYS)
    tip, hub = _positive(rotor["tip_radius_m"]), _positive(rotor["hub_radius_m"])
    _require(rotor["hub_radius_m"] < rotor["tip_radius_m"] and hub < tip)
    _require(type(rotor["blade_count"]) is int and 1 <= rotor["blade_count"] <= 64)
    omega = _positive(rotor["angular_speed_rad_s"])
    _positive(rotor["imposed_axial_velocity_m_s"], zero=True)
    for key in ("density_kg_m3", "dynamic_viscosity_pa_s", "speed_of_sound_m_s"):
        _positive(rotor[key])
    for key in ("geometry_source", "uncertainty_status"):
        _require(type(rotor[key]) is str and 0 < len(rotor[key]) <= 2000 and bool(rotor[key].strip()))
    _require(type(annuli) is list and 1 <= len(annuli) <= 8)
    previous, requests, geometry, budget = rotor["hub_radius_m"], [], [], 0
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
        section = {key: deepcopy(rotor[key]) for key in (
            "imposed_axial_velocity_m_s", "tip_radius_m", "density_kg_m3",
            "dynamic_viscosity_pa_s", "speed_of_sound_m_s", "blade_count")}
        section.update(imposed_tangential_velocity_m_s=tangential, radius_m=midpoint,
                       chord_m=deepcopy(annulus["chord_m"]), pitch_rad=deepcopy(annulus["pitch_rad"]))
        actual = {"evaluation": "stable_section_solve_experimental", "numerical_policy": deepcopy(_POLICY),
                  "residual_template": {"evaluation": "stable_section_residual_experimental",
                                        "numerical_policy": deepcopy(_POLICY),
                                        "polar": deepcopy(annulus["polar"]), "section": section},
                  "solve": deepcopy(annulus["solve"])}
        _solve_preflight(actual)
        budget += actual["solve"]["max_evaluations"]
        _require(budget <= 256)
        requests.append(actual)
        geometry.append((midpoint, width))
        previous = outer
    _exact(previous, rotor["tip_radius_m"])
    return requests, geometry


def _trace_value(rows, index):
    return rows[index]["result"]["outputs"]["residual_m2_s"]


def _trace_bracket(rows, lower, upper):
    width = _sum(float(rows[upper]["psi_rad"]), -float(rows[lower]["psi_rad"]))
    _require(width >= 0)
    return {"lower_evaluation_index": lower, "upper_evaluation_index": upper,
            "angle_width_rad": width}


def _trace_solution(rows, index):
    return {"evaluation_index": index, "psi_rad": rows[index]["psi_rad"],
            "residual_m2_s": _trace_value(rows, index)}


def _opposite(left, right):
    return left < 0 < right or right < 0 < left


def _replay_solve(rows, request):
    """Independent ordered state engine; consumes guarded observations, never evaluates.

    This engine is admission only. It neither executes nor calls V140's solve algorithm.
    Its cursor is local; parent quotas and whole-child result counts are untouched.
    """
    endpoints = _solve_preflight(request)
    _require(type(rows) is list and 1 <= len(rows) <= request["solve"]["max_evaluations"])
    cursor, seen = 0, []

    def consume(actual_request):
        nonlocal cursor
        _require(cursor < len(rows) and cursor < request["solve"]["max_evaluations"])
        row = rows[cursor]
        _keys(row, "psi_rad request_sha256 result")
        psi = actual_request["section"]["psi_rad"]
        _exact(row["psi_rad"], psi)  # Native endpoint type and signed zero also bind.
        _require(all(previous != psi for previous in seen))
        _exact(row["request_sha256"], sha256_record(actual_request))
        # Accepted V140 independent guard reused ONLY for its actual residual scope.
        _solve._guard_residual(row["result"], actual_request)
        seen.append(psi)
        index = cursor
        cursor += 1
        return index

    def finish(state, bracket=None, solution=None):
        _require(cursor == len(rows))  # No unused, appended or truncated observations.
        return state, bracket, solution

    lower = consume(endpoints[0])
    if _trace_value(rows, lower) is None:
        return finish("NOT_RUN_OUT_OF_POLAR_DOMAIN")
    upper = consume(endpoints[1])
    if _trace_value(rows, upper) is None:
        return finish("NOT_RUN_OUT_OF_POLAR_DOMAIN")
    # Both actual endpoint observations precede exact-zero and sign decisions.
    for index in (lower, upper):
        if _trace_value(rows, index) == 0:
            return finish("CONVERGED", _trace_bracket(rows, index, index), _trace_solution(rows, index))
    if not _opposite(_trace_value(rows, lower), _trace_value(rows, upper)):
        return finish("NOT_BRACKETED", _trace_bracket(rows, lower, upper))
    settings = request["solve"]
    while True:
        bracket = _trace_bracket(rows, lower, upper)
        best = min((lower, upper), key=lambda index: (abs(_trace_value(rows, index)), index))
        if (bracket["angle_width_rad"] <= settings["angle_tolerance_rad"]
                and abs(_trace_value(rows, best)) <= settings["residual_tolerance_m2_s"]):
            return finish("CONVERGED", bracket, _trace_solution(rows, best))
        if cursor >= settings["max_evaluations"]:
            return finish("EVALUATION_BUDGET_EXHAUSTED", bracket)
        lo, hi = float(rows[lower]["psi_rad"]), float(rows[upper]["psi_rad"])
        midpoint = _sum(lo, _product(0.5, bracket["angle_width_rad"]))
        if not lo < midpoint < hi:
            return finish("FLOAT_STAGNATION", bracket)
        middle = consume(_residual_request(request["residual_template"], midpoint))
        value = _trace_value(rows, middle)
        if value is None:
            return finish("NOT_RUN_OUT_OF_POLAR_DOMAIN", bracket)
        if value == 0:
            return finish("CONVERGED", _trace_bracket(rows, middle, middle), _trace_solution(rows, middle))
        if _opposite(_trace_value(rows, lower), value):
            upper = middle
        else:
            _require(_opposite(value, _trace_value(rows, upper)))
            lower = middle


def _solve_units(rows, bracket, solution):
    """All nested residual units come from observations AFTER their V140 guards."""
    frozen = _SOLVE_CATALOG["output_field_units"]
    return {"evaluations": [
                {"psi_rad": "rad", "request_sha256": "sha256",
                 "result": {"outputs": deepcopy(row["result"]["output_units"])}}
                for row in rows],
            "solve_state": "label",
            "final_bracket": (deepcopy(frozen["final_bracket"])
                              if bracket is not None else "not_applicable"),
            "solution": deepcopy(frozen["solution"]) if solution is not None else "not_applicable"}


def _guard_solve(actual, request):
    """Full independent V140 whole-solve admission, AFTER raw quota and snapshot checks.

    No parent quota/count is committed here. The caller must admit the WHOLE returned
    solve before retaining anything, even when earlier residual observations were valid.
    """
    _measure_native(actual, _CHILD_LIMITS)
    _measure_native(request, _SOLVE_INPUT_LIMITS)
    catalog = _snapshot_native(_solve.stable_section_solve_catalog())
    _exact(catalog, _SOLVE_CATALOG)
    _exact(catalog["evaluation"], "stable_section_solve_experimental")
    _exact(catalog["schema_version"], "stable_section_solve_v1")
    _exact(catalog["numerical_policy"], _POLICY)
    _require(type(actual) is dict and actual.keys() == _SOLVE_KEYS)
    _exact(actual["evaluation"], catalog["evaluation"])
    _exact(actual["schema_version"], catalog["schema_version"])
    _exact(actual["numerical_policy"], _POLICY)
    _exact(actual["status"], "COMPUTED_EXPERIMENTAL")
    _exact(actual["reasons"], [])
    output = actual["outputs"]
    _keys(output, "evaluations solve_state final_bracket solution")
    rows = output["evaluations"]
    state, bracket, solution = _replay_solve(rows, request)
    expected = {key: deepcopy(catalog[key]) for key in _SOLVE_KEYS}
    expected.update(
        status="COMPUTED_EXPERIMENTAL", reasons=[], diagnostics_complete=True,
        residual_result_count=len(rows), load_result_count=len(rows), lookup_result_count=len(rows),
        request_sha256=sha256_record(request),
        outputs={"evaluations": rows, "solve_state": state,
                 "final_bracket": bracket, "solution": solution},
        output_units=_solve_units(rows, bracket, solution))
    # Row subtrees are already independently admitted; avoid a redundant whole-child copy.
    _measure_native(expected, _CHILD_LIMITS)
    expected["evaluation_sha256"] = sha256_record({
        key: value for key, value in expected.items() if key != "evaluation_sha256"})
    _exact(actual, expected)
    return state, bracket, solution


_LIMITS = {"input_json": _INPUT_LIMITS, "output_json": _OUTPUT_LIMITS,
           "section_solve_input_json": _SOLVE_INPUT_LIMITS,
           "section_solve_output_json": _CHILD_LIMITS,
           "retained_children": {"max_serialized_bytes": _CHILD_BYTES_MAX,
                                  "max_nodes_including_keys": _CHILD_NODES_MAX,
                                  "scope": "sum of canonical whole child results, root depth1 each"},
           "core_work": {"annuli_max": 8, "section_solve_calls_max": 8,
                         "residual_calls_max": 256, "load_calls_max": 256,
                         "lookup_calls_max": 256, "aggregate_table_rows_max": 524288}}
_LIMITATIONS = [
    "Private experimental isolated axial rotor with fixed contiguous midpoint annuli; acceptance pending.",
    "Hub cutoff explicit; no hub-loss, interaction, radial refinement or spatial pressure/velocity field.",
    "No API, UI, legacy rotor switch, automatic fallback, source fetching or benchmark execution.",
    "Geometry and polar sources/uncertainty are unverified caller assertions; no physical validation.",
    "Midpoint quadrature and binary64 convergence have no whole-model error or physical qualification.",
    "Signed thrust/torque/power do not establish aircraft, motor, DC, regen or feasibility claims.",
    "Child quota measures complete returned objects; upstream child allocation/hash already occurred.",
    "Serialized byte/node ceilings are composition admission limits, not RAM/API/concurrency/time proofs.",
    "Only fully guarded whole solves contribute counts; partial or rejected child rows never count.",
    "Hashes bind native data; they do not establish authenticity, runtime identity or physical truth.",
    *_SOLVE_CATALOG["limitations"]]
_CONTRIBUTION_UNITS = {"thrust_n": "N", "torque_nm": "N*m"}
_INTEGRATED_UNITS = {"total_thrust_n": "N", "total_torque_nm": "N*m", "shaft_power_w": "W"}


def _integrate(rows, omega):
    """Signed midpoint rule from selected actual all-blade V133 loads; no extra B."""
    contributions = []
    for row in rows:
        output = row["actual_solve_result"]["outputs"]
        _require(output["solve_state"] == "CONVERGED")
        index = output["solution"]["evaluation_index"]
        residual = output["evaluations"][index]["result"]["outputs"]
        loads = residual["actual_load_result"]["outputs"]["loads"]
        contributions.append({
            "thrust_n": _product(loads["thrust_density_n_m"], row["radial_width_m"]),
            "torque_nm": _product(loads["torque_density_nm_m"], row["radial_width_m"])})
    thrust = _checked(math.fsum(item["thrust_n"] for item in contributions))
    torque = _checked(math.fsum(item["torque_nm"] for item in contributions))
    integrated = {"total_thrust_n": thrust, "total_torque_nm": torque,
                  "shaft_power_w": _product(omega, torque)}
    return contributions, integrated


def _response(status, reasons, digest=None, sections=0, residuals=0):
    return {"evaluation": EVALUATION, "schema_version": SCHEMA_VERSION,
            "numerical_policy": deepcopy(_POLICY), "status": status, "reasons": list(reasons),
            "outputs": {}, "output_units": {}, "diagnostics_complete": False,
            "section_solve_result_count": sections, "residual_result_count": residuals,
            "load_result_count": residuals, "lookup_result_count": residuals,
            "physical_validation": "NOT_ESTABLISHED", "numerical_qualification": "NOT_ESTABLISHED",
            "runtime_identity": "NOT_ESTABLISHED", "aircraft_status": None, "feasibility": None,
            "evidence_level": "unverified", "source_classification": "UNVERIFIED_CALLER_ASSERTION",
            "mach_interval_status": "UNVERIFIED_CALLER_APPLICABILITY_ONLY",
            "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
            "source_urls": list(_SOLVE_CATALOG["source_urls"]),
            "request_sha256": digest, "evaluation_sha256": None}


def _output_units(rows, integrated):
    return {"rotor_state": "label", "annuli": [
                {"annulus_index": "index", "radial_inner_m": "m", "radial_outer_m": "m",
                 "midpoint_radius_m": "m", "radial_width_m": "m",
                 "actual_solve_request": deepcopy(_SOLVE_CATALOG["input_units"]),
                 "actual_solve_result": {"outputs": deepcopy(row["actual_solve_result"]["output_units"])},
                 "contribution": (deepcopy(_CONTRIBUTION_UNITS)
                                  if row["contribution"] is not None else "not_applicable")}
                for row in rows],
            "integrated": deepcopy(_INTEGRATED_UNITS) if integrated is not None else "not_applicable"}


def _check_export(response):
    """Local output/count/unit structure checks; whole children were independently guarded."""
    _exact(response["numerical_policy"], _POLICY)
    sections = response["section_solve_result_count"]
    counts = [response[key] for key in ("residual_result_count", "load_result_count", "lookup_result_count")]
    _require(type(sections) is int and 0 <= sections <= 8)
    _require(all(type(count) is int and 0 <= count <= 256 for count in counts))
    _require(counts[0] == counts[1] == counts[2])
    _require(sections <= counts[0] <= 32 * sections)  # An admitted OOD solve can contain one row.
    output = response["outputs"]
    if not output:
        _exact(response["output_units"], {})
        return
    _require(response["status"] == "COMPUTED_EXPERIMENTAL")
    _exact(response["diagnostics_complete"], True)
    _keys(output, "rotor_state annuli integrated")
    rows, integrated = output["annuli"], output["integrated"]
    _require(type(rows) is list and len(rows) == sections and sections > 0)
    total, quota = 0, _ChildQuota()
    converged = True
    for index, row in enumerate(rows):
        _keys(row, "annulus_index radial_inner_m radial_outer_m midpoint_radius_m radial_width_m "
                   "actual_solve_request actual_solve_result contribution")
        _exact(row["annulus_index"], index)
        for key in ("radial_inner_m", "radial_outer_m", "midpoint_radius_m", "radial_width_m"):
            _positive(row[key])
        for key in ("midpoint_radius_m", "radial_width_m"):
            _require(type(row[key]) is float)
        child = row["actual_solve_result"]
        quota.commit(quota.measure(child))
        count = child["residual_result_count"]
        _require(type(count) is int and 1 <= count <= 32)
        _exact(child["load_result_count"], count)
        _exact(child["lookup_result_count"], count)
        total += count
        converged = converged and child["outputs"]["solve_state"] == "CONVERGED"
        if row["contribution"] is not None:
            _keys(row["contribution"], "thrust_n torque_nm")
            for value in row["contribution"].values():
                _checked(value)
    _exact(total, counts[0])
    _exact(output["rotor_state"], "COMPUTED" if converged else "NOT_RUN_SECTION_NOT_CONVERGED")
    _require((integrated is not None) == converged)
    _require(all((row["contribution"] is not None) == converged for row in rows))
    if integrated is not None:
        _keys(integrated, "total_thrust_n total_torque_nm shaft_power_w")
        for value in integrated.values():
            _checked(value)
    _exact(response["output_units"], _output_units(rows, integrated))


def _seal(response):
    _measure_native(response, _OUTPUT_LIMITS)
    _check_export(response)
    if response["request_sha256"] is not None:
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"})
    _measure_native(response, _OUTPUT_LIMITS)
    return response


def _failure(reason, digest=None, sections=0, residuals=0):
    try:
        return _seal(_response("EXECUTION_FAILED", [reason], digest, sections, residuals))
    except Exception:  # noqa: BLE001 -- persistent export/hash faults expose no payload or hashes.
        response = _response("EXECUTION_FAILED", [reason], sections=sections, residuals=residuals)
        _measure_native(response, _OUTPUT_LIMITS)
        return response


def evaluate_stable_polar_rotor(request):
    """Compose actual V140 solves; raw quota admission precedes parent copy/hash/guard."""
    try:
        snapshot = _snapshot_native(request)
        _keys(snapshot, "evaluation numerical_policy rotor annuli")
        _require(type(snapshot["evaluation"]) is str)
    except Exception:  # noqa: BLE001 -- bounded native root before copy/hash/model work.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    if snapshot["evaluation"] != EVALUATION:
        return _seal(_response("SOLVER_UNSUPPORTED", ["UNSUPPORTED_EVALUATION"]))
    try:
        requests, geometry = _preflight(snapshot)
    except Exception:  # noqa: BLE001 -- ALL annuli/polars/endpoints before any actual solve.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    digest, sections, residuals, rows, quota = None, 0, 0, [], _ChildQuota()
    try:
        digest = sha256_record(snapshot)
        for index, actual_request in enumerate(requests):
            try:
                # Child allocation/hash happens upstream; the quota cannot prevent that work.
                actual = _solve.evaluate_stable_section_solve(deepcopy(actual_request))
                retained, measured = _snapshot_child(actual, quota)
                _guard_solve(retained, actual_request)
                quota.commit(measured)
            except _ResourceBudgetExceeded:
                return _failure("RESOURCE_BUDGET_EXCEEDED", digest, sections, residuals)
            except Exception:  # noqa: BLE001 -- current whole child contributes no accepted counts.
                return _failure("SOLVE_BOUNDARY_FAILED", digest, sections, residuals)
            sections += 1
            residuals += retained["residual_result_count"]
            annulus = snapshot["annuli"][index]
            midpoint, width = geometry[index]
            rows.append({"annulus_index": index,
                         "radial_inner_m": deepcopy(annulus["radial_inner_m"]),
                         "radial_outer_m": deepcopy(annulus["radial_outer_m"]),
                         "midpoint_radius_m": midpoint, "radial_width_m": width,
                         "actual_solve_request": actual_request,
                         "actual_solve_result": retained, "contribution": None})
        converged = all(row["actual_solve_result"]["outputs"]["solve_state"] == "CONVERGED" for row in rows)
        integrated = None
        if converged:
            contributions, integrated = _integrate(rows, float(snapshot["rotor"]["angular_speed_rad_s"]))
            for row, contribution in zip(rows, contributions, strict=True):
                row["contribution"] = contribution
        response = _response("COMPUTED_EXPERIMENTAL", [], digest, sections, residuals)
        response["outputs"] = {
            "rotor_state": "COMPUTED" if converged else "NOT_RUN_SECTION_NOT_CONVERGED",
            "annuli": rows, "integrated": integrated}
        response["output_units"] = _output_units(rows, integrated)
        response["diagnostics_complete"] = True
        return _seal(response)
    except Exception:  # noqa: BLE001 -- arithmetic/export faults retain counts, no partial rotor payload.
        return _failure("STABLE_POLAR_ROTOR_EXECUTION_FAILED", digest, sections, residuals)


def stable_polar_rotor_catalog():
    """Fresh private composition contract; no evaluator, source or benchmark access."""
    child_units = _SOLVE_CATALOG["input_units"]
    result = {
        **_response("RESEARCH_ONLY", []),
        "required_fields": ["evaluation", "numerical_policy", "rotor", "annuli"],
        "input_units": {
            "evaluation": "label", "numerical_policy": {"id": "label", "f_min": "1", "f_max": "1"},
            "rotor": {"tip_radius_m": "m", "hub_radius_m": "m", "blade_count": "1",
                      "angular_speed_rad_s": "rad/s", "imposed_axial_velocity_m_s": "m/s",
                      "density_kg_m3": "kg/m^3", "dynamic_viscosity_pa_s": "Pa*s",
                      "speed_of_sound_m_s": "m/s", "geometry_source": "text", "uncertainty_status": "text"},
            "annuli": {"radial_inner_m": "m", "radial_outer_m": "m", "chord_m": "m", "pitch_rad": "rad",
                       "polar": deepcopy(child_units["residual_template"]["polar"]),
                       "solve": deepcopy(child_units["solve"])}},
        "output_field_units": {
            "rotor_state": "label",
            "annuli": {"annulus_index": "index", "radial_inner_m": "m", "radial_outer_m": "m",
                       "midpoint_radius_m": "m", "radial_width_m": "m",
                       "actual_solve_request": deepcopy(child_units),
                       "actual_solve_result": {"outputs": deepcopy(_SOLVE_CATALOG["output_field_units"])},
                       "contribution": deepcopy(_CONTRIBUTION_UNITS)},
            "integrated": deepcopy(_INTEGRATED_UNITS)},
        "request_contract": {
            "schema": "Exact evaluation/numerical_policy/rotor/annuli; exact fields, no defaults.",
            "policy": "Exact frozen V140 policy including str/float/int native types; both child policy positions explicit.",
            "geometry": "1..8 full-native-exact contiguous hub-to-tip annuli, positive hub, strict interior midpoint.",
            "properties": "Positive normal radii/chord/omega/rho/mu/sound speed; Ua>=0, pitch[0,pi/2], B int1..64.",
            "sources": "Nonblank geometry_source/uncertainty_status <=2000 strict UTF8 chars; caller polars unverified.",
            "budget": "Each explicit builtin int2..32; aggregate requested <=256; no retries or tolerance loosening.",
            "preflight": "All derived actual stable solve requests, polars and both static endpoints before any child call."},
        "calculations": {
            "geometry": "dr=fsum(outer,-inner); r=fsum(inner,.5*dr); Ut=Omega*r; Ua=imposed axial.",
            "integration": "Selected actual all-blade V133 dT/dr,dQ/dr times dr; no extra blade count.",
            "totals": "Ordered signed contributions summed with fsum; shaft_power_w=Omega*total_torque_nm.",
            "eligibility": "All children CONVERGED or ALL contributions/integrated null with not_applicable units.",
            "arithmetic": "Checked normal-or-zero binary64; nested V140 bound alone permits positive finite subnormal."},
        "boundary_contract": {
            "guard": "Fresh frozen exact V140 catalog; independent ordered trace engine, accepted V140 residual guard only in residual scope.",
            "oracle": "No solve evaluator/_bisect or producer numerical helper used for trace replay.",
            "quota": "Sum canonical WHOLE returned child objects, including units/metadata/hashes; <=64MiB and8388608 nodes.",
            "admission": "Raw intrinsic+remaining quota stream checks, copy, remeasure/exact compare, full guard, commit quota, then counts.",
            "upstream": "Child has already allocated/hashed its returned result; quota does not prevent upstream allocation.",
            "refusal": "Quota exception => RESOURCE_BUDGET_EXCEEDED; no parent copy/hash/guard of that rejected child; prior whole counts only.",
            "counts": "Section solves int0..8; residual/load/lookup equal sums of fully guarded whole solves int0..256; not attempts.",
            "nonconverged": "Accepted computed nonconverged/OOD child retained; all annuli still called; integration null.",
            "failure": "Atomic empty outputs/units; SOLVE_BOUNDARY_FAILED or STABLE_POLAR_ROTOR_EXECUTION_FAILED with prior counts.",
            "export": "Separate root128MiB/16777216-node ceiling; requests/wrappers/units extra; prehash and postseal checked.",
            "qualification": "Configured byte/node ceilings are not RAM/API/time/concurrency proofs; probes and independent acceptance pending."},
        "status_matrix": {
            "RESEARCH_ONLY": "Catalog only; zero counts, null hashes.",
            "MODEL_INAPPLICABLE": "INVALID_REQUEST; no calls/counts, empty payload, null hashes.",
            "SOLVER_UNSUPPORTED": "UNSUPPORTED_EVALUATION; no calls/counts, empty payload, null hashes.",
            "COMPUTED_EXPERIMENTAL": "All whole children admitted; COMPUTED or NOT_RUN_SECTION_NOT_CONVERGED.",
            "EXECUTION_FAILED": "Sanitized atomic failure/resource receipt; prior whole counts only, no retained payload."},
        "hash_contract": {
            "request": "SHA256 full validated native request: policy/geometry/all polar bytes/budgets; sorted compact UTF8 ensure_ascii=False allow_nan=False.",
            "evaluation": "SHA256 full bounded response excluding only evaluation_sha256; data binding, not authenticity.",
            "exceptions": "Ordinary Exception sanitized; BaseException propagates; persistent export/hash fault clears payload/both hashes, retains counts."}}
    _measure_native(result, _OUTPUT_LIMITS)
    return result
