"""Bounded experimental allocation using retained actual V112 static loads."""

from copy import deepcopy

from scipy.optimize import least_squares

from . import reference_air_tabulated_hover as _reference
from . import tabulated_rotor_assembly as _assembly
from .hover_bemt import _mul, _normal
from .provenance import sha256_record
from .reference_air_tabulated_hover import _exact
from .tabulated_hover_bemt_request import _json_walk, _require
from .tabulated_thrust_target_assembly_validation import _air

EVALUATION = "bounded_tabulated_static_wrench_solve_experimental"
SCHEMA_VERSION = "tabulated_static_wrench_solve_v1"
# Captured before caller data; returned metadata never defines admission policy.
_ASSEMBLY_CATALOG = _assembly.tabulated_rotor_assembly_catalog()
_ROOT = frozenset(("evaluation", "assembly_template", "rotor_speed_bounds",
                   "required_net_force_body_n", "required_net_moment_cg_body_nm",
                   "absolute_force_tolerance_n", "absolute_moment_tolerance_nm",
                   "max_evaluations"))
_BOUND = frozenset(("id", "angular_speed_bracket_rad_s", "initial_angular_speed_rad_s"))
_LIMITS = {
    "input_json": {**_ASSEMBLY_CATALOG["limits"]["input_json"],
                   "max_nodes_including_keys": 262144, "max_depth": 16},
    "output_json": {**_ASSEMBLY_CATALOG["limits"]["output_json"],
                    "max_nodes_including_keys": 1048576, "max_depth": 28},
    "assembly_input_json": deepcopy(_ASSEMBLY_CATALOG["limits"]["input_json"]),
    "assembly_output_json": deepcopy(_ASSEMBLY_CATALOG["limits"]["output_json"]),
    "child_input_json": deepcopy(_ASSEMBLY_CATALOG["limits"]["child_input_json"]),
    "child_output_json": deepcopy(_ASSEMBLY_CATALOG["limits"]["child_output_json"]),
    "core_work": {"rotors_max": 8, "total_annuli_per_assembly_max": 4096,
                  "evaluations_min": 2, "evaluations_max": 64,
                  "evaluation_annuli_product_max": 65536},
}
_LIMITATIONS = (
    "Experimental bounded allocation of isolated tabulated static rotor loads only.",
    "No physical or numerical qualification, runtime identity or aircraft validation.",
    "No global uniqueness, infeasibility, Jacobian rank, control authority or stability claim.",
    "No motor, thermal, mission, installed, interference or non-hover validation.",
    "Residual acceptance is a numerical condition on actual retained net loads including gravity.",
    "Nonselected result digests are format-only producer provenance without retained payloads.",
    "Sources and classifications are unverified caller declarations; no complete PDF claim.",
)


def _assembly_input(snapshot, speeds):
    actual = deepcopy(snapshot["assembly_template"])
    for rotor, speed in zip(actual["rotors"], speeds, strict=True):
        rotor["rotor_template"]["angular_speed_rad_s"] = speed
    return actual


def _preflight(snapshot):
    _require(type(snapshot) is dict and snapshot.keys() == _ROOT)
    _require(type(snapshot["evaluation"]) is str and snapshot["evaluation"] == EVALUATION)
    template, bounds = snapshot["assembly_template"], snapshot["rotor_speed_bounds"]
    _require(type(template) is dict and template.keys() == set(_assembly._ROOT))
    _require(type(template["evaluation"]) is str and template["evaluation"] == _ASSEMBLY_CATALOG["evaluation"])
    rotors = template["rotors"]
    _require(type(rotors) is list and 1 <= len(rotors) <= 8)
    _require(type(bounds) is list and len(bounds) == len(rotors))
    speeds, seen = [], set()
    fields = set(_ASSEMBLY_CATALOG["rotor_template_fields"]) - {"angular_speed_rad_s"}
    for rotor, bound in zip(rotors, bounds, strict=True):
        _require(type(rotor) is dict and rotor.keys() == set(_assembly._ROTOR))
        child = rotor["rotor_template"]
        _require(type(child) is dict and child.keys() == fields)
        _require(type(bound) is dict and bound.keys() == _BOUND)
        name = bound["id"]
        _require(type(name) is str and type(rotor["id"]) is str and name == rotor["id"] and name not in seen)
        seen.add(name)
        bracket = bound["angular_speed_bracket_rad_s"]
        _require(type(bracket) is list and len(bracket) == 2)
        lo, hi = [_assembly._number(v) for v in bracket]
        initial = _assembly._number(bound["initial_angular_speed_rad_s"])
        _require(0.0 < lo < hi and lo <= initial <= hi)
        speeds.append(initial)
    for field in ("required_net_force_body_n", "required_net_moment_cg_body_nm"):
        _assembly._vector(snapshot[field])
    for field in ("absolute_force_tolerance_n", "absolute_moment_tolerance_nm"):
        _require(_assembly._number(snapshot[field]) > 0.0)
    budget = snapshot["max_evaluations"]
    _require(type(budget) is int and 2 <= budget <= 64)
    actual = _assembly_input(snapshot, speeds)
    _json_walk(actual, _LIMITS["assembly_input_json"])
    _assembly._preflight(actual)
    _require(budget * sum(r["rotor_template"]["annuli"] for r in rotors) <= 65536)
    return actual


def _response(status, reasons, digest=None, count=0, rotor_count=0):
    return {"evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
            "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
            "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
            "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
            "evaluation_count": count, "rotor_evaluation_count": rotor_count,
            "reasons": list(reasons), "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
            "request_sha256": digest, "evaluation_sha256": None,
            "outputs": {}, "output_units": {}, "stages": [], "transfers": []}


def _seal(response):
    _json_walk(response, _LIMITS["output_json"])
    if response["request_sha256"] is not None and response["status"] in ("COMPUTED_EXPERIMENTAL", "EXECUTION_FAILED"):
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"})
    _json_walk(response, _LIMITS["output_json"])
    return response


_ASSEMBLY_RESULT_KEYS = frozenset((
    "evaluation", "schema_version", "status", "evidence_level", "physical_validation",
    "numerical_qualification", "runtime_identity", "aircraft_status", "feasibility",
    "diagnostics_complete", "rotor_evaluation_count", "reasons", "limitations", "limits",
    "request_sha256", "evaluation_sha256", "outputs", "output_units", "stages", "transfers",
))
_ASSEMBLY_DYNAMIC = frozenset((
    "status", "diagnostics_complete", "rotor_evaluation_count", "reasons", "request_sha256",
    "evaluation_sha256", "outputs", "output_units", "stages", "transfers",
))


def _bounded_snapshot(value, limits):
    """Bound real builtin JSON before copy hooks, equality or hashing can run."""
    _json_walk(value, limits)
    detached = deepcopy(value)
    _json_walk(detached, limits)
    return detached


def _assembly_snapshot(actual):
    """Detach the entire actual V112 return immediately under its own budget."""
    return _bounded_snapshot(actual, _LIMITS["assembly_output_json"])


def _guard_assembly_success(actual, request):
    """Pure full-success admission of retained actual data; never rerun models.

    This boundary establishes neither failure causality nor physical validation
    nor execution attestation. Noncomputed envelopes are outside admission.
    """
    _json_walk(actual, _LIMITS["assembly_output_json"])
    _json_walk(request, _LIMITS["assembly_input_json"])
    _require(type(request) is dict and request.keys() == set(_assembly._ROOT))
    _exact(request["evaluation"], _ASSEMBLY_CATALOG["evaluation"])
    _assembly._preflight(request)
    _require(type(actual) is dict and actual.keys() == _ASSEMBLY_RESULT_KEYS)
    for name in _ASSEMBLY_RESULT_KEYS - _ASSEMBLY_DYNAMIC:
        _exact(actual[name], _ASSEMBLY_CATALOG[name])
    _exact(actual["status"], "COMPUTED_EXPERIMENTAL")
    _exact(actual["diagnostics_complete"], True)
    _exact(actual["reasons"], [])
    _exact(actual["rotor_evaluation_count"], len(request["rotors"]))
    _exact(actual["request_sha256"], sha256_record(request))
    _exact(actual["evaluation_sha256"], sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"}))
    units = _ASSEMBLY_CATALOG["output_field_units"]
    _exact(actual["output_units"], units)
    outputs = actual["outputs"]
    _require(type(outputs) is dict and outputs.keys() == units.keys())
    _air(outputs["air"], request["air"])
    rows, rotors = outputs["rotors"], request["rotors"]
    _require(type(rows) is list and len(rows) == len(rotors))
    stages, transfers = actual["stages"], actual["transfers"]
    _require(type(stages) is list and len(stages) == len(rotors) + 1)
    _require(type(transfers) is list and len(transfers) == len(rotors))
    air_digest = sha256_record(outputs["air"])
    _exact(stages[0], {"stage": "air", "inputs": request["air"],
                       "inputs_sha256": sha256_record(request["air"]),
                       "result_sha256": air_digest})
    density = outputs["air"]["state"]["density_kg_m3"]
    cg = _assembly._vector(request["cg_body_m"])
    for index, (row, rotor) in enumerate(zip(rows, rotors, strict=True)):
        _require(type(row) is dict and row.keys() == units["rotors"].keys())
        injected = row["actual_forward_request"]
        _json_walk(injected, _LIMITS["child_input_json"])
        _exact(injected, {**rotor["rotor_template"], "density_kg_m3": density})
        forward = row["actual_forward_result"]
        _json_walk(forward, _LIMITS["child_output_json"])
        _require(_reference._validate_child(forward, injected) is True)
        loads = _assembly._loads(rotor, cg, forward["outputs"])
        for name, expected in loads.items():
            _exact(row[name], expected)
        stage, request_digest = "rotor:" + rotor["id"], sha256_record(injected)
        _exact(stages[index + 1], {"stage": stage, "inputs": injected,
                                  "inputs_sha256": request_digest,
                                  "result_sha256": sha256_record(forward)})
        _exact(transfers[index], {
            "from_stage": "air", "from_field": "state.density_kg_m3",
            "to_stage": stage, "to_field": "density_kg_m3", "value": density,
            "unit": "kg/m^3", "producer_result_sha256": air_digest,
            "consumer_request_sha256": request_digest,
        })
    gravity = [_mul(_mul(_assembly._number(request["mass_kg"]),
                         outputs["air"]["gravity_m_s2"]), direction)
               for direction in _assembly._vector(request["gravity_direction_body"], unit=True)]
    _exact(outputs["gravity_force_body_n"], gravity)
    _exact(outputs["net_force_body_n"], [
        _assembly._sum([row["force_body_n"][i] for row in rows] + [gravity[i]])
        for i in range(3)])
    _exact(outputs["net_moment_cg_body_nm"], [
        _assembly._sum([row["moment_cg_body_nm"][i] for row in rows]) for i in range(3)])


class _BudgetStop(Exception):
    pass


class _ResidualMet(Exception):
    pass


class _AssemblyBoundaryFailed(Exception):
    pass


_CANDIDATE_UNITS = {
    "index": "1", "angular_speeds_rad_s": "rad/s", "net_force_body_n": "N",
    "net_moment_cg_body_nm": "N*m", "force_residual_n": "N", "moment_residual_nm": "N*m",
    "scaled_residual": "1", "max_scaled_residual": "1",
    "request_sha256": "SHA256", "result_sha256": "SHA256",
}
_OUTPUT_UNITS = {
    "outcome": "label", "candidates": _CANDIDATE_UNITS, "selected_index": "1",
    "actual_assembly_request": deepcopy(_ASSEMBLY_CATALOG["input_units"]),
    "actual_assembly_result": {"outputs": deepcopy(_ASSEMBLY_CATALOG["output_field_units"])},
}
_SOURCE_URL = "https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html"


def _candidate(snapshot, speeds, actual, request, index):
    outputs = actual["outputs"]
    force = _assembly._vector(outputs["net_force_body_n"])
    moment = _assembly._vector(outputs["net_moment_cg_body_nm"])
    fr = [_normal(a - b, zero=True) for a, b in zip(
        force, _assembly._vector(snapshot["required_net_force_body_n"]), strict=True)]
    mr = [_normal(a - b, zero=True) for a, b in zip(
        moment, _assembly._vector(snapshot["required_net_moment_cg_body_nm"]), strict=True)]
    ft = _assembly._number(snapshot["absolute_force_tolerance_n"])
    mt = _assembly._number(snapshot["absolute_moment_tolerance_nm"])
    scaled = [_normal(v / ft, zero=True) for v in fr] + [_normal(v / mt, zero=True) for v in mr]
    _require(all(v == 0.0 or r != 0.0 for v, r in zip(fr + mr, scaled, strict=True)))
    return {"index": index, "angular_speeds_rad_s": list(speeds), "net_force_body_n": force,
            "net_moment_cg_body_nm": moment, "force_residual_n": fr, "moment_residual_nm": mr,
            "scaled_residual": scaled, "max_scaled_residual": max(abs(v) for v in scaled),
            "request_sha256": sha256_record(request), "result_sha256": sha256_record(actual)}


def _solve(snapshot, counts):
    bounds = snapshot["rotor_speed_bounds"]
    los = [_assembly._number(b["angular_speed_bracket_rad_s"][0]) for b in bounds]
    his = [_assembly._number(b["angular_speed_bracket_rad_s"][1]) for b in bounds]
    initial = [_assembly._number(b["initial_angular_speed_rad_s"]) for b in bounds]
    budget, candidates, best = snapshot["max_evaluations"], [], None

    def objective(x):
        nonlocal best
        if counts["evaluation_count"] >= budget:
            raise _BudgetStop
        # SciPy supplies ndarray scalars; convert each exactly once, then bound.
        speeds = [_normal(float(v), zero=True) for v in x]
        _require(len(speeds) == len(bounds))
        _require(all(lo <= speed <= hi for speed, lo, hi in zip(speeds, los, his, strict=True)))
        request = _assembly_input(snapshot, speeds)
        _json_walk(request, _LIMITS["assembly_input_json"])
        try:
            actual = _assembly_snapshot(_assembly.evaluate_tabulated_rotor_assembly(deepcopy(request)))
            _guard_assembly_success(actual, request)
        except Exception as error:
            raise _AssemblyBoundaryFailed from error
        counts["evaluation_count"] += 1
        counts["rotor_evaluation_count"] += len(request["rotors"])
        row = _candidate(snapshot, speeds, actual, request, len(candidates))
        candidates.append(row)
        if best is None or row["max_scaled_residual"] < best[0]["max_scaled_residual"]:
            best = (row, request, actual)
        if row["max_scaled_residual"] <= 1.0:
            raise _ResidualMet
        return row["scaled_residual"]

    try:
        least_squares(objective, initial, bounds=(los, his), method="trf", jac="2-point",
                      loss="linear", x_scale=1, ftol=1e-12, xtol=1e-12, gtol=1e-12,
                      max_nfev=budget)
    except (_BudgetStop, _ResidualMet):
        pass
    _require(best is not None)
    outcome = ("RESIDUAL_MET" if best[0]["max_scaled_residual"] <= 1.0 else
               "EVALUATION_LIMIT" if counts["evaluation_count"] >= budget else "SOLVER_STOPPED")
    return {"outcome": outcome, "candidates": candidates, "selected_index": best[0]["index"],
            "actual_assembly_request": best[1], "actual_assembly_result": best[2]}


def evaluate_tabulated_static_wrench_solve(request):
    """Allocate bounded speeds using actual V112 calls and pure success admission."""
    try:
        snapshot = _bounded_snapshot(request, _LIMITS["input_json"])
        _require(type(snapshot) is dict and snapshot.keys() == _ROOT)
        _require(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _seal(_response("SOLVER_UNSUPPORTED", ["Unsupported evaluation."]))
        _preflight(snapshot)
    except (ValueError, OverflowError):
        return _seal(_response("MODEL_INAPPLICABLE", ["Invalid bounded allocation request."]))
    except Exception:  # noqa: BLE001 -- public boundary sanitizes ordinary admission faults.
        return _seal(_response("EXECUTION_FAILED", ["Request admission failed."]))
    digest, counts = None, {"evaluation_count": 0, "rotor_evaluation_count": 0}
    try:
        digest = sha256_record(snapshot)
        outputs = _solve(snapshot, counts)
        result = _response("COMPUTED_EXPERIMENTAL", [], digest,
                           counts["evaluation_count"], counts["rotor_evaluation_count"])
        result.update(diagnostics_complete=True, outputs=outputs, output_units=deepcopy(_OUTPUT_UNITS))
        return _seal(result)
    except _AssemblyBoundaryFailed:
        reason = "ASSEMBLY_BOUNDARY_FAILED"
    except Exception:  # noqa: BLE001 -- public boundary sanitizes ordinary execution faults.
        reason = "ALLOCATION_EXECUTION_FAILED"
    return _seal(_response("EXECUTION_FAILED", [reason], digest,
                           counts["evaluation_count"], counts["rotor_evaluation_count"]))


def tabulated_static_wrench_solve_catalog():
    """Fresh closed request, units, limits and numerical policy; no execution."""
    return {**_response("RESEARCH_ONLY", []), "required_fields": sorted(_ROOT),
            "bound_fields": sorted(_BOUND), "defaults": {},
            "input_units": {"evaluation": "label", "assembly_template": {
                **deepcopy(_ASSEMBLY_CATALOG["input_units"]), "rotors": {
                    **deepcopy(_ASSEMBLY_CATALOG["input_units"]["rotors"]), "rotor_template": {
                        k: deepcopy(v) for k, v in _ASSEMBLY_CATALOG["input_units"]["rotors"]["rotor_template"].items()
                        if k != "angular_speed_rad_s"}}},
                "rotor_speed_bounds": {"id": "label", "angular_speed_bracket_rad_s": "rad/s",
                                       "initial_angular_speed_rad_s": "rad/s"},
                "required_net_force_body_n": "N", "required_net_moment_cg_body_nm": "N*m",
                "absolute_force_tolerance_n": "N", "absolute_moment_tolerance_nm": "N*m",
                "max_evaluations": "1"}, "output_field_units": deepcopy(_OUTPUT_UNITS),
            "request_contract": {
                "objects": "Closed builtin JSON objects; no bool or subclasses as numbers; no implicit defaults.",
                "assembly_template": "Full V112 root and declarations; omit density and angular speed from every rotor template.",
                "bounds": "Ordered unique IDs matching rotors; positive finite normal lo < hi; lo <= initial <= hi.",
                "numbers": "Exact builtin int/float binary64 conversion; finite normal or zero; positive tolerances.",
                "preflight": "All templates, bounds, declarations, frame, mass, child JSON budgets and work product before hashing or model calls.",
            }, "formulas": {
                "residual": "Six components in order: (Factual-Frequired)/force_tolerance then (Mactual-Mrequired)/moment_tolerance.",
                "acceptance": "max(abs(scaled_residual)) <= 1 inclusive; actual net force already includes mass times actual gravity.",
                "selection": "Earliest strict minimum of actual max absolute scaled residual; retain full selected request/result once.",
                "arithmetic": "Binary64 subtraction then division; finite normal or exact zero; reject overflow and nonzero underflow.",
            }, "numerical_policy": {
                "method": "trf", "jac": "2-point", "loss": "linear", "x_scale": 1,
                "ftol": 1e-12, "xtol": 1e-12, "gtol": 1e-12,
                "budget": "Own objective counter includes finite differences; stop before any call beyond max_evaluations; no extra initial/final call.",
                "scipy": "max_nfev/nfev exclude numerical Jacobian calls; local minimum only; TRF may move initial speeds inside bounds; SciPy success is not acceptance.",
                "source_url": _SOURCE_URL,
            }, "response_contract": {
                "counts": "Only fully guarded V112 SUCCESS trials and their rotor counts; not attempted calls, failure causality or execution attestation.",
                "outcomes": ["RESIDUAL_MET", "EVALUATION_LIMIT", "SOLVER_STOPPED"],
                "boundary": "Every noncomputed or malformed actual assembly gives only ASSEMBLY_BOUNDARY_FAILED; no trusted child failure cause.",
                "atomic": "Failures retain prior guarded counts; empty outputs, output_units, stages, transfers; diagnostics false; BaseException propagates.",
                "hashes": "Request null before admission; sealed accepted success/failure hash omits itself; JSON bounded before copy/hash/equality.",
                "trace": "Chronological guarded candidate summaries with actual speeds/net loads/residuals and request/result digests; selected full request/result once.",
                "provenance": "Nonselected request digests recoverable from template plus speeds; nonselected result digests format-only without payloads.",
            }}
