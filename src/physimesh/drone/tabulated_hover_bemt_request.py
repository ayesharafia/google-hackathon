"""Bounded JSON request adapter for the experimental tabulated hover kernel.

The request contract is a local engineering proposal, not an external standard.
Only ``evaluate_tabulated_hover_bemt`` executes the kernel, once per supported
strict JSON snapshot. Physical and geometry preflight belong to that kernel.
Digests describe data, never runtime identity, accuracy, or successful execution:
an inapplicable core request may have a request digest but no evaluation digest.
"""

import math
import sys
from copy import deepcopy
from dataclasses import asdict, fields

from .hover_bemt import _div, _mul, _normal, _positive_difference, _sum
from .provenance import sha256_record
from .tabulated_hover_bemt import (
    GeometryStation,
    TabulatedHoverSolution,
    solve_tabulated_hover,
)

EVALUATION = "tabulated_geometry_hover_experimental"
MODEL_ID = "tabulated_geometry_hover_v0_1"
SCHEMA_VERSION = "tabulated_hover_request_v1"

# Twelve required core kwargs, thirteen root fields including evaluation.
_CORE_KEYS = (
    "radius_m", "angular_speed_rad_s", "density_kg_m3", "blade_count",
    "root_cutout_m", "annuli", "lift_curve_slope_per_rad",
    "profile_drag_coefficient", "stations", "geometry_source", "geometry_kind",
    "uncertainty_status",
)
_REQUEST_KEYS = ("evaluation", *_CORE_KEYS)
_STATION_UNITS = {"radius_m": "m", "chord_m": "m", "blade_angle_rad": "rad"}
_INPUT_UNITS = {
    "evaluation": "label", "radius_m": "m", "angular_speed_rad_s": "rad/s",
    "density_kg_m3": "kg/m^3", "blade_count": "1", "root_cutout_m": "m",
    "annuli": "1", "lift_curve_slope_per_rad": "1/rad",
    "profile_drag_coefficient": "1", "stations": _STATION_UNITS,
    "geometry_source": "text", "geometry_kind": "label", "uncertainty_status": "text",
}
_ARRAY_UNITS = {
    "radii_m": "m", "chord_m": "m", "blade_angle_rad": "rad",
    "radial_fraction": "1", "local_solidity": "1", "inflow_ratio": "1",
    "approx_inflow_angle_rad": "rad", "approx_angle_of_attack_rad": "rad",
    "local_balance_coefficient": "1",
}
_SCALAR_UNITS = {
    "thrust_coefficient": "1", "blade_thrust_coefficient": "1",
    "induced_power_coefficient": "1", "profile_power_coefficient": "1",
    "shaft_power_coefficient": "1", "thrust_n": "N", "shaft_power_w": "W",
    "shaft_torque_nm": "N*m", "thrust_balance_coefficient": "1",
    "max_local_balance_coefficient": "1",
}
_OUTPUT_UNITS = {
    "radius_m": "m", "root_cutout_m": "m", "geometry_source": "text",
    "geometry_kind": "label", "uncertainty_status": "text", "stations": _STATION_UNITS,
    **_ARRAY_UNITS, **_SCALAR_UNITS, "annuli": "1",
}
# Dataclass markers are validated and moved to these envelope fields, once.
_MARKERS = {
    "model": ("core_model", "tabulated_geometry_hover_experimental"),
    "version": ("core_version", "0.1"),
    "status": ("core_status", "COMPUTED_EXPERIMENTAL"),
    "physical_validation": ("physical_validation", "NOT_ESTABLISHED"),
}
_SOLUTION_KEYS = frozenset((*_OUTPUT_UNITS, *_MARKERS))
_LIMITS = {
    "input_json": {
        "max_depth": 10, "max_nodes_including_keys": 8192,
        "max_container_items": 256, "max_string_characters": 2000,
        "max_integer_bits": 1023, "finite_floats_only": True,
        "valid_utf8_only": True, "root_depth": 1,
    },
    "core_work": {"stations_min": 2, "stations_max": 256, "annuli_min": 1,
                  "annuli_max": 2048, "blade_count_min": 1, "blade_count_max": 32},
    "output_json": {
        "max_depth": 10, "max_nodes_including_keys": 32768,
        "max_container_items": 2048, "max_string_characters": 2000,
        "max_integer_bits": 1023, "finite_floats_only": True,
        "valid_utf8_only": True, "root_depth": 1,
    },
}
_LIMITATIONS = (
    "Local engineering request proposal, not an external standard.",
    "Experimental isolated hover, small-angle attached linear lift; angle validity is not established.",
    "Tabulated geometry extends geometry representation only; no new physical accuracy is established.",
    "Geometry source, kind and uncertainty status are unverified caller assertions; no sources are fetched.",
    "Unknown uncertainty remains unknown; source classification does not establish evidence or accuracy.",
    "No Reynolds polars, stall, swirl, tip/root losses, Mach/compressibility or non-hover flight.",
    "No ground effects, rotor/aircraft interference, structural validation or aircraft qualification.",
    "Finite results, balance residuals and refinement do not establish physical or numerical qualification.",
    "Shaft power is mechanical power, not electrical input power; no electrical efficiency is modeled.",
    "Digests bind JSON data only; runtime identity and aircraft feasibility are not established.",
)


def _require(condition):
    if not condition:
        raise ValueError("Contract check failed")


def _json_walk(value, limits):
    """Bound strict builtin JSON before copying; count every value and key.

    No conversion methods on foreign objects are invoked. Cycles exceed the
    depth bound; repeated aliases count on every occurrence, as in JSON.
    """
    remaining = limits["max_nodes_including_keys"]

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        _require(remaining >= 0 and depth <= limits["max_depth"])
        kind = type(item)
        if kind is str:
            _require(len(item) <= limits["max_string_characters"])
            item.encode("utf-8", errors="strict")
        elif kind is int:
            _require(item.bit_length() <= limits["max_integer_bits"])
        elif kind is float:
            _require(math.isfinite(item))
        elif kind is dict:
            _require(len(item) <= limits["max_container_items"])
            for key, child in item.items():
                _require(type(key) is str)
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif kind is list:
            _require(len(item) <= limits["max_container_items"])
            for child in item:
                visit(child, depth + 1)
        else:
            _require(kind is bool or item is None)

    visit(value, limits["root_depth"])


def _response(status, reasons, request_digest=None):
    return {
        "evaluation": EVALUATION, "model_id": MODEL_ID, "schema_version": SCHEMA_VERSION,
        "status": status, "core_model": None, "core_version": None, "core_status": None,
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        "reasons": list(reasons), "limitations": list(_LIMITATIONS),
        "outputs": {}, "output_units": {}, "limits": deepcopy(_LIMITS),
        "request_sha256": request_digest, "evaluation_sha256": None,
    }


def _seal(response):
    """Validate outbound JSON under its own budget and hash without self-reference."""
    _json_walk(response, _LIMITS["output_json"])
    if response["request_sha256"] is not None and response["status"] in (
        "COMPUTED_EXPERIMENTAL", "EXECUTION_FAILED",
    ):
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"
        })
    return response


def tabulated_hover_bemt_catalog():
    """Return fresh nested metadata; all physical/declaration inputs are required."""
    return {
        **_response("RESEARCH_ONLY", []),
        "required_fields": list(_REQUEST_KEYS), "required_core_kwargs": list(_CORE_KEYS),
        "input_units": deepcopy(_INPUT_UNITS), "output_field_units": deepcopy(_OUTPUT_UNITS),
        "envelope_marker_units": {
            "core_model": "label", "core_version": "label", "core_status": "label",
            "physical_validation": "label",
        },
        "request_contract": {
            "extra_fields": "forbidden", "defaults": {},
            "root": "exact builtin dict; evaluation plus twelve required core kwargs",
            "json": "builtin dict/list/str/int/float/bool/null only; own input budget before copy",
            "physical_preflight": "core owns finite-normal numeric, geometry and work-bound validation",
            "numbers": "core physical numbers: builtin int/float, no bool; positive unless explicitly zero",
            "counts": "builtin int only: blade_count 1..32, annuli 1..2048",
            "geometry": {
                "stations": "builtin list of 2..256 exact radius_m/chord_m/blade_angle_rad dictionaries",
                "radius_m": "positive; strictly increasing stations in [0, radius_m]",
                "coverage": "first station <= root_cutout_m; last station == radius_m; no extrapolation",
                "root_cutout_m": "strictly between zero and radius_m; no hub geometry inferred",
                "chord_m": "positive", "blade_angle_rad": "nonnegative",
                "interpolation": "piecewise linear chord and blade angle independently at physical midpoints",
                "pitch": "blade angle in radians; constant pitch length is not constant blade angle",
            },
            "declarations": "nonblank builtin geometry_source/uncertainty_status strings, <=2000 characters",
            "source_classification": {
                "geometry_kind": ["measured", "digitized_measurement", "as_designed", "synthetic"],
                "meaning": "caller assertions only; no independently verified provenance",
                "uncertainty_status": "required caller text; unknown is not replaced or inferred",
            },
        },
        "interpretation": {
            "zero_blade_angle": "zero inflow, lift, thrust and induced power; profile drag may still consume power",
            "profile_drag_coefficient": "nonnegative constant; zero allowed; profile power is retained at zero angle",
            "lift_curve_slope_per_rad": "positive constant attached-linear slope; no airfoil or Re polars inferred",
            "local_solidity": "B*c(r)/(pi*R), normalized by rotor radius, not local radius",
            "coefficient_normalization": {
                "CT": "T/[rho*pi*R^2*(Omega*R)^2]",
                "CP": "P/[rho*pi*R^2*(Omega*R)^3]",
                "torque": "Q=P/Omega", "integration": "uniform physical midpoint annuli over cutout..R",
            },
            "residuals": "blade minus momentum; local integrands before annular width, global coefficients after sum",
            "units": "array units apply to every element; station dictionary units apply to every station; text/label are nonphysical",
            "scope": "geometry representation only; no inferred aircraft or additional physical qualification",
        },
        "response_contract": {
            "completed": "COMPUTED_EXPERIMENTAL only after actual returned contract validation",
            "invalid": "MODEL_INAPPLICABLE: strict request/shape/evaluation type or core numerical domain",
            "unsupported": "SOLVER_UNSUPPORTED: strict JSON exact root with a different evaluation string",
            "failed": "EXECUTION_FAILED: unexpected ordinary Exception or returned-contract/export failure",
            "base_exception": "propagates", "failure_outputs": "empty outputs and output_units; diagnostics_complete false",
            "marker_binding": "dataclass model/version/status/physical_validation moved to envelope exactly once",
            "request_sha256": "copied input after strict JSON/exact shape/supported evaluation, before the core call",
            "evaluation_sha256": "completed or execution-failed response including request_sha256, omitting evaluation_sha256 itself",
            "digest_encoding": "SHA256 UTF8 JSON; sorted keys, compact separators, ensure_ascii=False, allow_nan=False",
            "inapplicable_digest": "no digest before snapshot acceptance; core domain refusal may retain request hash, never evaluation hash",
            "null_hash": "no digest available; null is not a digest",
        },
    }


def _float(value, *, signed=False, positive=False):
    """Returned numbers must be builtin finite-normal binary64 values."""
    _require(type(value) is float)
    _normal(value, zero=not positive)
    if not signed:
        _require(value >= 0.0)
    if positive:
        _require(value > 0.0)


def _same(actual, expected):
    """Exact deterministic arithmetic binding, including the zero/nonzero branch."""
    _require(actual == expected)


def _interpolated(radial, left, right, name):
    """Check the prescribed interpolation, without running a hover model."""
    start, end = left[name], right[name]
    if radial == left["radius_m"]:
        return start
    if radial == right["radius_m"]:
        return end
    _require(left["radius_m"] < radial < right["radius_m"])
    span = _normal(right["radius_m"] - left["radius_m"])
    offset = _normal(radial - left["radius_m"])
    _normal(right["radius_m"] - radial)
    fraction = _div(offset, span)
    complement = _normal(1.0 - fraction)
    _require(0.0 < fraction < 1.0 and 0.0 < complement < 1.0)
    return start if start == end else _sum([_mul(complement, start), _mul(fraction, end)])


def _validate_solution(solution, request):
    """Check the actual typed result before exporting its JSON values.

    Identity, frozen declarations, exact fields, markers and numeric tuple
    members must pass before asdict can copy anything. The exported values
    then use the same independent JSON and governing checks as direct slices.
    """
    _require(type(solution) is TabulatedHoverSolution)
    _require(TabulatedHoverSolution.__dataclass_params__.frozen is True)
    _require({field.name for field in fields(solution)} == _SOLUTION_KEYS)
    _require(vars(solution).keys() == _SOLUTION_KEYS)
    for name, (_, marker) in _MARKERS.items():
        value = getattr(solution, name)
        _require(type(value) is str and value == marker)

    count = solution.annuli
    _require(type(count) is int and 1 <= count <= 2048)
    for name in ("radius_m", "root_cutout_m"):
        _float(getattr(solution, name), positive=True)
    for name in ("geometry_source", "geometry_kind", "uncertainty_status"):
        value = getattr(solution, name)
        _require(type(value) is str and bool(value.strip()) and len(value) <= 2000)
        value.encode("utf-8", errors="strict")
    stations = solution.stations
    _require(type(stations) is tuple and 2 <= len(stations) <= 256)
    _require(GeometryStation.__dataclass_params__.frozen is True)
    for station in stations:
        _require(type(station) is GeometryStation)
        _require({field.name for field in fields(station)} == _STATION_UNITS.keys())
        _require(vars(station).keys() == _STATION_UNITS.keys())
        for name in _STATION_UNITS:
            _float(getattr(station, name), positive=name == "chord_m")
    for name in _ARRAY_UNITS:
        array = getattr(solution, name)
        _require(type(array) is tuple and len(array) == count)
        for value in array:
            _float(value, signed=name == "local_balance_coefficient")
    for name in _SCALAR_UNITS:
        _float(getattr(solution, name), signed=name == "thrust_balance_coefficient")

    values = _export_solution(solution)
    _validate_output_values(values, request)
    return values


def _validate_output_values(values, request):
    """Validate an actual JSON output slice against the request fields it uses.

    No dataclass, marker or response envelope is synthesized. This checks
    returned inflow with the governing balance, without solving or rerunning
    any model. Exact bindings preserve the accepted arithmetic operation order.
    Whole-request admission, envelope markers and hashes remain separate.
    """
    _require(type(values) is dict)
    _json_walk(values, _LIMITS["output_json"])
    _require(values.keys() == _OUTPUT_UNITS.keys())
    _require(type(request) is dict and set(_CORE_KEYS) <= request.keys())
    count = values["annuli"]
    _require(type(count) is int and 1 <= count <= 2048)
    _require(type(request["annuli"]) is int and count == request["annuli"])
    for name in ("radius_m", "root_cutout_m"):
        value = values[name]
        _float(value, positive=True)
        _require(type(request[name]) in (int, float))
        _same(value, float(request[name]))
    _require(values["root_cutout_m"] < values["radius_m"])
    for name in ("geometry_source", "geometry_kind", "uncertainty_status"):
        value = values[name]
        _require(type(value) is str and type(request[name]) is str and value == request[name])
        _require(bool(value.strip()) and len(value) <= 2000)
        value.encode("utf-8", errors="strict")
    _require(values["geometry_kind"] in ("measured", "digitized_measurement", "as_designed", "synthetic"))

    stations = values["stations"]
    _require(type(stations) is list and 2 <= len(stations) <= 256)
    supplied = request["stations"]
    _require(type(supplied) is list and len(stations) == len(supplied))
    previous = None
    for station, original in zip(stations, supplied, strict=True):
        _require(type(station) is dict and station.keys() == _STATION_UNITS.keys())
        _require(type(original) is dict and original.keys() == _STATION_UNITS.keys())
        for name in _STATION_UNITS:
            value = station[name]
            _float(value, positive=name == "chord_m")
            _require(type(original[name]) in (int, float))
            _same(value, float(original[name]))
        _require(station["radius_m"] <= values["radius_m"])
        fraction = _div(station["radius_m"], values["radius_m"])
        if previous is not None:
            _require(station["radius_m"] > previous["radius_m"])
            _normal(station["radius_m"] - previous["radius_m"])
            _require(fraction > _div(previous["radius_m"], values["radius_m"]))
        previous = station
    _require(stations[0]["radius_m"] <= values["root_cutout_m"])
    _same(stations[-1]["radius_m"], values["radius_m"])

    for name in _ARRAY_UNITS:
        array = values[name]
        _require(type(array) is list and len(array) == count)
        for value in array:
            _float(value, signed=name == "local_balance_coefficient")
    for name in _SCALAR_UNITS:
        _float(values[name], signed=name == "thrust_balance_coefficient")

    # Only reached after the actual core call. These are contract checks, not
    # adapter-side physical preflight or a second call with dummy geometry.
    for name in ("angular_speed_rad_s", "density_kg_m3", "lift_curve_slope_per_rad"):
        _require(type(request[name]) in (int, float))
        _float(float(request[name]), positive=True)
    _require(type(request["profile_drag_coefficient"]) in (int, float))
    _float(float(request["profile_drag_coefficient"]))
    blades = request["blade_count"]
    _require(type(blades) is int and 1 <= blades <= 32)
    _validate_governing(values, request)


def _validate_governing(values, request):
    """Bind interpolation, balances, quadrature and SI normalization to inputs."""
    radius, cutout, count = values["radius_m"], values["root_cutout_m"], values["annuli"]
    omega = float(request["angular_speed_rad_s"])
    density = float(request["density_kg_m3"])
    slope = float(request["lift_curve_slope_per_rad"])
    drag = float(request["profile_drag_coefficient"])
    blades = float(request["blade_count"])
    cutout_fraction = _div(cutout, radius)
    _require(0.0 < cutout_fraction < 1.0)
    width_m = _div(_normal(radius - cutout), float(count))
    width = _div(width_m, radius)
    circumference = _mul(math.pi, radius)
    momentum_terms, blade_terms, induced_terms, profile_terms = [], [], [], []
    segment = 0
    for index in range(count):
        radial_m = values["radii_m"][index]
        radial = values["radial_fraction"][index]
        _same(radial_m, _normal(cutout + _mul(index + 0.5, width_m)))
        _same(radial, _div(radial_m, radius))
        left_edge = _normal(cutout + _mul(float(index), width_m))
        right_edge = (radius if index + 1 == count
                      else _normal(cutout + _mul(float(index + 1), width_m)))
        _require(left_edge < radial_m < right_edge)
        _require(_div(left_edge, radius) < radial < _div(right_edge, radius))
        while segment < len(values["stations"]) - 2 and radial_m > values["stations"][segment + 1]["radius_m"]:
            segment += 1
        left, right = values["stations"][segment:segment + 2]
        chord, theta = values["chord_m"][index], values["blade_angle_rad"][index]
        _same(chord, _interpolated(radial_m, left, right, "chord_m"))
        _same(theta, _interpolated(radial_m, left, right, "blade_angle_rad"))
        solidity = values["local_solidity"][index]
        _same(solidity, _div(_mul(blades, chord), circumference))
        blade_factor = _div(_mul(solidity, slope), 2.0)
        profile_factor = _div(_mul(solidity, drag), 2.0)
        inflow = values["inflow_ratio"][index]
        if theta == 0.0:
            _same(inflow, 0.0)
        else:
            _require(inflow > 0.0)
        angle = _div(inflow, radial)
        _same(values["approx_inflow_angle_rad"][index], angle)
        _same(values["approx_angle_of_attack_rad"][index], _positive_difference(theta, angle))
        radial_squared = _mul(radial, radial)
        momentum = _mul(_mul(4.0, _mul(inflow, inflow)), radial)
        theta_term = _mul(theta, radial_squared)
        inflow_term = _mul(inflow, radial)
        blade = _mul(blade_factor, _positive_difference(theta_term, inflow_term))
        local_balance = _normal(blade - momentum, zero=True)
        _same(values["local_balance_coefficient"][index], local_balance)
        # Roundoff scale uses the operands before cancellation. This numerical
        # identity guard is not a tolerance on physical accuracy or residuals.
        balance_scale = max(abs(_mul(blade_factor, theta_term)),
                            abs(_mul(blade_factor, inflow_term)), abs(momentum))
        _require(abs(local_balance) <= (64.0 * sys.float_info.epsilon) * balance_scale)
        momentum_terms.append(_mul(momentum, width))
        blade_terms.append(_mul(blade, width))
        induced_terms.append(_mul(_mul(momentum, inflow), width))
        profile_terms.append(_mul(_mul(profile_factor, _mul(radial_squared, radial)), width))

    _same(values["thrust_coefficient"], _sum(momentum_terms))
    _same(values["blade_thrust_coefficient"], _sum(blade_terms))
    _same(values["induced_power_coefficient"], _sum(induced_terms))
    _same(values["profile_power_coefficient"], _sum(profile_terms))
    _same(values["shaft_power_coefficient"],
          _sum([values["induced_power_coefficient"], values["profile_power_coefficient"]]))
    _same(values["thrust_balance_coefficient"],
          _normal(values["blade_thrust_coefficient"] - values["thrust_coefficient"], zero=True))
    _same(values["max_local_balance_coefficient"],
          max(abs(balance) for balance in values["local_balance_coefficient"]))
    area = _mul(math.pi, _mul(radius, radius))
    tip_speed = _mul(omega, radius)
    thrust_scale = _mul(_mul(density, area), _mul(tip_speed, tip_speed))
    power_scale = _mul(thrust_scale, tip_speed)
    _same(values["thrust_n"], _mul(thrust_scale, values["thrust_coefficient"]))
    _same(values["shaft_power_w"], _mul(power_scale, values["shaft_power_coefficient"]))
    _same(values["shaft_torque_nm"], _div(values["shaft_power_w"], omega))


def _export_solution(solution):
    """Copy the actual typed result after the wrapper's structural checks."""
    _require(type(solution) is TabulatedHoverSolution)
    values = asdict(solution)
    for name in _MARKERS:
        del values[name]
    values["stations"] = list(values["stations"])
    for name in _ARRAY_UNITS:
        values[name] = list(values[name])
    _require(values.keys() == _OUTPUT_UNITS.keys())
    _json_walk(values, _LIMITS["output_json"])
    return values


def evaluate_tabulated_hover_bemt(request):
    """Evaluate one bounded explicit JSON request, with atomic failure outputs.

    BaseException is deliberately not caught. Invalid physical/numerical inputs
    are classified only by the actual core; no dry run or default is supplied.
    Input and result digests reuse the accepted provenance encoding.
    """
    try:
        _json_walk(request, _LIMITS["input_json"])
        snapshot = deepcopy(request)
        # Validate the copied snapshot too, before hashing or passing any data
        # to the core. The first walk already bounded copying work.
        _json_walk(snapshot, _LIMITS["input_json"])
        _require(type(snapshot) is dict and snapshot.keys() == set(_REQUEST_KEYS))
        _require(type(snapshot["evaluation"]) is str)
    except ValueError:
        return _response("MODEL_INAPPLICABLE", ["Invalid strict JSON request or exact root shape."])
    except Exception:  # noqa: BLE001 -- never export ordinary exception text.
        return _response("EXECUTION_FAILED", ["Request snapshot failed."])
    if snapshot["evaluation"] != EVALUATION:
        return _response("SOLVER_UNSUPPORTED", ["Unsupported evaluation."])

    request_digest = None
    try:
        request_digest = sha256_record(snapshot)
        # Keep the hashed snapshot separate even if a replacement core mutates
        # its arguments. Output binding always uses the original snapshot.
        arguments = deepcopy({name: snapshot[name] for name in _CORE_KEYS})
    except Exception:  # noqa: BLE001
        return _seal(_response("EXECUTION_FAILED", ["Request preparation failed."], request_digest))

    try:
        solution = solve_tabulated_hover(**arguments)
    except (ValueError, TypeError, ArithmeticError):
        return _response("MODEL_INAPPLICABLE", [
            "Request is outside the core input or numerical domain.",
        ], request_digest)
    except Exception:  # noqa: BLE001
        return _seal(_response("EXECUTION_FAILED", ["Core execution failed."], request_digest))

    try:
        outputs = _validate_solution(solution, snapshot)
        response = _response("COMPUTED_EXPERIMENTAL", [], request_digest)
        response.update(
            outputs=outputs, output_units=deepcopy(_OUTPUT_UNITS), diagnostics_complete=True,
        )
        for name, (envelope_name, _) in _MARKERS.items():
            response[envelope_name] = getattr(solution, name)
        return _seal(response)
    except Exception:  # noqa: BLE001 -- discard every partial output/marker/hash.
        return _seal(_response("EXECUTION_FAILED", ["Core result contract failed."], request_digest))
