"""V142 disk pressure jump derived solely from retained annulus thrust."""

import math
from copy import deepcopy as _deepcopy

from . import polar_rotor as _rotor
from .provenance import sha256_record as _sha256_record

__all__ = ["derive_disk_pressure"]

_EVALUATION = "polar_rotor_disk_pressure"
_SCHEMA_VERSION = "polar_rotor_disk_pressure_v1"
_DERIVATION = "ACTUATOR_DISK_IDENTITY_FROM_INTEGRATED_ANNULUS_THRUST"
_STATE_TEXT = (
    "This is a derived IDEALIZED ACTUATOR-DISK quantity from integrated annulus thrust, "
    "expressed as a derived disk pressure jump; NOT surface pressure, NOT a solved or CFD pressure field. "
    "It carries no spatial/vector information beyond the axisymmetric annulus it derives from. "
    "The full-disk mean spreads thrust over the whole disk including any inner hole; "
    "the active-annular mean spreads it only over the modeled annuli. "
    "Their averaging areas differ whenever the innermost radius > 0; "
    "for nonzero total thrust, the means differ."
)
_require = _rotor._require
_exact = _rotor._exact
_keys = _rotor._keys
_checked = _rotor._checked
_product = _rotor._product
_sum = _rotor._sum
_COUNTS = ("section_solve_result_count", "residual_result_count",
           "load_result_count", "lookup_result_count")


def _number(value):
    _require(type(value) in (int, float))
    return _checked(float(value))


def _digest(value):
    _require(type(value) is str and len(value) == 64)
    _require(all(character in "0123456789abcdef" for character in value))


def _preflight(snapshot):
    """Guard the sealed envelope and every consumed field before derivation."""
    base = _rotor._response("COMPUTED_EXPERIMENTAL", [])
    _require(type(snapshot) is dict and snapshot.keys() == base.keys())
    variable = {*_COUNTS, "outputs", "output_units", "request_sha256", "evaluation_sha256",
                "diagnostics_complete"}
    for key in base.keys() - variable:
        _exact(snapshot[key], base[key])
    _exact(snapshot["diagnostics_complete"], True)
    _digest(snapshot["request_sha256"])
    _digest(snapshot["evaluation_sha256"])
    _exact(snapshot["evaluation_sha256"], _sha256_record({
        key: value for key, value in snapshot.items() if key != "evaluation_sha256"}))
    output = snapshot["outputs"]
    _keys(output, "rotor_state annuli integrated")
    _exact(output["rotor_state"], "COMPUTED")
    rows, integrated = output["annuli"], output["integrated"]
    _require(type(rows) is list and 1 <= len(rows) <= 8)
    _keys(integrated, "integration_method contributions totals")
    _exact(integrated["integration_method"], "MIDPOINT_PRESCRIBED_ANNULI")
    contributions, totals = integrated["contributions"], integrated["totals"]
    _require(type(contributions) is list and len(contributions) == len(rows))
    _keys(totals, "thrust_n torque_nm shaft_power_w")
    for value in totals.values():
        _number(value)
    for key in _COUNTS:
        _require(type(snapshot[key]) is int)
    _require(snapshot[_COUNTS[0]] == len(rows))
    residuals = snapshot[_COUNTS[1]]
    _require(len(rows) <= residuals <= 16 * len(rows))
    _require(snapshot[_COUNTS[2]] == snapshot[_COUNTS[3]] == residuals)
    for index, (row, contribution) in enumerate(zip(rows, contributions, strict=True)):
        _keys(row, "annulus_index radial_inner_m radial_outer_m midpoint_radius_m "
              "radial_width_m solve_result")
        _exact(row["annulus_index"], index)
        for key in ("radial_inner_m", "radial_outer_m", "midpoint_radius_m", "radial_width_m"):
            _number(row[key])
        _require(0 <= row["radial_inner_m"] < row["midpoint_radius_m"] < row["radial_outer_m"])
        _require(row["radial_outer_m"] > 0 and row["radial_width_m"] > 0)
        if index:
            _exact(row["radial_inner_m"], rows[index - 1]["radial_outer_m"])
        child = row["solve_result"]
        _require(type(child) is dict and type(child["outputs"]) is dict)
        _exact(child["outputs"]["solve_state"], "CONVERGED")
        _keys(contribution, "annulus_index selected_evaluation_index thrust_density_n_m "
              "torque_density_nm_m radial_width_m thrust_n torque_nm")
        _exact(contribution["annulus_index"], index)
        selected = contribution["selected_evaluation_index"]
        _require(type(selected) is int and 0 <= selected < 16)
        _exact(child["outputs"]["solution"]["evaluation_index"], selected)
        for key in ("thrust_density_n_m", "torque_density_nm_m", "radial_width_m",
                    "thrust_n", "torque_nm"):
            _number(contribution[key])
        _exact(contribution["radial_width_m"], row["radial_width_m"])
    _exact(snapshot["output_units"], _rotor._output_units(rows, integrated))
    return rows, contributions, totals


def _quotient(numerator, denominator):
    result = _checked(numerator / denominator)
    _require(result != 0 or numerator == 0)
    return result


def _derive(rows, contributions, totals, digest):
    pressures, areas = [], []
    for row, contribution in zip(rows, contributions, strict=True):
        inner, outer = _number(row["radial_inner_m"]), _number(row["radial_outer_m"])
        width = _sum(outer, -inner)
        _exact(row["radial_width_m"], width)
        _exact(row["midpoint_radius_m"], _sum(inner, _product(0.5, width)))
        for quantity, density in (("thrust_n", "thrust_density_n_m"),
                                  ("torque_nm", "torque_density_nm_m")):
            _exact(contribution[quantity], _product(_number(contribution[density]), width))
        area = _product(math.pi, _sum(_product(outer, outer), -_product(inner, inner)))
        _require(area > 0)
        areas.append(area)
        pressures.append({"annulus_index": row["annulus_index"],
                          "disk_pressure_jump_pa": _quotient(_number(contribution["thrust_n"]), area)})
    for key in ("thrust_n", "torque_nm"):
        _exact(totals[key], _checked(math.fsum(_number(row[key]) for row in contributions)))
    radius = max(_number(row["radial_outer_m"]) for row in rows)
    _require(radius > 0)
    disk_area = _product(math.pi, _product(radius, radius))
    _require(disk_area > 0)
    active_area = _checked(math.fsum(areas))
    _require(active_area > 0)
    return {"derivation": _DERIVATION, "annuli": pressures,
            "rotor_mean_disk_loading_pa": _quotient(_number(totals["thrust_n"]), disk_area),
            "rotor_active_annular_loading_pa": _quotient(_number(totals["thrust_n"]), active_area),
            "input_digest": digest}


def _response(status, reasons, digest=None, outputs=None):
    outputs = {} if outputs is None else outputs
    result = {
        "evaluation": _EVALUATION, "schema_version": _SCHEMA_VERSION,
        "status": status, "reasons": list(reasons),
        "disk_pressure_state": "DERIVED" if outputs else "NOT_RUN",
        "state_text": _STATE_TEXT, "outputs": outputs, "output_units": {},
        "polar_rotor_result_count": 1 if outputs else 0,
        **dict.fromkeys(_COUNTS, 0),
        "diagnostics_complete": bool(outputs), "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "evidence_level": "unverified",
        "limitations": [_STATE_TEXT, "Input seals bind native JSON; they do not authenticate provenance.",
                        "Retained rotor convergence is consumed without rerunning section solves."],
        "request_sha256": digest, "evaluation_sha256": None,
    }
    if outputs:
        result["output_units"] = {
            "derivation": "label",
            "annuli": [{"annulus_index": "index", "disk_pressure_jump_pa": "Pa"}
                       for _ in outputs["annuli"]],
            "rotor_mean_disk_loading_pa": "Pa", "rotor_active_annular_loading_pa": "Pa",
            "input_digest": "sha256",
        }
    _rotor._walk(result, output=True)
    result["evaluation_sha256"] = _sha256_record({
        key: value for key, value in result.items() if key != "evaluation_sha256"})
    return _deepcopy(result)


def derive_disk_pressure(response):
    """Derive scalar annular pressure jumps from a sealed V135/V141-lineage rotor response.

    Binary64 finite normal-or-zero arithmetic follows the retained rotor guards.
    No model is run and no pressure field or new physical input is introduced.
    """
    try:
        snapshot = _rotor._snapshot(response, output=True)
        rows, contributions, totals = _preflight(snapshot)
        digest = _sha256_record(snapshot)
    except Exception:  # noqa: BLE001 -- malformed native input yields no accepted input or partial output.
        return _response("MODEL_INAPPLICABLE", ["INVALID_POLAR_ROTOR_RESPONSE"])
    try:
        outputs = _derive(rows, contributions, totals, digest)
        return _response("COMPUTED_EXPERIMENTAL", [], digest, outputs)
    except Exception:  # noqa: BLE001 -- arithmetic refusal is atomic, including accepted counts.
        return _response("EXECUTION_FAILED", ["DISK_PRESSURE_ARITHMETIC_FAILED"], digest)
