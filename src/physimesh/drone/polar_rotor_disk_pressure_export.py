"""V143 deterministic report export of retained V142 derived disk pressures."""

from copy import deepcopy as _deepcopy

from . import polar_rotor as _rotor
from . import polar_rotor_disk_pressure as _pressure
from .provenance import canonical_json as _canonical_json
from .provenance import sha256_record as _sha256_record

__all__ = ["export_disk_pressure_report"]

_SCHEMA_VERSION = "polar_rotor_disk_pressure_export_v1"
_TITLE = "Derived idealized actuator-disk pressure report"
_require, _exact, _checked = _rotor._require, _rotor._exact, _rotor._checked
_COUNTS = ("polar_rotor_result_count", "section_solve_result_count", "residual_result_count",
           "load_result_count", "lookup_result_count")
_FIXED = {
    "evaluation": "polar_rotor_disk_pressure", "schema_version": "polar_rotor_disk_pressure_v1",
    "status": "COMPUTED_EXPERIMENTAL", "reasons": [], "disk_pressure_state": "DERIVED",
    **dict.fromkeys(_COUNTS, 0), "polar_rotor_result_count": 1,
    "diagnostics_complete": True, "physical_validation": "NOT_ESTABLISHED",
    "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
    "aircraft_status": None, "feasibility": None, "evidence_level": "unverified",
}
_VARIABLE_KEYS = {"state_text", "limitations", "outputs", "output_units",
                  "request_sha256", "evaluation_sha256"}
_OUTPUT_KEYS = ("derivation annuli rotor_mean_disk_loading_pa "
                "rotor_active_annular_loading_pa input_digest")
_LABELS = (
    "derived IDEALIZED ACTUATOR-DISK quantity from integrated annulus thrust",
    "NOT surface pressure", "NOT a solved or CFD pressure field",
    "no spatial/vector information beyond the axisymmetric annulus",
    "full-disk mean spreads thrust over the whole disk including any inner hole",
    "active-annular mean spreads it only over the modeled annuli",
)


def _digest(value):
    _require(type(value) is str and len(value) == 64)
    _require(all(character in "0123456789abcdef" for character in value))


def _has_labels(text):
    return type(text) is str and all(label in text for label in _LABELS)


def _preflight(snapshot):
    _require(type(snapshot) is dict and snapshot.keys() == _FIXED.keys() | _VARIABLE_KEYS)
    for key, value in _FIXED.items():
        _exact(snapshot[key], value)
    for key in ("request_sha256", "evaluation_sha256"):
        _digest(snapshot[key])
    _exact(snapshot["evaluation_sha256"], _sha256_record({
        key: value for key, value in snapshot.items() if key != "evaluation_sha256"}))
    _require(_has_labels(snapshot["state_text"]))
    limitations = snapshot["limitations"]
    _require(type(limitations) is list and 1 <= len(limitations) <= 256)
    _require(all(type(text) is str and bool(text.strip()) for text in limitations))
    _require(any(_has_labels(text) for text in limitations))
    output = snapshot["outputs"]
    _rotor._keys(output, _OUTPUT_KEYS)
    _exact(output["derivation"], "ACTUATOR_DISK_IDENTITY_FROM_INTEGRATED_ANNULUS_THRUST")
    _digest(output["input_digest"])
    _exact(output["input_digest"], snapshot["request_sha256"])
    rows = output["annuli"]
    _require(type(rows) is list and 1 <= len(rows) <= 8)
    for index, row in enumerate(rows):
        _rotor._keys(row, "annulus_index disk_pressure_jump_pa")
        _exact(row["annulus_index"], index)
        _checked(row["disk_pressure_jump_pa"])
    for key in ("rotor_mean_disk_loading_pa", "rotor_active_annular_loading_pa"):
        _checked(output[key])
    _exact(snapshot["output_units"], {
        "derivation": "label", "annuli": [{"annulus_index": "index", "disk_pressure_jump_pa": "Pa"}
                                            for _ in rows],
        "rotor_mean_disk_loading_pa": "Pa", "rotor_active_annular_loading_pa": "Pa",
        "input_digest": "sha256",
    })


def _report(snapshot):
    return {
        "title": _TITLE, "schema_version": _SCHEMA_VERSION,
        **_deepcopy(snapshot["outputs"]),
        "state_text": snapshot["state_text"], "limitations": _deepcopy(snapshot["limitations"]),
        "source_request_sha256": snapshot["request_sha256"],
        "source_evaluation_sha256": snapshot["evaluation_sha256"],
        "output_units": _deepcopy(snapshot["output_units"]),
    }


def _response(status, reasons, digest=None, outputs=None, source=None):
    outputs = {} if outputs is None else outputs
    state_text = _pressure._STATE_TEXT if source is None else source["state_text"]
    limitations = [state_text] if source is None else _deepcopy(source["limitations"])
    result = {
        "evaluation": "polar_rotor_disk_pressure_export", "schema_version": _SCHEMA_VERSION,
        "status": status, "reasons": list(reasons),
        "disk_pressure_report_state": "EXPORTED" if outputs else "NOT_RUN",
        "state_text": state_text, "limitations": limitations,
        "outputs": outputs, "output_units": {},
        "disk_pressure_result_count": 1 if outputs else 0, **dict.fromkeys(_COUNTS, 0),
        "diagnostics_complete": bool(outputs), "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "evidence_level": "unverified",
        "request_sha256": digest, "evaluation_sha256": None,
    }
    if outputs:
        report = outputs["report"]
        result["output_units"] = {
            "report": {**_deepcopy(report["output_units"]), "title": "text", "schema_version": "label",
                       "state_text": "text", "limitations": ["text" for _ in limitations],
                       "source_request_sha256": "sha256", "source_evaluation_sha256": "sha256",
                       "output_units": "unit_metadata"},
            "report_canonical_sha256": "sha256", "report_bytes": "byte",
        }
    _rotor._walk(result, output=True)
    result["evaluation_sha256"] = _sha256_record({
        key: value for key, value in result.items() if key != "evaluation_sha256"})
    return _deepcopy(result)


def export_disk_pressure_report(response):
    """Export canonical UTF-8 JSON report metadata without running any physical model.

    Report bytes are canonical_json(outputs['report']).encode('utf-8'); the envelope
    carries their digest and length. Source seals bind JSON, not provenance authenticity.
    """
    try:
        snapshot = _rotor._snapshot(response, output=True)
        _preflight(snapshot)
        digest = _sha256_record(snapshot)
    except Exception:  # noqa: BLE001 -- reject the entire malformed or label-stripped source.
        return _response("MODEL_INAPPLICABLE", ["INVALID_DISK_PRESSURE_RESPONSE"])
    try:
        report = _report(snapshot)
        encoded = _canonical_json(report).encode("utf-8")
        outputs = {"report": report, "report_canonical_sha256": _sha256_record(report),
                   "report_bytes": len(encoded)}
        return _response("COMPUTED_EXPERIMENTAL", [], digest, outputs, snapshot)
    except Exception:  # noqa: BLE001 -- no partial report or accepted counts on export failure.
        return _response("EXECUTION_FAILED", ["DISK_PRESSURE_REPORT_EXPORT_FAILED"], digest)
