"""V143 serialization checks using local synthetic, test-only V142 inputs."""

import hashlib
import json
import math
from copy import deepcopy

import pytest

from physimesh.drone import polar_rotor as rotor
from physimesh.drone import polar_rotor_disk_pressure_export as exporter
from physimesh.drone.polar_rotor_disk_pressure import derive_disk_pressure
from physimesh.drone.provenance import canonical_json, sha256_record


def _independent_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_independent_bytes(value)).hexdigest()


def _seal(value):
    value["evaluation_sha256"] = _digest({
        key: item for key, item in value.items() if key != "evaluation_sha256"})
    return value


@pytest.fixture
def derivation_response():
    """Run the real V142 postprocessor on synthetic retained records, not model solves."""
    result = rotor._response("COMPUTED_EXPERIMENTAL", [], "a" * 64, 2, 2)
    annuli, contributions = [], []
    for index, (inner, outer, thrust) in enumerate(((1.0, 2.0, 6.0), (2.0, 4.0, 10.0))):
        width = outer - inner
        annuli.append({
            "annulus_index": index, "radial_inner_m": inner, "radial_outer_m": outer,
            "midpoint_radius_m": (inner + outer) / 2, "radial_width_m": width,
            "solve_result": {"outputs": {"solve_state": "CONVERGED",
                                          "solution": {"evaluation_index": 0}},
                             "output_units": {"solve_state": "label",
                                              "solution": {"evaluation_index": "index"}}},
        })
        contributions.append({
            "annulus_index": index, "selected_evaluation_index": 0,
            "thrust_density_n_m": thrust / width, "torque_density_nm_m": 0.0,
            "radial_width_m": width, "thrust_n": thrust, "torque_nm": 0.0,
        })
    integrated = {"integration_method": "MIDPOINT_PRESCRIBED_ANNULI", "contributions": contributions,
                  "totals": {"thrust_n": 16.0, "torque_nm": 0.0, "shaft_power_w": 0.0}}
    result["outputs"] = {"rotor_state": "COMPUTED", "annuli": annuli, "integrated": integrated}
    result["output_units"] = rotor._output_units(annuli, integrated)
    result["diagnostics_complete"] = True
    response = derive_disk_pressure(_seal(result))
    assert response["status"] == "COMPUTED_EXPERIMENTAL"
    return response


def _assert_sealed(result):
    assert result["evaluation_sha256"] == _digest({
        key: item for key, item in result.items() if key != "evaluation_sha256"})


def _assert_refused(result, status="MODEL_INAPPLICABLE"):
    assert result["status"] == status
    assert result["reasons"] == ["INVALID_DISK_PRESSURE_RESPONSE" if status == "MODEL_INAPPLICABLE"
                                 else "DISK_PRESSURE_REPORT_EXPORT_FAILED"]
    assert result["disk_pressure_report_state"] == "NOT_RUN"
    assert result["outputs"] == result["output_units"] == {}
    assert result["diagnostics_complete"] is False
    counts = {key: value for key, value in result.items() if key.endswith("_result_count")}
    assert counts and all(type(value) is int and value == 0 for value in counts.values())
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    _assert_sealed(result)


def test_deterministic_canonical_report_and_independent_recomputation(derivation_response):
    first = exporter.export_disk_pressure_report(derivation_response)
    second = exporter.export_disk_pressure_report(derivation_response)
    assert first["status"] == "COMPUTED_EXPERIMENTAL"
    assert first["disk_pressure_result_count"] == 1
    output = first["outputs"]
    report = output["report"]
    assert set(output) == {"report", "report_canonical_sha256", "report_bytes"}
    assert set(report) == {
        "title", "schema_version", "derivation", "state_text", "limitations", "annuli",
        "rotor_mean_disk_loading_pa", "rotor_active_annular_loading_pa", "input_digest",
        "source_request_sha256", "source_evaluation_sha256", "output_units",
    }
    assert report["title"] == "Derived idealized actuator-disk pressure report"
    assert report["schema_version"] == "polar_rotor_disk_pressure_export_v1"
    encoded = canonical_json(report).encode("utf-8")
    assert encoded == _independent_bytes(report)
    assert encoded == canonical_json(second["outputs"]["report"]).encode("utf-8")
    assert output["report_canonical_sha256"] == second["outputs"]["report_canonical_sha256"]
    assert output["report_canonical_sha256"] == sha256_record(report) == hashlib.sha256(encoded).hexdigest()
    assert type(output["report_bytes"]) is int and output["report_bytes"] == len(encoded)
    assert _independent_bytes(first) == _independent_bytes(second)
    assert report["annuli"] == [
        {"annulus_index": 0, "disk_pressure_jump_pa": 6.0 / (math.pi * (2.0**2 - 1.0**2))},
        {"annulus_index": 1, "disk_pressure_jump_pa": 10.0 / (math.pi * (4.0**2 - 2.0**2))},
    ]
    assert report["rotor_mean_disk_loading_pa"] == 16.0 / (math.pi * 4.0**2)
    active_area = math.fsum((math.pi * (2.0**2 - 1.0**2), math.pi * (4.0**2 - 2.0**2)))
    assert report["rotor_active_annular_loading_pa"] == 16.0 / active_area
    _assert_sealed(first)


def test_traceability_labels_units_and_immutability(derivation_response):
    before, retained = _digest(derivation_response), deepcopy(derivation_response)
    result = exporter.export_disk_pressure_report(derivation_response)
    assert _digest(derivation_response) == before
    assert derivation_response == retained
    assert result["request_sha256"] == before
    report = result["outputs"]["report"]
    assert report["input_digest"] == derivation_response["outputs"]["input_digest"]
    assert report["source_request_sha256"] == derivation_response["request_sha256"]
    assert report["source_evaluation_sha256"] == derivation_response["evaluation_sha256"]
    for key in ("state_text", "limitations"):
        assert report[key] == result[key] == derivation_response[key]
    for label in ("derived IDEALIZED ACTUATOR-DISK", "NOT surface pressure",
                  "NOT a solved or CFD pressure field", "no spatial/vector information"):
        assert label in report["state_text"]
        assert any(label in text for text in report["limitations"])
    assert report["output_units"] == derivation_response["output_units"]
    assert result["output_units"].keys() == result["outputs"].keys()
    assert result["output_units"]["report"].keys() == report.keys()
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[key] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is result["feasibility"] is None
    report["limitations"].append("caller change")
    report["annuli"][0]["disk_pressure_jump_pa"] = 99.0
    report["output_units"]["annuli"][0]["disk_pressure_jump_pa"] = "changed"
    assert _digest(derivation_response) == before


@pytest.mark.parametrize("target", ["state_text", "limitations"])
@pytest.mark.parametrize("label", ["IDEALIZED ACTUATOR-DISK", "NOT surface pressure",
                                   "NOT a solved or CFD pressure field", "no spatial/vector information"])
def test_resealed_stripped_labels_refused(derivation_response, target, label):
    if target == "state_text":
        derivation_response[target] = derivation_response[target].replace(label, "removed")
    else:
        derivation_response[target] = [text.replace(label, "removed") for text in derivation_response[target]]
    _seal(derivation_response)
    before = _digest(derivation_response)
    _assert_refused(exporter.export_disk_pressure_report(derivation_response))
    assert _digest(derivation_response) == before


@pytest.mark.parametrize("key", [
    "evaluation", "schema_version", "status", "reasons", "disk_pressure_state", "state_text",
    "limitations", "outputs", "output_units", "polar_rotor_result_count", "section_solve_result_count",
    "residual_result_count", "load_result_count", "lookup_result_count", "diagnostics_complete",
    "physical_validation", "numerical_qualification", "runtime_identity", "aircraft_status", "feasibility",
    "evidence_level", "request_sha256", "evaluation_sha256",
])
def test_missing_envelope_key_refused(derivation_response, key):
    del derivation_response[key]
    if key != "evaluation_sha256":
        _seal(derivation_response)
    _assert_refused(exporter.export_disk_pressure_report(derivation_response))


@pytest.mark.parametrize("key", ["derivation", "annuli", "rotor_mean_disk_loading_pa",
                                 "rotor_active_annular_loading_pa", "input_digest"])
def test_missing_output_key_refused(derivation_response, key):
    del derivation_response["outputs"][key]
    _assert_refused(exporter.export_disk_pressure_report(_seal(derivation_response)))


@pytest.mark.parametrize("path,value", [
    (("extra",), 0), (("evaluation",), "other"), (("schema_version",), "other"),
    (("status",), "EXECUTION_FAILED"), (("disk_pressure_state",), "NOT_RUN"),
    (("diagnostics_complete",), 1), (("polar_rotor_result_count",), True),
    (("section_solve_result_count",), 1), (("physical_validation",), "changed"),
    (("request_sha256",), "g" * 64), (("request_sha256",), "b" * 64),
    (("limitations",), []), (("limitations",), "text"), (("limitations",), [True]),
    (("outputs", "derivation"), "other"), (("outputs", "input_digest"), "short"),
    (("outputs", "input_digest"), "A" * 64), (("outputs", "annuli"), []),
    (("outputs", "annuli"), {}), (("outputs", "annuli", 0, "annulus_index"), False),
    (("outputs", "annuli", 1, "annulus_index"), 0),
    (("outputs", "annuli", 0, "disk_pressure_jump_pa"), True),
    (("outputs", "annuli", 0, "disk_pressure_jump_pa"), 1),
    (("outputs", "rotor_mean_disk_loading_pa"), "1.0"),
    (("outputs", "rotor_active_annular_loading_pa"), None),
    (("output_units", "rotor_mean_disk_loading_pa"), "N"),
    (("output_units", "annuli", 0, "disk_pressure_jump_pa"), "N"),
    (("output_units", "extra"), "Pa"), (("outputs", "extra"), 0),
])
def test_resealed_malformed_payload_refused(derivation_response, path, value):
    target = derivation_response
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    _assert_refused(exporter.export_disk_pressure_report(_seal(derivation_response)))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("key", ["annuli", "rotor_mean_disk_loading_pa", "rotor_active_annular_loading_pa"])
def test_nonfinite_pressure_refused(derivation_response, key, value):
    if key == "annuli":
        derivation_response["outputs"][key][0]["disk_pressure_jump_pa"] = value
    else:
        derivation_response["outputs"][key] = value
    _assert_refused(exporter.export_disk_pressure_report(derivation_response))


@pytest.mark.parametrize("value", [None, [], {}, True, "response"])
def test_malformed_root_refused(value):
    _assert_refused(exporter.export_disk_pressure_report(value))


def test_stale_source_seal_refused(derivation_response):
    derivation_response["outputs"]["annuli"][0]["disk_pressure_jump_pa"] = 42.0
    _assert_refused(exporter.export_disk_pressure_report(derivation_response))


def test_foreign_object_rejected_before_copy(derivation_response):
    class Foreign(dict):
        def __deepcopy__(self, memo):
            pytest.fail("foreign copy hook must not run")

        def items(self):
            pytest.fail("foreign iteration hook must not run")

    derivation_response["outputs"]["hidden"] = Foreign()
    _assert_refused(exporter.export_disk_pressure_report(derivation_response))


def test_utf8_byte_length_and_added_labels_preserved(derivation_response):
    derivation_response["limitations"].append("Synthetic test-only note: \u03c0, \u00b5, \u73af")
    _seal(derivation_response)
    result = exporter.export_disk_pressure_report(derivation_response)
    report = result["outputs"]["report"]
    assert result["outputs"]["report_bytes"] == len(_independent_bytes(report))
    assert result["outputs"]["report_bytes"] > len(canonical_json(report))
    assert report["limitations"] == derivation_response["limitations"]


def test_serialization_failure_is_atomic(derivation_response, monkeypatch):
    def fail(report):
        raise ValueError("private detail")

    monkeypatch.setattr(exporter, "_canonical_json", fail)
    result = exporter.export_disk_pressure_report(derivation_response)
    _assert_refused(result, "EXECUTION_FAILED")
    assert "private detail" not in canonical_json(result)
