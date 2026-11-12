"""Experimental local loads from prescribed section kinematics and a V132 polar."""

import math
from copy import deepcopy

from . import section_polar as _polar
from .hover_bemt import _normal
from .provenance import sha256_record

EVALUATION = "section_load_experimental"
SCHEMA_VERSION = "section_load_v1"
_SECTION_KEYS = (
    "axial_velocity_m_s tangential_velocity_m_s chord_m radius_m density_kg_m3 "
    "dynamic_viscosity_pa_s speed_of_sound_m_s pitch_rad blade_count"
)


def _require(condition):
    if not condition:
        raise ValueError("Invalid section load request")


def _walk(value, *, output=False):
    """Inspect exact builtins before invoking copy, hashing, or child code."""
    remaining = 32768

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        _require(remaining >= 0 and depth <= (16 if output else 10))
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


def _exact(actual, expected):
    """Full builtin type/value equality, including the sign of native float zero."""
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


def _number(value, *, zero=False):
    _require(type(value) in (int, float))
    number = float(value)
    _normal(number, zero=zero)
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
            _number(section[key], zero=key in ("axial_velocity_m_s", "pitch_rad"))
    _require(section["pitch_rad"] <= math.pi / 2)
    # V132 preflight validates every table, regardless of query coverage.
    _polar._preflight({"polar": request["polar"], "query": {
        "alpha_rad": 0, "reynolds_number": 1, "mach_number": 0,
    }})


def _checked(value):
    _normal(value, zero=True)
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


def _kinematics(section):
    wa, wt = float(section["axial_velocity_m_s"]), float(section["tangential_velocity_m_s"])
    phi = _checked(math.atan2(wa, wt))
    _require(phi != 0 or wa == 0)
    alpha = _sum(float(section["pitch_rad"]), -phi)
    speed = _checked(math.hypot(wa, wt))
    reynolds = _quotient(_product(_product(float(section["density_kg_m3"]), speed),
                                     float(section["chord_m"])), float(section["dynamic_viscosity_pa_s"]))
    mach = _quotient(speed, float(section["speed_of_sound_m_s"]))
    return {"phi_rad": phi, "relative_speed_m_s": speed}, {
        "alpha_rad": alpha, "reynolds_number": reynolds, "mach_number": mach,
    }


# Freeze accepted V132 metadata independently of subsequent child/helper changes.
_V132_CATALOG_RAW = _polar.section_polar_catalog()
_walk(_V132_CATALOG_RAW, output=True)
_V132_CATALOG = deepcopy(_V132_CATALOG_RAW)
del _V132_CATALOG_RAW
_CHILD_EXTRA = frozenset((
    "required_fields", "input_units", "output_field_units", "request_contract",
    "formulas", "status_matrix", "hash_contract",
))
_CHILD_KEYS = frozenset(_V132_CATALOG) - _CHILD_EXTRA
_JSON = {
    "max_nodes_including_keys": 32768, "max_depth": 10, "max_container_items": 256,
    "max_string_characters": 2000, "max_integer_bits": 1023, "root_depth": 1,
}
_LIMITS = {
    "input_json": _JSON,
    "output_json": {**_JSON, "max_depth": 16},
    "lookup_input_json": deepcopy(_V132_CATALOG["limits"]["input_json"]),
    "lookup_output_json": deepcopy(_V132_CATALOG["limits"]["output_json"]),
    "core_work": {"lookup_calls_max": 1, "blade_count_min": 1, "blade_count_max": 64},
}
_SOURCE_URLS = list(_V132_CATALOG["source_urls"])
_LIMITATIONS = [
    "Experimental prescribed local kinematics and caller polar only; no rotor or actuator closure.",
    "All polar source, classification, uncertainty and Mach applicability claims remain UNVERIFIED.",
    "No RPM-derived velocity, induction, nonlinear rotor solver, motor or mission integration.",
    "Signed local force and torque imply no windmill, reverse-flow, aircraft or feasibility qualification.",
    "Input bounds and binary64 checks establish no physical validity or numerical qualification.",
    "References describe formula conventions; they do not validate or authorize this implementation.",
    "No source or dataset is fetched during evaluation; no coefficient Mach correction is applied.",
    "Hashes bind full native JSON data, not source authenticity, execution attestation or runtime identity.",
    "Only fully guarded child results count; a domain refusal is an accepted result, not infeasibility.",
    "Unexpected child failure is sanitized as LOOKUP_BOUNDARY_FAILED; no child failure cause is trusted.",
    "Checked products, quotients and sums can refuse representational extremes; no full-range promise.",
]
_KINEMATIC_UNITS = {"phi_rad": "rad", "relative_speed_m_s": "m/s"}
_LOAD_UNITS = {
    "dynamic_pressure_pa": "Pa", "lift_density_n_m": "N/m", "drag_density_n_m": "N/m",
    "thrust_density_n_m": "N/m", "torque_density_nm_m": "N*m/m",
}


def _snapshot(value, *, child=False):
    # The child's own narrower output budget is also enforced independently.
    _walk(value, output=child)
    if child:
        _bounded_child(value)
    result = deepcopy(value)
    _walk(result, output=child)
    if child:
        _bounded_child(result)
    _exact(result, value)
    return result


def _bounded_child(value):
    remaining = 8192

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        _require(remaining >= 0 and depth <= 12)
        if type(item) is dict:
            for key, child in item.items():
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)

    visit(value, 1)


def _bracket(values, query):
    for index, value in enumerate(values):
        if query == value:
            return index, index
        if query < value:
            _require(index > 0)
            return index - 1, index
    raise ValueError("Unbracketed query")


def _weight(lo, hi, query, *, log=False):
    lo, hi, query = float(lo), float(hi), float(query)
    if log:
        def distance(value):
            fraction = (value - lo) / lo
            return (math.log1p(fraction) if math.isfinite(fraction) and fraction > 0
                    else math.log(value) - math.log(lo))
        weight = distance(query) / distance(hi)
    else:
        weight = (query - lo) / (hi - lo)
    _require(math.isfinite(weight) and 0 < weight < 1)
    return weight


def _mix(lo, hi, weight):
    return _sum(_product(float(lo), 1.0 - weight), _product(float(hi), weight))


def _expected_outputs(polar, query):
    """Pure scalar boundary reconstruction; never invokes a V132 numerical helper."""
    tables = polar["reynolds_tables"]
    alphas = [row["alpha_rad"] for row in tables[0]["rows"]]
    reynolds = [table["reynolds_number"] for table in tables]
    ai, aj = _bracket(alphas, query["alpha_rad"])
    ri, rj = _bracket(reynolds, query["reynolds_number"])
    aw = 0 if ai == aj else _weight(alphas[ai], alphas[aj], query["alpha_rad"])
    rw = 0 if ri == rj else _weight(reynolds[ri], reynolds[rj], query["reynolds_number"], log=True)
    corners, coefficients = [], []
    for ti, tw in ([(ri, 1)] if ri == rj else [(ri, 1 - rw), (rj, rw)]):
        rows = tables[ti]["rows"]
        coefficients.append({key: rows[ai][key] if ai == aj else _mix(rows[ai][key], rows[aj][key], aw)
                             for key in ("cl", "cd")})
        for row, weight in ([(ai, 1)] if ai == aj else [(ai, 1 - aw), (aj, aw)]):
            corner_weight = _product(tw, weight)
            _require(corner_weight > 0)
            corners.append({"table_index": ti, "row_index": row,
                            "reynolds_number": reynolds[ti], **rows[row], "weight": corner_weight})
    return {
        "query": deepcopy(query), "sampled_mach_number": polar["sampled_mach_number"],
        "declared_mach_interval": deepcopy(polar["declared_mach_interval"]),
        "mach_dependence": "NONE_DECLARED_APPLICABILITY_ONLY",
        **{key: coefficients[0][key] if ri == rj else _mix(coefficients[0][key], coefficients[1][key], rw)
           for key in ("cl", "cd")},
        "interpolation": {"alpha_indices": [ai, aj], "reynolds_indices": [ri, rj],
                          "alpha_weight": aw, "log_reynolds_weight": rw, "source_rows": corners},
    }


def _guard_lookup(actual, request):
    """Pure full child guard; accepts computed or exact expected domain refusal only."""
    _walk(actual, output=True)
    _bounded_child(actual)
    _walk(request)
    # Fresh catalog and frozen accepted metadata must agree, including status matrix,
    # units, source URLs, limitations and the full documented hash/schema contract.
    catalog = _snapshot(_polar.section_polar_catalog(), child=True)
    _exact(catalog, _V132_CATALOG)
    _require(type(actual) is dict and actual.keys() == _CHILD_KEYS)
    polar, query = request["polar"], request["query"]
    tables = polar["reynolds_tables"]
    domains = {
        "alpha_rad": (tables[0]["rows"][0]["alpha_rad"], tables[0]["rows"][-1]["alpha_rad"]),
        "reynolds_number": (tables[0]["reynolds_number"], tables[-1]["reynolds_number"]),
        "mach_number": polar["declared_mach_interval"],
    }
    axes = [axis for axis, (lo, hi) in domains.items() if not lo <= query[axis] <= hi]
    expected = {key: deepcopy(catalog[key]) for key in _CHILD_KEYS}
    expected.update(
        status="OUT_OF_POLAR_DOMAIN" if axes else "COMPUTED_EXPERIMENTAL",
        reasons=["OUT_OF_POLAR_DOMAIN"] if axes else [], out_of_domain_axes=axes,
        diagnostics_complete=not axes, request_sha256=sha256_record(request),
        outputs={} if axes else _expected_outputs(polar, query),
        output_units={} if axes else deepcopy(catalog["output_field_units"]),
    )
    expected["evaluation_sha256"] = sha256_record({
        key: value for key, value in expected.items() if key != "evaluation_sha256"})
    _exact(actual, expected)


def _loads(section, kinematics, coefficients):
    speed = kinematics["relative_speed_m_s"]
    # q = (.5*rho)*(W*W); each intermediate must be normal or exact zero.
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


def _output_units(ran=True):
    return {
        "kinematics": deepcopy(_KINEMATIC_UNITS),
        "actual_lookup_request": deepcopy(_V132_CATALOG["input_units"]),
        "actual_lookup_result": {"outputs": deepcopy(_V132_CATALOG["output_field_units"]) if ran else {}},
        "load_state": "label", "loads": deepcopy(_LOAD_UNITS) if ran else "not_applicable",
    }


def _response(status, reasons, digest=None, count=0):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "reasons": list(reasons), "outputs": {}, "output_units": {},
        "lookup_result_count": count, "diagnostics_complete": False,
        "physical_validation": "NOT_ESTABLISHED", "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED", "aircraft_status": None, "feasibility": None,
        "evidence_level": "unverified", "source_classification": "UNVERIFIED_CALLER_ASSERTION",
        "mach_interval_status": "UNVERIFIED_CALLER_APPLICABILITY_ONLY",
        "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS), "source_urls": list(_SOURCE_URLS),
        "request_sha256": digest, "evaluation_sha256": None,
    }


def _seal(response):
    _require(type(response["lookup_result_count"]) is int and 0 <= response["lookup_result_count"] <= 1)
    _walk(response, output=True)
    if response["request_sha256"] is not None:
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"})
    _walk(response, output=True)
    return response


def _failure(reason, digest=None, count=0):
    try:
        return _seal(_response("EXECUTION_FAILED", [reason], digest, count))
    except Exception:  # noqa: BLE001 -- persistent export failures remain sanitized.
        result = _response("EXECUTION_FAILED", [reason], count=count)
        _walk(result, output=True)
        return result


def evaluate_section_load(request):
    """Call the actual V132 evaluator once after full preflight and checked kinematics."""
    try:
        snapshot = _snapshot(request)
        _keys(snapshot, "evaluation polar section")
        _require(type(snapshot["evaluation"]) is str)
    except Exception:  # noqa: BLE001 -- no foreign copy/hash hooks or failure details.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    if snapshot["evaluation"] != EVALUATION:
        return _seal(_response("SOLVER_UNSUPPORTED", ["UNSUPPORTED_EVALUATION"]))
    try:
        _preflight(snapshot)
    except Exception:  # noqa: BLE001 -- all static input validation precedes lookup.
        return _seal(_response("MODEL_INAPPLICABLE", ["INVALID_REQUEST"]))
    digest, count = None, 0
    try:
        digest = sha256_record(snapshot)
        kinematics, query = _kinematics(snapshot["section"])
        child_request = {"evaluation": _V132_CATALOG["evaluation"],
                         "polar": deepcopy(snapshot["polar"]), "query": query}
        _walk(child_request)
        _polar._preflight(child_request)
    except Exception:  # noqa: BLE001 -- representational failures expose no partial kinematics.
        return _failure("SECTION_LOAD_EXECUTION_FAILED", digest)
    try:
        actual = _polar.evaluate_section_polar(deepcopy(child_request))
        retained = _snapshot(actual, child=True)
        _guard_lookup(retained, child_request)
        count = 1
    except Exception:  # noqa: BLE001 -- unexpected child statuses and malformed results are atomic.
        return _failure("LOOKUP_BOUNDARY_FAILED", digest)
    try:
        ran = retained["status"] == "COMPUTED_EXPERIMENTAL"
        loads = _loads(snapshot["section"], kinematics, retained["outputs"]) if ran else None
        response = _response("COMPUTED_EXPERIMENTAL", [], digest, count)
        response["outputs"] = {
            "kinematics": kinematics, "actual_lookup_request": child_request,
            "actual_lookup_result": retained,
            "load_state": "COMPUTED" if ran else "NOT_RUN_OUT_OF_POLAR_DOMAIN", "loads": loads,
        }
        response["output_units"] = _output_units(ran)
        response["diagnostics_complete"] = True
        return _seal(response)
    except Exception:  # noqa: BLE001 -- no partial loads or retained child on arithmetic/export failure.
        return _failure("SECTION_LOAD_EXECUTION_FAILED", digest, count)


def section_load_catalog():
    """Fresh local contract metadata; no evaluator call or source access."""
    result = {
        **_response("RESEARCH_ONLY", []),
        "required_fields": ["evaluation", "polar", "section"],
        "input_units": {
            "evaluation": "label", "polar": deepcopy(_V132_CATALOG["input_units"]["polar"]),
            "section": {
                "axial_velocity_m_s": "m/s", "tangential_velocity_m_s": "m/s", "chord_m": "m",
                "radius_m": "m", "density_kg_m3": "kg/m^3", "dynamic_viscosity_pa_s": "Pa*s",
                "speed_of_sound_m_s": "m/s", "pitch_rad": "rad", "blade_count": "1",
            },
        },
        "output_field_units": _output_units(),
        "status_matrix": {
            "RESEARCH_ONLY": "catalog only; zero accepted children; no hashes",
            "MODEL_INAPPLICABLE": "invalid bounded schema/static inputs; no hashes or child calls",
            "SOLVER_UNSUPPORTED": "exact bounded root with another evaluation string; no hashes or calls",
            "COMPUTED_EXPERIMENTAL": "one fully guarded child; computed loads or retained domain refusal",
            "EXECUTION_FAILED": "sanitized arithmetic/export or LOOKUP_BOUNDARY_FAILED; empty outputs/units",
        },
        "request_contract": {
            "json": "exact builtin bounded JSON before snapshot/copy/hash; exact keys; no defaults",
            "polar": (
                "exact V132 polar; all tables statically preflighted using a dummy query before kinematics"
            ),
            "section": (
                "Wa>=0, Wt,c,r,rho,mu,a>0; normal binary64; beta in [0,pi/2]; builtin blade_count 1..64"
            ),
            "native": "original native request snapshot hashed; checked derived query is binary64",
            "order": (
                "bounded snapshot, exact evaluation, full static preflight, hash, kinematics, "
                "derived preflight, one lookup, full guard, loads"
            ),
        },
        "formulas": {
            "kinematics": "phi=atan2(Wa,Wt); alpha=beta-phi; W=hypot(Wa,Wt); Re=rho*W*c/mu; Mach=W/a",
            "loads": (
                "q=.5*rho*W^2; L'=B*q*c*Cl; D'=B*q*c*Cd; "
                "T'=L'*(Wt/W)-D'*(Wa/W); Q'=r*(L'*(Wa/W)+D'*(Wt/W))"
            ),
            "convention": "positive axial thrust; positive resisting shaft torque; signed T' and Q' accepted",
            "reference": "Drela QPROP formulation equations 48-53; direct projection avoids Cd/Cl division",
            "arithmetic": (
                "checked normal-or-zero products/quotients/sums; nonzero underflow refused; "
                "exact cancellation allowed"
            ),
        },
        "boundary_contract": {
            "guard": (
                "fresh catalog exact against frozen V132 metadata; full native exact child response "
                "with independent interpolation reconstruction"
            ),
            "count": "0 until entire child accepted, then 1 including OOD; not attempts or attestation",
            "failure": (
                "unexpected child MODEL_INAPPLICABLE/EXECUTION_FAILED or any malformed payload "
                "=> LOOKUP_BOUNDARY_FAILED"
            ),
            "ood": "root COMPUTED_EXPERIMENTAL, loads null, NOT_RUN_OUT_OF_POLAR_DOMAIN, full child retained",
        },
        "hash_contract": {
            "request": (
                "SHA256 sorted compact UTF8 JSON of full original native validated snapshot; "
                "ensure_ascii=False, allow_nan=False"
            ),
            "evaluation": (
                "full bounded response excluding only evaluation_sha256; "
                "no authenticity/identity qualification"
            ),
            "exceptions": (
                "ordinary Exception sanitized; BaseException propagates; "
                "persistent hash failure clears both hashes"
            ),
        },
    }
    _walk(result, output=True)
    return result
