"""Provisional observational continuum comparison; standalone, not a public API."""

import copy
import math
import sys
from itertools import pairwise

from scipy.optimize import brentq

from physimesh.drone.beam_modal import solve_cantilever_modes

_BRACKETS = ((1, 2), (4, 5), (7, 8), (10, 11), (14, 15), (17, 18))


class _Invalid(Exception):
    def __init__(self, code, field=None):
        self.code, self.field = code, field


def _finite_json(value):
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_finite_json(v) for v in value)
    if type(value) is dict:
        return all(type(k) is str and _finite_json(v) for k, v in value.items())
    return False


def _reference(beta, xi):
    """Tip-normalized displacement and xi derivative, without growing exponentials."""
    t = math.exp(-beta)
    s, c = math.sin(beta), math.cos(beta)
    d = 1 - t*t + 2*s*t
    a = (-t + s - c) / d
    b = (1 + (s + c)*t) / d
    sigma = (1 + t*t + 2*c*t) / d

    def evaluate(x):
        ep, em = math.exp(beta*(x-1)), math.exp(-beta*x)
        return (a*ep + b*em - math.cos(beta*x) + sigma*math.sin(beta*x),
                beta*(a*ep - b*em + math.sin(beta*x) + sigma*math.cos(beta*x)))

    tip, _ = evaluate(1.0)
    u, du = evaluate(xi)
    result = u/tip, du/tip
    if not all(math.isfinite(v) for v in result):
        raise _Invalid("REFERENCE_FAILURE")
    return result


def _observed_order(coarse, fine, nc, nf):
    if not all(math.isfinite(v) and v > 0 for v in (coarse, fine)):
        return None
    # Difference of logs avoids overflow in the ratio of tiny errors.
    value = (math.log(coarse) - math.log(fine)) / math.log(nf/nc)
    return value if math.isfinite(value) else None


def _scalar(value, field):
    if type(value) not in (int, float):
        raise _Invalid("INVALID_TYPE", field)
    try:
        result = float(value)
    except OverflowError:
        raise _Invalid("NONFINITE_OR_UNDERFLOW", field) from None
    if not math.isfinite(result) or 0 < result < sys.float_info.min:
        raise _Invalid("NONFINITE_OR_UNDERFLOW", field)
    if result <= 0:
        raise _Invalid("INVALID_VALUE", field)
    return result


def uniform_modal_refinement(*, length_m, E_pa, I_m4, mass_per_length_kg_m,
                             element_counts, modes):
    """Observe first-six-mode continuum errors on 2..6 increasing meshes.

    All arguments are required. No observation establishes accuracy or approval.
    A refusal discards every partial mesh result.
    """
    envelope = {"schema_version": "uniform_modal_refinement_v1",
                "physical_validation": "NOT_ESTABLISHED",
                "numerical_qualification": "NOT_ESTABLISHED",
                "mesh_accuracy": "NOT_ESTABLISHED", "evidence_level": "unverified",
                "aircraft_status": None, "feasibility": None}
    try:
        inputs = {k: _scalar(v, k) for k, v in (
            ("length_m", length_m), ("E_pa", E_pa), ("I_m4", I_m4),
            ("mass_per_length_kg_m", mass_per_length_kg_m))}
        if type(element_counts) is not list:
            raise _Invalid("INVALID_TYPE", "element_counts")
        if not 2 <= len(element_counts) <= 6:
            raise _Invalid("UNSUPPORTED_RANGE", "element_counts")
        if any(type(n) is not int for n in element_counts):
            raise _Invalid("INVALID_TYPE", "element_counts")
        if any(not 2 <= n <= 64 for n in element_counts) or any(
                a >= b for a, b in pairwise(element_counts)):
            raise _Invalid("UNSUPPORTED_RANGE", "element_counts")
        if type(modes) is not int:
            raise _Invalid("INVALID_TYPE", "modes")
        if not 1 <= modes <= min(6, 2*element_counts[0]):
            raise _Invalid("UNSUPPORTED_RANGE", "modes")
        try:
            roots = [float(brentq(lambda x: math.cos(x) + 1/math.cosh(x), lo, hi,
                                 xtol=5e-324, rtol=4*sys.float_info.epsilon))
                     for lo, hi in _BRACKETS[:modes]]
        except RuntimeError:
            raise _Invalid("REFERENCE_FAILURE") from None
        meshes = []
        for n in element_counts:
            core = solve_cantilever_modes(**inputs, elements=n, modes=modes)
            if not _finite_json(core) or type(core) is not dict:
                raise _Invalid("MALFORMED_CORE_RESULT")
            if core.get("status") == "REFUSED":
                refusal = core.get("refusal")
                if (type(refusal) is not dict or type(refusal.get("code")) is not str
                        or type(refusal.get("message")) is not str
                        or "field" not in refusal
                        or (refusal["field"] is not None and type(refusal["field"]) is not str)):
                    raise _Invalid("MALFORMED_CORE_RESULT")
                return {**envelope, "status": "REFUSED", "outputs": {},
                        "refusal": {"code": "CORE_REFUSAL", "field": None,
                                    "message": "A requested mesh was refused."},
                        "core_refusal": copy.deepcopy(refusal)}
            if core.get("status") != "SUCCESS" or len(core["modes"]) != modes:
                raise _Invalid("MALFORMED_CORE_RESULT")
            observations = []
            for j, (mode, beta) in enumerate(zip(core["modes"], roots), 1):
                if (mode["mode_index"] != j or mode["xi"] != [i/n for i in range(n+1)]
                        or len(mode["normalized_deflection"]) != n+1
                        or len(mode["normalized_deflection_derivative_xi"]) != n+1
                        or mode["eigenvalue_dimensionless"] <= 0):
                    raise _Invalid("MALFORMED_CORE_RESULT")
                reference = [_reference(beta, i/n) for i in range(n+1)]
                error = math.sqrt(mode["eigenvalue_dimensionless"])/(beta*beta) - 1
                observations.append({"mode_index": j,
                    "dimensionless_frequency_relative_error": error,
                    "absolute_dimensionless_frequency_relative_error": abs(error),
                    "max_abs_nodal_shape_error": max(abs(u-r[0]) for u, r in zip(
                        mode["normalized_deflection"], reference)),
                    "max_abs_nodal_derivative_xi_error": max(abs(u-r[1]) for u, r in zip(
                        mode["normalized_deflection_derivative_xi"], reference))})
            meshes.append({"elements": n, "modes": observations})
        adjacent = []
        for coarse, fine in pairwise(meshes):
            adjacent.append({"coarse_elements": coarse["elements"],
                "fine_elements": fine["elements"], "modes": [
                    {"mode_index": c["mode_index"], "observed_frequency_order":
                     _observed_order(c["absolute_dimensionless_frequency_relative_error"],
                                     f["absolute_dimensionless_frequency_relative_error"],
                                     coarse["elements"], fine["elements"]),
                     "frequency_error_decreased": f["absolute_dimensionless_frequency_relative_error"]
                     < c["absolute_dimensionless_frequency_relative_error"]}
                    for c, f in zip(coarse["modes"], fine["modes"])]})
        outputs = {"reference": [{"mode_index": j, "beta": b,
                     "dimensionless_omega": b*b} for j, b in enumerate(roots, 1)],
                   "reference_representation": "finite binary approximation; no exact bound",
                   "order_interpretation": "observed only; nonnested meshes allowed; not certified",
                   "shape_interpretation": "absolute nodal diagnostics on different node sets",
                   "meshes": meshes, "adjacent": adjacent}
        if not _finite_json(outputs):
            raise _Invalid("NONFINITE_OBSERVATION")
        return {**envelope, "status": "SUCCESS", "outputs": outputs}
    except _Invalid as exc:
        refusal = {"code": exc.code, "field": exc.field,
                   "message": "Benchmark input or observation could not be represented."}
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        refusal = {"code": "MALFORMED_OR_NUMERICAL_FAILURE", "field": None,
                   "message": "Benchmark computation could not be completed."}
    return {**envelope, "status": "REFUSED", "refusal": refusal, "outputs": {}}
