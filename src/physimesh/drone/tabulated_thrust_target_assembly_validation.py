"""Pure validation of retained actual V114 assembly results.

Failure envelopes establish necessary bounds, never execution attestation.
Only retained full results can be content-verified.
"""

import math

from . import tabulated_rotor_assembly as _loads
from . import tabulated_thrust_target_assembly as _assembly
from .hover_bemt import _mul
from .provenance import sha256_record
from .reference_air_tabulated_hover import _AIR_MARKERS, _exact
from .tabulated_hover_bemt_request import _json_walk, _require
from .tabulated_hover_thrust_target_validation import validate_tabulated_hover_thrust_target_result

# Independent code-owned snapshot, captured before any caller data is inspected.
_CATALOG = _assembly.tabulated_thrust_target_assembly_catalog()
_MARKERS = dict(_AIR_MARKERS)
_ROOT_KEYS = frozenset((
    "evaluation", "schema_version", "status", "evidence_level", "physical_validation",
    "numerical_qualification", "runtime_identity", "aircraft_status", "feasibility",
    "diagnostics_complete", "inverse_result_count", "forward_evaluation_count", "reasons",
    "limitations", "limits", "request_sha256", "evaluation_sha256", "outputs", "output_units",
    "stages", "transfers",
))
_DYNAMIC = frozenset((
    "status", "diagnostics_complete", "inverse_result_count", "forward_evaluation_count",
    "reasons", "request_sha256", "evaluation_sha256", "outputs", "output_units", "stages", "transfers",
))


def _admission(request):
    try:
        _json_walk(request, _CATALOG["limits"]["input_json"])
        _require(type(request) is dict and request.keys() == set(_CATALOG["required_fields"]))
        _require(type(request["evaluation"]) is str)
        if request["evaluation"] != _CATALOG["evaluation"]:
            return "SOLVER_UNSUPPORTED"
        _assembly._preflight(request)
    except (ValueError, OverflowError):
        return "MODEL_INAPPLICABLE"
    return "ADMITTED"


def _empty(actual):
    for name, expected in (("outputs", {}), ("output_units", {}), ("stages", []),
                           ("transfers", []), ("diagnostics_complete", False)):
        _exact(actual[name], expected)


def _air(actual, request):
    """V106 arithmetic on the actual raw mapping, with no typed fabrication."""
    units = _CATALOG["output_field_units"]["air"]
    _require(type(actual) is dict and actual.keys() == units.keys())
    state = actual["state"]
    _require(type(state) is dict and state.keys() == units["state"].keys())
    for name, expected in _MARKERS.items():
        _exact(actual[name], expected)
    _exact(state["model_id"], "coesa1976.lower-atmosphere.0-30km.v1")
    _exact(state["evidence_status"], "REFERENCE_MODEL_NOT_AIRCRAFT_VALIDATION")
    altitude, kind = float(request["altitude_m"]), request["altitude_kind"]
    _exact(state["input_altitude_m"], altitude)
    _exact(state["altitude_kind"], kind)
    earth, g0, gas = 6356750.0, 9.80665, 8314.32 / 28.9644
    h = earth * altitude / (earth + altitude) if kind == "geometric" else altitude
    _exact(state["geopotential_altitude_m"], h)
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
        _exact(state[name], expected)
    z = altitude if kind == "geometric" else earth * h / (earth - h)
    _exact(actual["geometric_altitude_m"], z)
    mu = 1.716e-5 * (273.15 + 110.33333) / (temperature + 110.33333) * (temperature / 273.15) ** 1.5
    for name, expected in (("dynamic_viscosity_pa_s", mu),
                           ("speed_of_sound_m_s", math.sqrt(1.4 * gas * temperature)),
                           ("gravity_m_s2", g0 * (earth / (earth + z)) ** 2)):
        _exact(actual[name], expected)


def _success(actual, request):
    outputs = actual["outputs"]
    _require(type(outputs) is dict and outputs.keys() == _CATALOG["output_field_units"].keys())
    _exact(actual["diagnostics_complete"], True)
    _exact(actual["reasons"], [])
    _exact(actual["output_units"], _CATALOG["output_field_units"])
    _air(outputs["air"], request["air"])
    rows, rotors = outputs["rotors"], request["rotors"]
    _require(type(rows) is list and len(rows) == len(rotors))
    stages, transfers = actual["stages"], actual["transfers"]
    _require(type(stages) is list and len(stages) == len(rows) + 1)
    _require(type(transfers) is list and len(transfers) == len(rows))
    air_digest = sha256_record(outputs["air"])
    _exact(stages[0], {"stage": "air", "inputs": request["air"],
                       "inputs_sha256": sha256_record(request["air"]), "result_sha256": air_digest})
    density = outputs["air"]["state"]["density_kg_m3"]
    cg, count = _loads._vector(request["cg_body_m"]), 0
    for index, (row, rotor) in enumerate(zip(rows, rotors, strict=True)):
        _require(type(row) is dict and row.keys() == _CATALOG["output_field_units"]["rotors"].keys())
        injected, template = row["actual_target_request"], rotor["target_template"]
        _json_walk(injected, _CATALOG["limits"]["inverse_input_json"])
        _exact(injected, {**template, "rotor_template": {
            **template["rotor_template"], "density_kg_m3": density,
        }})
        inverse = row["actual_target_result"]
        _json_walk(inverse, _CATALOG["limits"]["inverse_output_json"])
        _require(validate_tabulated_hover_thrust_target_result(inverse, injected) is None)
        _exact(inverse["status"], "COMPUTED_EXPERIMENTAL")
        count += inverse["evaluation_count"]
        selected = inverse["outputs"]["actual_forward_result"]["outputs"]
        # V112 signed helpers operate only on the retained actual selected values.
        expected_loads = _loads._loads(rotor, cg, selected)
        for name, expected in expected_loads.items():
            _exact(row[name], expected)
        stage, request_digest = "rotor:" + rotor["id"], sha256_record(injected)
        _exact(stages[index + 1], {"stage": stage, "inputs": injected,
                                  "inputs_sha256": request_digest, "result_sha256": sha256_record(inverse)})
        _exact(transfers[index], {
            "from_stage": "air", "from_field": "state.density_kg_m3", "to_stage": stage,
            "to_field": "rotor_template.density_kg_m3", "value": density, "unit": "kg/m^3",
            "producer_result_sha256": air_digest, "consumer_request_sha256": request_digest,
        })
    gravity = [_mul(_mul(_loads._number(request["mass_kg"]), outputs["air"]["gravity_m_s2"]), d)
               for d in _loads._vector(request["gravity_direction_body"], unit=True)]
    _exact(outputs["gravity_force_body_n"], gravity)
    _exact(outputs["net_force_body_n"], [
        _loads._sum([row["force_body_n"][i] for row in rows] + [gravity[i]]) for i in range(3)
    ])
    _exact(outputs["net_moment_cg_body_nm"], [
        _loads._sum([row["moment_cg_body_nm"][i] for row in rows]) for i in range(3)
    ])
    _exact(actual["inverse_result_count"], len(rotors))
    _exact(actual["forward_evaluation_count"], count)


def _failure(actual, request):
    _empty(actual)
    status = actual["status"]
    _require(status in ("MODEL_INAPPLICABLE", "TARGET_NOT_BRACKETED", "ITERATION_LIMIT",
                        "NUMERICAL_LIMIT", "EXECUTION_FAILED"))
    # Snapshot/hash infrastructure faults are outside deterministic admission.
    _exact(actual["reasons"], [_CATALOG["status_reason_matrix"][status][-1]])
    n, count = actual["inverse_result_count"], actual["forward_evaluation_count"]
    budgets = [r["target_template"]["max_evaluations"] for r in request["rotors"]]
    _require(0 <= n <= len(budgets) and 0 <= count <= sum(budgets[:n]))
    if n == 0:
        _require(status == "EXECUTION_FAILED" and count == 0)
        return
    prior_min, prior_max, last = 2 * (n - 1), sum(budgets[:n - 1]), budgets[n - 1]
    if status == "ITERATION_LIMIT":
        _require(prior_min + last <= count <= prior_max + last)
    elif status == "TARGET_NOT_BRACKETED":
        _require(prior_min + 2 <= count <= prior_max + 2)
    elif status == "NUMERICAL_LIMIT":
        _require(last >= 3 and prior_min + 2 <= count <= prior_max + last - 1)
    elif status == "MODEL_INAPPLICABLE":
        _require(prior_min + 1 <= count)
    else:
        _require(prior_min <= count)


def validate_tabulated_thrust_target_assembly_result(actual, request):
    """Return None for an actual contract; reject inconsistencies with ValueError.

    No copying hooks, mutation, model calls or fabricated component envelopes.
    Unexpected exceptions from pure dependencies propagate.
    """
    _json_walk(actual, _CATALOG["limits"]["output_json"])
    admission = _admission(request)
    _require(type(actual) is dict and actual.keys() == _ROOT_KEYS)
    for name in _ROOT_KEYS - _DYNAMIC:
        _exact(actual[name], _CATALOG[name])
    status = actual["status"]
    _require(type(status) is str and status in _CATALOG["status_reason_matrix"])
    inverses, forwards = actual["inverse_result_count"], actual["forward_evaluation_count"]
    _require(type(inverses) is int and type(forwards) is int)
    if admission != "ADMITTED":
        _exact(status, admission)
        _exact(inverses, 0)
        _exact(forwards, 0)
        _exact(actual["request_sha256"], None)
        _exact(actual["evaluation_sha256"], None)
        _exact(actual["reasons"], [_CATALOG["status_reason_matrix"][admission][0]])
        _empty(actual)
        return
    _exact(actual["request_sha256"], sha256_record(request))
    if status == "MODEL_INAPPLICABLE":
        _exact(actual["evaluation_sha256"], None)
    else:
        _exact(actual["evaluation_sha256"], sha256_record({
            key: value for key, value in actual.items() if key != "evaluation_sha256"
        }))
    if status == "COMPUTED_EXPERIMENTAL":
        _success(actual, request)
    else:
        _failure(actual, request)
