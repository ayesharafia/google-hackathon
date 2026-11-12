"""Bounded, local experimental section polar lookup; no source fetching or solver."""

import math
import sys
from copy import deepcopy

from .hover_bemt import _normal
from .provenance import sha256_record

EVALUATION = "section_polar_lookup_experimental"
SCHEMA_VERSION = "section_polar_lookup_v1"
_INPUT_LIMIT = 32768
_OUTPUT_LIMIT = 8192


def _require(condition):
    if not condition:
        raise ValueError("Invalid section polar request")


def _walk(value, *, output=False):
    remaining = _OUTPUT_LIMIT if output else _INPUT_LIMIT

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        _require(remaining >= 0 and depth <= (12 if output else 10))
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
            for key, child in item.items():
                _require(type(key) is str)
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif kind is list:
            _require(len(item) <= 256)
            for child in item:
                visit(child, depth + 1)
        else:
            _require(kind is bool or item is None)

    visit(value, 1)


def _keys(value, keys):
    _require(type(value) is dict and set(value) == set(keys.split()))


def _number(value, *, positive=False, nonnegative=False, alpha=False, normal=True):
    _require(type(value) in (int, float))
    number = float(value)
    _require(math.isfinite(number) and (not normal or number == 0 or abs(number) >= sys.float_info.min))
    _require(not positive or number > 0)
    _require(not nonnegative or number >= 0)
    _require(not alpha or -math.pi <= value <= math.pi)
    return number


def _preflight(request):
    polar, query = request["polar"], request["query"]
    _keys(
        polar,
        "airfoil_id source source_kind uncertainty_status sampled_mach_number "
        "declared_mach_interval reynolds_tables",
    )
    for key in ("airfoil_id", "source", "source_kind", "uncertainty_status"):
        value = polar[key]
        _require(
            type(value) is str
            and bool(value.strip())
            and len(value) <= (128 if key == "airfoil_id" else 2000)
        )
    _require(polar["source_kind"] in ("measured", "digitized_measurement", "computed", "synthetic"))
    _number(polar["sampled_mach_number"], nonnegative=True, normal=False)
    interval = polar["declared_mach_interval"]
    _require(type(interval) is list and len(interval) == 2)
    for value in interval:
        _number(value, nonnegative=True, normal=False)
    _require(interval[0] <= polar["sampled_mach_number"] <= interval[1])
    tables = polar["reynolds_tables"]
    _require(type(tables) is list and 1 <= len(tables) <= 8)
    grid = None
    previous = None
    for table in tables:
        _keys(table, "reynolds_number rows")
        re = table["reynolds_number"]
        _number(re, positive=True)
        _require(previous is None or previous < re)
        previous = re
        rows = table["rows"]
        _require(type(rows) is list and 2 <= len(rows) <= 256)
        current = []
        for row in rows:
            _keys(row, "alpha_rad cl cd")
            _number(row["alpha_rad"], alpha=True)
            _number(row["cl"])
            _number(row["cd"], nonnegative=True)
            _require(not current or current[-1] < row["alpha_rad"])
            current.append(row["alpha_rad"])
        if grid is not None:
            _require(
                len(grid) == len(current)
                and all(
                    type(a) is type(b) and a == b and (a != 0 or math.copysign(1, a) == math.copysign(1, b))
                    for a, b in zip(grid, current, strict=True)
                )
            )
        grid = current
    _keys(query, "alpha_rad reynolds_number mach_number")
    _number(query["alpha_rad"], alpha=True)
    _number(query["reynolds_number"], positive=True)
    _number(query["mach_number"], nonnegative=True, normal=False)


def _bracket(values, query):
    for index, value in enumerate(values):
        if query == value:
            return index, index
        if query < value:
            return index - 1, index
    raise ArithmeticError("Unbracketed query")


def _checked(value):
    _normal(value, zero=True)
    return value


def _mix(left, right, weight):
    # Refuse underflow of any nonzero contribution; true exact cancellation is allowed.
    a = _checked(float(left) * (1.0 - weight))
    b = _checked(float(right) * weight)
    if (left != 0 and a == 0) or (right != 0 and b == 0):
        raise ArithmeticError("Unrepresentable contribution")
    result = _checked(math.fsum((a, b)))
    if result == 0 and a != -b:
        raise ArithmeticError("Unrepresentable sum")
    return result


def _weight(lo, hi, query, *, logarithmic=False):
    lo, hi, query = float(lo), float(hi), float(query)
    if logarithmic:

        def distance(value):
            fraction = (value - lo) / lo
            return (
                math.log1p(fraction)
                if math.isfinite(fraction) and fraction > 0
                else math.log(value) - math.log(lo)
            )

        weight = distance(query) / distance(hi)
    else:
        weight = (query - lo) / (hi - lo)
    _require(math.isfinite(weight) and 0 < weight < 1)
    return weight


def _lookup(polar, query):
    tables = polar["reynolds_tables"]
    alphas = [row["alpha_rad"] for row in tables[0]["rows"]]
    reynolds = [table["reynolds_number"] for table in tables]
    ai, aj = _bracket(alphas, query["alpha_rad"])
    ri, rj = _bracket(reynolds, query["reynolds_number"])
    aw = 0 if ai == aj else _weight(alphas[ai], alphas[aj], query["alpha_rad"])
    rw = 0 if ri == rj else _weight(reynolds[ri], reynolds[rj], query["reynolds_number"], logarithmic=True)
    corners = []
    by_table = []
    for ti, tw in [(ri, 1)] if ri == rj else [(ri, 1 - rw), (rj, rw)]:
        rows = tables[ti]["rows"]
        by_table.append(
            {
                key: rows[ai][key] if ai == aj else _mix(rows[ai][key], rows[aj][key], aw)
                for key in ("cl", "cd")
            }
        )
        for row_index, alpha_weight in [(ai, 1)] if ai == aj else [(ai, 1 - aw), (aj, aw)]:
            weight = _checked(tw * alpha_weight)
            if weight <= 0:
                raise ArithmeticError("Unrepresentable corner weight")
            corners.append(
                {
                    "table_index": ti,
                    "row_index": row_index,
                    "reynolds_number": reynolds[ti],
                    **rows[row_index],
                    "weight": weight,
                }
            )
    coefficients = {
        key: by_table[0][key] if ri == rj else _mix(by_table[0][key], by_table[1][key], rw)
        for key in ("cl", "cd")
    }
    return {
        "query": deepcopy(query),
        "sampled_mach_number": polar["sampled_mach_number"],
        "declared_mach_interval": deepcopy(polar["declared_mach_interval"]),
        "mach_dependence": "NONE_DECLARED_APPLICABILITY_ONLY",
        **coefficients,
        "interpolation": {
            "alpha_indices": [ai, aj],
            "reynolds_indices": [ri, rj],
            "alpha_weight": aw,
            "log_reynolds_weight": rw,
            "source_rows": corners,
        },
    }


def evaluate_section_polar(request):
    """Validate all tables, then look up a single query in the caller's domain."""
    try:
        _walk(request)
        snapshot = deepcopy(request)
        _walk(snapshot)
        _require(type(snapshot) is dict and snapshot == request)
        _keys(snapshot, "evaluation polar query")
        _require(type(snapshot["evaluation"]) is str)
    except Exception:  # noqa: BLE001 -- sanitize ordinary failures; BaseException propagates.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    if snapshot["evaluation"] != EVALUATION:
        return _seal(_response("SOLVER_UNSUPPORTED", ["UNSUPPORTED_EVALUATION"]))
    try:
        _preflight(snapshot)
    except Exception:  # noqa: BLE001 -- sanitize ordinary failures; BaseException propagates.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    try:
        digest = sha256_record(snapshot)
        response = _response("COMPUTED_EXPERIMENTAL", [], digest)
        polar, query = snapshot["polar"], snapshot["query"]
        tables = polar["reynolds_tables"]
        domains = {
            "alpha_rad": (tables[0]["rows"][0]["alpha_rad"], tables[0]["rows"][-1]["alpha_rad"]),
            "reynolds_number": (tables[0]["reynolds_number"], tables[-1]["reynolds_number"]),
            "mach_number": polar["declared_mach_interval"],
        }
        axes = [axis for axis, (lo, hi) in domains.items() if not lo <= query[axis] <= hi]
        if axes:
            response["status"] = "OUT_OF_POLAR_DOMAIN"
            response["reasons"] = ["OUT_OF_POLAR_DOMAIN"]
            response["out_of_domain_axes"] = axes
        else:
            response["outputs"] = _lookup(polar, query)
            response["output_units"] = deepcopy(_OUTPUT_UNITS)
            response["diagnostics_complete"] = True
        return _seal(response)
    except Exception:  # noqa: BLE001 -- sanitize ordinary failures; BaseException propagates.
        return _execution_failure(locals().get("digest"))


_QUERY_UNITS = {"alpha_rad": "rad", "reynolds_number": "1", "mach_number": "1"}
_ROW_UNITS = {"alpha_rad": "rad", "cl": "1", "cd": "1"}
_OUTPUT_UNITS = {
    "query": _QUERY_UNITS,
    "sampled_mach_number": "1",
    "declared_mach_interval": "1",
    "mach_dependence": "label",
    "cl": "1",
    "cd": "1",
    "interpolation": {
        "alpha_indices": "1",
        "reynolds_indices": "1",
        "alpha_weight": "1",
        "log_reynolds_weight": "1",
        "source_rows": {
            "table_index": "1",
            "row_index": "1",
            "reynolds_number": "1",
            **_ROW_UNITS,
            "weight": "1",
        },
    },
}
_LIMITS = {
    "input_json": {
        "max_nodes_including_keys": 32768,
        "max_depth": 10,
        "max_container_items": 256,
        "max_string_characters": 2000,
        "max_integer_bits": 1023,
        "root_depth": 1,
    },
    "output_json": {
        "max_nodes_including_keys": 8192,
        "max_depth": 12,
        "max_container_items": 256,
        "max_string_characters": 2000,
        "max_integer_bits": 1023,
        "root_depth": 1,
    },
    "tables": {"min": 1, "max": 8, "rows_min": 2, "rows_max": 256},
}
_SOURCE_URLS = [
    "https://openfast.readthedocs.io/en/main/source/user/aerodyn/input.html",
    "https://web.mit.edu/drela/Public/web/qprop/qprop_theory.pdf",
]
_LIMITATIONS = [
    "Local engineering request proposal; references do not authorize or validate this implementation.",
    "Source identity, classification and uncertainty are unverified caller assertions; no source is fetched.",
    "Declared Mach interval is UNVERIFIED caller applicability scope, not measured coverage.",
    "No coefficient Mach dependence or correction; sampled Mach is explicit metadata only.",
    "Reynolds samples are explicit points, not independently established continuous coverage.",
    "No inferred stall, 360-degree extension, compressibility, rotation or hysteresis.",
    "Alpha bounds [-pi, pi] restrict the local data domain; they establish no physical validity.",
    "No nonlinear BEMT, rotor solution, physical validation, aircraft verdict or feasibility claim.",
    "Finite values and interpolation checks establish neither physical nor numerical qualification.",
    "Binary64 interpolation may refuse numerical extremes; full numeric dynamic range is not promised.",
    "Hashes bind JSON data, not source authenticity, runtime identity or scientific accuracy.",
]


def _response(status, reasons, digest=None):
    return {
        "evaluation": EVALUATION,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "reasons": list(reasons),
        "outputs": {},
        "output_units": {},
        "out_of_domain_axes": [],
        "diagnostics_complete": False,
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "evidence_level": "unverified",
        "source_classification": "UNVERIFIED_CALLER_ASSERTION",
        "mach_interval_status": "UNVERIFIED_CALLER_APPLICABILITY_ONLY",
        "limitations": list(_LIMITATIONS),
        "limits": deepcopy(_LIMITS),
        "source_urls": list(_SOURCE_URLS),
        "request_sha256": digest,
        "evaluation_sha256": None,
    }


def _seal(response):
    _walk(response, output=True)
    if response["request_sha256"] is not None and response["status"] in (
        "COMPUTED_EXPERIMENTAL",
        "OUT_OF_POLAR_DOMAIN",
        "EXECUTION_FAILED",
    ):
        response["evaluation_sha256"] = sha256_record(
            {key: value for key, value in response.items() if key != "evaluation_sha256"}
        )
    _walk(response, output=True)
    return response


def _execution_failure(digest=None):
    """Keep a persistent digest/export failure from leaking an ordinary exception."""
    response = _response("EXECUTION_FAILED", ["LOOKUP_EXECUTION_FAILED"], digest)
    try:
        return _seal(response)
    except Exception:  # noqa: BLE001 -- persistent export failure must remain sanitized.
        response = _response("EXECUTION_FAILED", ["LOOKUP_EXECUTION_FAILED"])
        _walk(response, output=True)
        return response


def section_polar_catalog():
    """Fresh metadata only; never calls the evaluator or fetches a source."""
    result = {
        **_response("RESEARCH_ONLY", []),
        "required_fields": ["evaluation", "polar", "query"],
        "input_units": {
            "evaluation": "label",
            "query": deepcopy(_QUERY_UNITS),
            "polar": {
                "airfoil_id": "text",
                "source": "text",
                "source_kind": "label",
                "uncertainty_status": "text",
                "sampled_mach_number": "1",
                "declared_mach_interval": "1",
                "reynolds_tables": {
                    "reynolds_number": "1",
                    "rows": deepcopy(_ROW_UNITS),
                },
            },
        },
        "output_field_units": deepcopy(_OUTPUT_UNITS),
        "request_contract": {
            "extra_fields": "forbidden at every schema dictionary; no defaults",
            "json": "exact builtin JSON types, finite floats, UTF8, bounded before deepcopy and hashing",
            "numbers": (
                "builtin int/float only, no bool or subclasses; Re positive normal; alpha/cl "
                "signed normal or zero; cd nonnegative normal or zero; Mach finite nonnegative"
            ),
            "alpha_domain": "[-pi, pi] radians; strictly increasing rows",
            "grid": "all tables identical numeric values, builtin types and zero signs (full_exact)",
            "reynolds": (
                "1..8 strictly increasing samples; a single sample accepts only exact numeric equality"
            ),
            "rows": "2..256 exact alpha_rad/cl/cd dictionaries per table",
            "declarations": "nonblank builtin strings <=2000 characters; airfoil_id <=128",
            "source_kind": ["measured", "digitized_measurement", "computed", "synthetic"],
            "mach": (
                "two finite nonnegative ordered bounds including sampled_mach_number; "
                "unverified applicability only"
            ),
            "validation_order": (
                "strict bounded snapshot, exact root/evaluation, all tables and query, hash, "
                "coverage, interpolation"
            ),
        },
        "formulas": {
            "alpha_weight": "(alpha-alpha_lo)/(alpha_hi-alpha_lo)",
            "log_reynolds_weight": "log(Re/Re_lo)/log(Re_hi/Re_lo)",
            "log_branch": (
                "log1p((value-lo)/lo) when fraction is finite and positive, otherwise "
                "log(value)-log(lo), independently for numerator and denominator"
            ),
            "coefficients": "linear alpha within each bracket table, then linear log(Re) between tables",
            "knots": "lo=hi, weight=0; exact alpha/Re knot coefficients retain native builtin type and value",
            "corners": "unique 1/2/4 rows; positive product weights; no duplicate or zero-weight corners",
            "arithmetic": (
                "binary64 checked convex combinations; refuse nonfinite/subnormal results, "
                "nonzero contribution underflow and interior weights rounded to endpoints"
            ),
            "cancellation": (
                "zero lift from exactly opposite rounded contributions is permitted; see "
                "documentation for numeric policy"
            ),
            "indices": "zero based source table/row indices; all indices and weights dimensionless",
        },
        "status_matrix": {
            "RESEARCH_ONLY": "catalog metadata; no evaluation or hashes",
            "MODEL_INAPPLICABLE": "invalid JSON/schema/numeric input; both hashes null",
            "SOLVER_UNSUPPORTED": (
                "strict bounded exact root with a different builtin evaluation string; both hashes null"
            ),
            "OUT_OF_POLAR_DOMAIN": (
                "valid recognized snapshot outside alpha/Re/declared Mach; explicit axes, "
                "empty outputs, both hashes"
            ),
            "COMPUTED_EXPERIMENTAL": "checked interpolation; outputs and units, both hashes",
            "EXECUTION_FAILED": (
                "sanitized ordinary execution/export failure; empty outputs; hashes when "
                "snapshot hashing succeeded"
            ),
        },
        "hash_contract": {
            "request": (
                "full validated strict builtin snapshot; sorted compact UTF8 JSON, "
                "ensure_ascii=False, allow_nan=False; SHA256"
            ),
            "evaluation": (
                "full response including request hash, omitting only evaluation_sha256; "
                "bounded walk before and after seal"
            ),
            "meaning": "data binding only; no source digest or authenticity assertion",
            "exceptions": "ordinary Exception sanitized; BaseException propagates",
        },
    }
    _walk(result, output=True)
    return result
