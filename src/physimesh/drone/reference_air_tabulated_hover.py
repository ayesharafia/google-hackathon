"""Fixed reference-air to accepted V105 tabulated-hover composition.

No evaluator is rerun for validation. Contract arithmetic binds actual returned
values; data digests establish neither runtime identity nor physical accuracy.
"""

import math
from copy import deepcopy
from dataclasses import asdict, fields

from . import reference_air_properties as _air
from . import tabulated_hover_bemt_request as _child
from .provenance import sha256_record
from .reference_air_properties import reference_air_properties
from .standard_atmosphere import StandardAtmosphereState
from .tabulated_hover_bemt_request import evaluate_tabulated_hover_bemt

EVALUATION = "reference_air_tabulated_hover_experimental"
SCHEMA_VERSION = "reference_air_tabulated_hover_v1"
_TEMPLATE_KEYS = frozenset(_child._REQUEST_KEYS) - {"density_kg_m3"}
_REQUIRE = _child._require
_JSON = _child._json_walk
_CHILD_METADATA = _child.tabulated_hover_bemt_catalog()
_LIMITS = {
    "input_json": {**_CHILD_METADATA["limits"]["input_json"],
                   "max_depth": 11, "max_nodes_including_keys": 16384},
    "child_input_json": deepcopy(_CHILD_METADATA["limits"]["input_json"]),
    "core_work": deepcopy(_CHILD_METADATA["limits"]["core_work"]),
    "output_json": {**_CHILD_METADATA["limits"]["output_json"],
                    "max_depth": 16, "max_nodes_including_keys": 65536},
}
_STATE_UNITS = {
    "input_altitude_m": "m", "altitude_kind": "label", "geopotential_altitude_m": "m",
    "pressure_pa": "Pa", "temperature_k": "K", "density_kg_m3": "kg/m^3",
    "model_id": "label", "evidence_status": "label",
}
_AIR_UNITS = {
    "state": _STATE_UNITS, "geometric_altitude_m": "m", "dynamic_viscosity_pa_s": "Pa*s",
    "speed_of_sound_m_s": "m/s", "gravity_m_s2": "m/s^2", "model_id": "label",
    "viscosity_model": "text", "sound_model": "text", "gravity_model": "text",
    "physical_qualification": "label", "numerical_qualification": "label",
}
_AIR_MARKERS = {
    "model_id": _air.MODEL_ID, "viscosity_model": _air.VISCOSITY_MODEL,
    "sound_model": _air.SOUND_MODEL, "gravity_model": _air.GRAVITY_MODEL,
    "physical_qualification": "NOT_ESTABLISHED", "numerical_qualification": "NOT_ESTABLISHED",
}
_CHILD_KEYS = frozenset((
    "evaluation", "model_id", "schema_version", "status", "core_model", "core_version", "core_status",
    "evidence_level", "physical_validation", "numerical_qualification", "runtime_identity",
    "aircraft_status", "feasibility", "diagnostics_complete", "reasons", "limitations", "outputs",
    "output_units", "limits", "request_sha256", "evaluation_sha256",
))
_LIMITATIONS = (
    "Local engineering workflow proposal, not an external standard.",
    "Reference dry air is not measured weather or aircraft validation.",
    "Density alone does not correct coefficients for Reynolds number or Mach number.",
    "No Reynolds/Mach polars, stall, swirl, tip/root losses or compressibility corrections.",
    "Attached-linear small-angle isolated hover; angle validity and physical accuracy are not established.",
    "Source claims, classification and uncertainty remain unverified caller assertions.",
    "No graph, rotor assembly, trim, mission or API integration; no new aircraft qualification.",
    "No 80 percent accuracy or novelty claim; finite values and hashes establish no qualification.",
    "Hashes describe actual JSON data, not runtime identity or physical validation.",
    "Rotor units apply only to the nested child outputs, not its whole response envelope.",
)


def _exact(actual, expected):
    """Metadata equality includes builtin types, avoiding bool/int equality."""
    _REQUIRE(type(actual) is type(expected))
    if type(expected) is dict:
        _REQUIRE(actual.keys() == expected.keys())
        for key in expected:
            _exact(actual[key], expected[key])
    elif type(expected) is list:
        _REQUIRE(len(actual) == len(expected))
        for left, right in zip(actual, expected, strict=True):
            _exact(left, right)
    else:
        _REQUIRE(actual == expected)


def _preflight(snapshot):
    air, rotor = snapshot["air"], snapshot["rotor_template"]
    _REQUIRE(type(air) is dict and air.keys() == {"altitude_m", "altitude_kind"})
    altitude, kind = air["altitude_m"], air["altitude_kind"]
    _REQUIRE(type(altitude) in (int, float) and 0 <= altitude <= 30000)
    _REQUIRE(type(kind) is str and kind in ("geometric", "geopotential"))
    _REQUIRE(type(rotor) is dict and rotor.keys() == _TEMPLATE_KEYS)
    _exact(rotor["evaluation"], _child.EVALUATION)
    for name, maximum in (("annuli", 2048), ("blade_count", 32)):
        _REQUIRE(type(rotor[name]) is int and 1 <= rotor[name] <= maximum)
    for name in ("radius_m", "angular_speed_rad_s", "root_cutout_m",
                 "lift_curve_slope_per_rad", "profile_drag_coefficient"):
        _REQUIRE(type(rotor[name]) in (int, float))
    for name in ("geometry_source", "geometry_kind", "uncertainty_status"):
        _REQUIRE(type(rotor[name]) is str and bool(rotor[name].strip()))
    _REQUIRE(rotor["geometry_kind"] in ("measured", "digitized_measurement", "as_designed", "synthetic"))
    stations = rotor["stations"]
    _REQUIRE(type(stations) is list and 2 <= len(stations) <= 256)
    for station in stations:
        _REQUIRE(type(station) is dict and station.keys() == _CHILD_METADATA["input_units"]["stations"].keys())
        _REQUIRE(all(type(value) in (int, float) for value in station.values()))


def _typed_fields(value, cls, expected):
    _REQUIRE(type(value) is cls and cls.__dataclass_params__.frozen is True)
    _REQUIRE({field.name for field in fields(value)} == expected.keys())
    _REQUIRE(vars(value).keys() == expected.keys())


def _positive_float(value):
    _REQUIRE(type(value) is float and math.isfinite(value) and value > 0.0)


def _validate_air(actual, request):
    """Typed boundary, then accepted hydrostatic and transport arithmetic.

    Explicit accepted constants, layer order, boundaries and operation order
    prevent a coherent pressure/density forgery. This is no second model call.
    """
    _typed_fields(actual, _air.ReferenceAirProperties, _AIR_UNITS)
    state = actual.state
    _typed_fields(state, StandardAtmosphereState, _STATE_UNITS)
    altitude, kind = float(request["altitude_m"]), request["altitude_kind"]
    _air._validate_state(state, altitude, kind)
    for name, expected in _AIR_MARKERS.items():
        _exact(getattr(actual, name), expected)
    earth, g0, gas = 6356750.0, 9.80665, 8314.32 / 28.9644
    h = earth * altitude / (earth + altitude) if kind == "geometric" else altitude
    _exact(state.geopotential_altitude_m, h)
    pressure, temperature = 101325.0, 288.15
    for bottom, top, lapse in ((0.0, 11000.0, -0.0065), (11000.0, 20000.0, 0.0),
                               (20000.0, 32000.0, 0.001)):
        dh = min(h, top) - bottom
        next_temperature = temperature + lapse * dh
        if lapse == 0.0:
            pressure = pressure * math.exp(-g0 * dh / (gas * temperature))
        else:
            pressure = pressure * (next_temperature / temperature) ** (-g0 / (gas * lapse))
        temperature = next_temperature
        if h <= top:
            break
    for name, expected in (("pressure_pa", pressure), ("temperature_k", temperature),
                           ("density_kg_m3", pressure / (gas * temperature))):
        _positive_float(getattr(state, name))
        _exact(getattr(state, name), expected)
    z = altitude if kind == "geometric" else earth * h / (earth - h)
    _REQUIRE(type(actual.geometric_altitude_m) is float and math.isfinite(actual.geometric_altitude_m))
    _exact(actual.geometric_altitude_m, z)
    mu = 1.716e-5 * (273.15 + 110.33333) / (temperature + 110.33333) * (temperature / 273.15) ** 1.5
    sound = math.sqrt(1.4 * gas * temperature)
    gravity = g0 * (earth / (earth + z)) ** 2
    for name, expected in (("dynamic_viscosity_pa_s", mu), ("speed_of_sound_m_s", sound),
                           ("gravity_m_s2", gravity)):
        _positive_float(getattr(actual, name))
        _exact(getattr(actual, name), expected)
    # Only the actual, fully checked typed result may cross this export boundary.
    raw = asdict(actual)
    _JSON(raw, _LIMITS["output_json"])
    return raw


def _validate_child(actual, injected):
    """Validate the actual full envelope separately from its actual output slice."""
    _JSON(actual, _CHILD_METADATA["limits"]["output_json"])
    _REQUIRE(type(actual) is dict and actual.keys() == _CHILD_KEYS)
    for name in ("evaluation", "model_id", "schema_version", "evidence_level", "physical_validation",
                 "numerical_qualification", "runtime_identity", "aircraft_status", "feasibility",
                 "limitations", "limits"):
        _exact(actual[name], _CHILD_METADATA[name])
    _exact(actual["request_sha256"], sha256_record(injected))
    status = actual["status"]
    _REQUIRE(type(status) is str)
    if status == "MODEL_INAPPLICABLE":
        for name, expected in {
            "core_model": None, "core_version": None, "core_status": None,
            "diagnostics_complete": False, "outputs": {}, "output_units": {}, "evaluation_sha256": None,
            "reasons": ["Request is outside the core input or numerical domain."],
        }.items():
            _exact(actual[name], expected)
        return False
    _REQUIRE(status == "COMPUTED_EXPERIMENTAL")
    for name, expected in {
        "core_model": "tabulated_geometry_hover_experimental", "core_version": "0.1",
        "core_status": "COMPUTED_EXPERIMENTAL", "diagnostics_complete": True, "reasons": [],
        "output_units": _CHILD_METADATA["output_field_units"],
    }.items():
        _exact(actual[name], expected)
    _exact(actual["evaluation_sha256"], sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"
    }))
    _child._validate_output_values(actual["outputs"], injected)
    return True


def _response(status, reasons, request_digest=None):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        "reasons": list(reasons), "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
        "request_sha256": request_digest, "evaluation_sha256": None,
        "outputs": {}, "output_units": {}, "stages": [], "transfers": [],
    }


def _seal(response):
    _JSON(response, _LIMITS["output_json"])
    if response["request_sha256"] is not None and response["status"] in (
        "COMPUTED_EXPERIMENTAL", "EXECUTION_FAILED",
    ):
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"
        })
    return response


def reference_air_tabulated_hover_catalog():
    """Fresh closed schema, units, bounds and separate data-binding contracts."""
    return {
        **_response("RESEARCH_ONLY", []),
        "required_fields": ["evaluation", "air", "rotor_template"],
        "air_fields": ["altitude_m", "altitude_kind"],
        "rotor_template_fields": [key for key in _child._REQUEST_KEYS if key != "density_kg_m3"],
        "input_units": {
            "evaluation": "label", "air": {"altitude_m": "m", "altitude_kind": "label"},
            "rotor_template": {key: deepcopy(value) for key, value in _CHILD_METADATA["input_units"].items()
                               if key != "density_kg_m3"},
        },
        "output_field_units": {"air": deepcopy(_AIR_UNITS),
                               "rotor": deepcopy(_CHILD_METADATA["output_field_units"])},
        "request_contract": {
            "extra_fields": "forbidden at every request object; density_kg_m3 forbidden in template",
            "defaults": {}, "air": "explicit builtin finite int/float 0..30000 m; geometric/geopotential",
            "template_evaluation": _child.EVALUATION,
            "preflight": "strict JSON, exact fields, numeric types, declarations, source classification and counts",
            "physical_domain": "owned only by actual accepted child core after actual air evaluation",
            "child_json": "independent V105 input walk after actual validated density injection",
        },
        "bindings": {
            "air": "actual frozen exact dataclasses, markers, altitude, hydrostatic and transport arithmetic",
            "rotor": "actual full V105 envelope, units, markers, request/evaluation digests and direct output slice",
            "stages": "actual inputs plus inputs_sha256 and actual result_sha256; no duplicate full results",
            "transfer": "only state.density_kg_m3 scalar SI, producer result digest to consumer request digest",
            "units": "air covers full raw air; rotor covers only outputs.rotor.outputs",
            "digests": "accepted SHA256 canonical UTF8 JSON; data only; evaluation digest omits itself",
        },
        "response_contract": {
            "completed": "COMPUTED_EXPERIMENTAL with actual air raw and unchanged actual full child response",
            "invalid": "MODEL_INAPPLICABLE before acceptance or actual valid child domain refusal",
            "unsupported": "SOLVER_UNSUPPORTED for other outer evaluation string",
            "failure": "EXECUTION_FAILED for ordinary exceptions or invalid actual returned contracts",
            "atomic": "all failure outputs/output_units/stages/transfers empty; diagnostics_complete false",
            "hashes": "request null before acceptance; evaluation only completed/failed after acceptance",
            "base_exception": "propagates; ordinary exception text is never exported",
        },
    }


def evaluate_reference_air_tabulated_hover(request):
    """Actual air once, actual validated density, actual V105 adapter once."""
    try:
        _JSON(request, _LIMITS["input_json"])
        snapshot = deepcopy(request)
        _JSON(snapshot, _LIMITS["input_json"])
        _REQUIRE(type(snapshot) is dict and snapshot.keys() == {"evaluation", "air", "rotor_template"})
        _REQUIRE(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _response("SOLVER_UNSUPPORTED", ["Unsupported evaluation."])
        _preflight(snapshot)
    except ValueError:
        return _response("MODEL_INAPPLICABLE", ["Invalid bounded workflow request."])
    except Exception:  # noqa: BLE001
        return _response("EXECUTION_FAILED", ["Request snapshot failed."])

    digest = None
    try:
        digest = sha256_record(snapshot)
        actual_air = reference_air_properties(**deepcopy(snapshot["air"]))
        raw_air = _validate_air(actual_air, snapshot["air"])
        injected = deepcopy(snapshot["rotor_template"])
        injected["density_kg_m3"] = actual_air.state.density_kg_m3
        _JSON(injected, _LIMITS["child_input_json"])
        actual_rotor = evaluate_tabulated_hover_bemt(deepcopy(injected))
        if not _validate_child(actual_rotor, injected):
            return _response("MODEL_INAPPLICABLE", ["Actual child refused the physical or numerical domain."], digest)
        air_digest, rotor_input_digest = sha256_record(raw_air), sha256_record(injected)
        response = _response("COMPUTED_EXPERIMENTAL", [], digest)
        response.update(
            diagnostics_complete=True, outputs={"air": raw_air, "rotor": actual_rotor},
            output_units={"air": deepcopy(_AIR_UNITS), "rotor": deepcopy(actual_rotor["output_units"])},
            stages=[
                {"stage": "air", "inputs": deepcopy(snapshot["air"]),
                 "inputs_sha256": sha256_record(snapshot["air"]), "result_sha256": air_digest},
                {"stage": "rotor", "inputs": injected, "inputs_sha256": rotor_input_digest,
                 "result_sha256": sha256_record(actual_rotor)},
            ],
            transfers=[{
                "from_stage": "air", "from_field": "state.density_kg_m3", "to_stage": "rotor",
                "to_field": "density_kg_m3", "value": actual_air.state.density_kg_m3, "unit": "kg/m^3",
                "producer_result_sha256": air_digest, "consumer_request_sha256": rotor_input_digest,
            }],
        )
        return _seal(response)
    except Exception:  # noqa: BLE001 -- atomic and sanitized; BaseException propagates.
        return _seal(_response("EXECUTION_FAILED", ["Workflow execution or returned contract failed."], digest))
