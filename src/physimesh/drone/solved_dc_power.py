import math
from copy import deepcopy

from . import dc_motor as dc
from . import solved_wrench_electrothermal as se
from . import solved_wrench_power as sp
from . import thermal as th
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "solved_static_wrench_dc_power_experimental"


def _motor_request(entry, omega, torque):
    return {
        "evaluation": dc.EVALUATION,
        "parameters": deepcopy(entry["parameters"]),
        "declared_limits": deepcopy(entry["declared_limits"]),
        "operating_point": {
            "angular_speed_rad_s": omega, "shaft_torque_nm": torque,
        },
    }


def _shaft_request(snapshot):
    return {
        "evaluation": sp.EVALUATION,
        "solve": deepcopy(snapshot["solve"]),
        "conversion": {
            "rotors": [{
                "node": rotor["node"], "conversion_efficiency": 1,
                "conversion_source": "Internal shaft-only bridge; no electrical conversion claim.",
            } for rotor in snapshot["solve"]["assembly_template"]["rotors"]],
            "auxiliary_power_w": 0,
            "auxiliary_source": "Internal shaft-only bridge; auxiliary accounted separately once.",
        },
    }


def _preflight(request):
    _json(request, budget=49152)
    snapshot = deepcopy(request)

    def exact(value, keys):
        _require(type(value) is dict and set(value) == set(keys))

    def source(value):
        _require(type(value) is str and bool(value.strip()) and len(value) <= 2000)

    def fraction(value):
        _require(type(value) in (int, float))
        _normal(value)
        _require(math.isfinite(value) and 0 <= value <= 1)

    exact(snapshot, ("evaluation", "solve", "motors", "auxiliary"))
    _require(type(snapshot["evaluation"]) is str and snapshot["evaluation"] == EVALUATION)
    motors = snapshot["motors"]
    _require(type(motors) is list)
    for entry in motors:
        exact(entry, (
            "node", "parameters", "declared_limits",
            "heat_fraction_of_motor_loss", "heat_source",
        ))
        _require(type(entry["node"]) is str)
        fraction(entry["heat_fraction_of_motor_loss"])
        source(entry["heat_source"])
    auxiliary = snapshot["auxiliary"]
    exact(auxiliary, ("power_w", "heat_fraction", "source"))
    power = auxiliary["power_w"]
    _require(type(power) in (int, float))
    _normal(power)
    _require(math.isfinite(power) and power >= 0)
    fraction(auxiliary["heat_fraction"])
    source(auxiliary["source"])
    core = sp._preflight(_shaft_request(snapshot))
    snapshot["solve"] = core["solve"]
    rotors = core["solve"]["assembly_template"]["rotors"]
    bounds = core["solve"]["rotor_speed_bounds"]
    _require(len(motors) == len(rotors) == len(bounds))
    for entry, rotor, bound in zip(motors, rotors, bounds):
        _require(entry["node"] == rotor["node"])
        dc._preflight(_motor_request(entry, bound["initial_angular_speed_rad_s"], 0))
    return snapshot


def _validated_motor(raw, request):
    sp.ls.ld._valid(raw, dc.EVALUATION, request)
    outputs, units = raw["outputs"], raw["output_units"]
    _require(type(outputs) is dict and set(outputs) == set(dc._units()))
    _require(type(units) is dict and units == dc._units())
    for key in set(outputs) - {"efficiency", "declared_limit_status", "limit_checks"}:
        value = outputs[key]
        _require(type(value) in (int, float))
        _normal(value)
        _require(key == "power_balance_residual_w" or value >= 0)
    efficiency = outputs["efficiency"]
    if efficiency is not None:
        _require(type(efficiency) in (int, float))
        _require(0 <= _normal(efficiency) <= 1)
    checks = outputs["limit_checks"]
    _require(type(checks) is dict and set(checks) == {
        "current", "terminal_voltage", "angular_speed", "shaft_torque",
    })
    _require(all(type(value) is bool for value in checks.values()))
    status = outputs["declared_limit_status"]
    _require(type(status) is str and status in (
        "WITHIN_DECLARED_LIMITS", "EXCEEDS_DECLARED_LIMITS",
    ))
    for key in ("stages", "transfers"):
        _require(type(raw[key]) is list and raw[key] == [])
    _require(outputs == dc._compute(request))
    return deepcopy(raw)


def _power(snapshot, shaft_raw):
    shaft_rows = shaft_raw["outputs"]["power"]["rotors"]
    entries = snapshot["motors"]
    _require(type(shaft_rows) is list and len(shaft_rows) == len(entries))
    rows, stages, transfers = [], [], []
    for index, (entry, shaft) in enumerate(zip(entries, shaft_rows)):
        _require(shaft["node"] == entry["node"])
        omega, torque = shaft["angular_speed_rad_s"], shaft["shaft_torque_nm"]
        _require(_normal(omega) > 0 and _normal(torque) >= 0)
        request = _motor_request(entry, omega, torque)
        raw = _validated_motor(dc.evaluate_dc_motor(deepcopy(request)), request)
        motor = raw["outputs"]
        _require(math.isclose(motor["shaft_power_w"], _normal(shaft["shaft_power_w"]),
                             rel_tol=1e-12, abs_tol=1e-12))
        loss = motor["total_loss_w"]
        heat = th.checked_product(loss, entry["heat_fraction_of_motor_loss"])
        remaining = th.checked_difference(loss, heat)
        _require(0 <= heat <= loss and remaining >= 0)
        rows.append({
            "node": entry["node"], "angular_speed_rad_s": omega,
            "shaft_torque_nm": torque, "motor": motor,
            "allocated_heat_w": heat, "unallocated_loss_w": remaining,
        })
        stages.append({"stage_id": f"motor_{index}",
                       "request_sha256": sha256_record(request),
                       "result_sha256": sha256_record(raw)})
        transfers.append({
            "node": entry["node"], "operating_point": deepcopy(request["operating_point"]),
            "source": "validated_selected_shaft_power_row",
            "heat_fraction_of_motor_loss": entry["heat_fraction_of_motor_loss"],
            "heat_source": entry["heat_source"],
        })
    auxiliary = snapshot["auxiliary"]
    aux_power = auxiliary["power_w"]
    aux_heat = th.checked_product(aux_power, auxiliary["heat_fraction"])
    _require(0 <= aux_heat <= aux_power)
    power = {"motors": rows}
    for name, field in (("total_shaft_power_w", "shaft_power_w"),
                        ("total_motor_electrical_power_w", "electrical_power_w"),
                        ("total_motor_loss_w", "total_loss_w")):
        power[name] = dc._power_sum(row["motor"][field] for row in rows)
    power["total_allocated_motor_heat_w"] = dc._power_sum(r["allocated_heat_w"] for r in rows)
    power["total_unallocated_motor_loss_w"] = dc._power_sum(r["unallocated_loss_w"] for r in rows)
    power["total_electrical_power_w"] = dc._power_sum([power["total_motor_electrical_power_w"], aux_power])
    power["auxiliary_electrical_power_w"], power["auxiliary_heat_w"] = aux_power, aux_heat
    power["total_allocated_heat_w"] = dc._power_sum([power["total_allocated_motor_heat_w"], aux_heat])
    return deepcopy((power, stages, {
        "motors": transfers, "auxiliary": {**auxiliary, "heat_w": aux_heat},
    }))


def _power_units(n):
    return {
        "motors": [{
            "node": "not_applicable", "angular_speed_rad_s": "rad/s",
            "shaft_torque_nm": "N*m", "motor": dc._units(),
            "allocated_heat_w": "W", "unallocated_loss_w": "W",
        } for _ in range(n)],
        **dict.fromkeys((
            "total_shaft_power_w", "total_motor_electrical_power_w", "total_motor_loss_w",
            "total_allocated_motor_heat_w", "total_unallocated_motor_loss_w",
            "total_electrical_power_w", "auxiliary_electrical_power_w",
            "auxiliary_heat_w", "total_allocated_heat_w",
        ), "W"),
    }


def evaluate_solved_dc_power(request):
    result = {
        "evaluation": EVALUATION,
        "status": "GRAPH_INVALID",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "feasibility": None,
        "aircraft_status": None,
        "diagnostics_complete": False,
        "reasons": [],
        "stages": [],
        "transfers": {},
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Scientifically unqualified experimental computation at one static point.",
            "Caller-declared constant-parameter DC equivalent; no BLDC phase conversion.",
            "No installed-flight, trim, control-authority or aircraft feasibility established.",
            "Declared motor limits are screening assumptions, not continuous thermal ratings.",
            "Heat fractions declare captured motor loss and auxiliary heat, not thermal adequacy.",
            "No mission, thermal evolution, heat feedback, ESC, battery or bus-current execution.",
            "Hashes record request/result provenance, not physical proof or runtime identity.",
        ],
    }
    errors = (
        ValueError, TypeError, OverflowError, UnicodeError,
        RecursionError, KeyError, ZeroDivisionError,
    )
    try:
        snapshot = _preflight(request)
    except errors:
        result["reasons"] = ["Invalid solved DC power request."]
        return deepcopy(result)
    try:
        result["request_sha256"] = sha256_record(snapshot)
        shaftreq = _shaft_request(snapshot)
        raw = sp.evaluate_solved_wrench_power(deepcopy(shaftreq))
        se._validated_power_result(raw, shaftreq)
        stages = [{
            "stage_id": "solved_wrench_power",
            "request_sha256": sha256_record(shaftreq),
            "result_sha256": sha256_record(raw),
            "stages": deepcopy(raw["stages"]),
        }]
        transfers = {"solved_wrench_power": deepcopy(raw["transfers"])}
        state, power, units = "NOT_RUN_RESIDUAL_UNMET", None, None
        if raw["outputs"]["solve"]["outcome"] == "RESIDUAL_MET":
            power, motor_stages, motor_transfers = _power(snapshot, raw)
            stages.extend(motor_stages)
            transfers.update(motor_transfers)
            units = _power_units(len(snapshot["motors"]))
            state = "COMPUTED_AT_RESIDUAL_MET_POINT"
        completed = deepcopy({
            "status": "COMPUTED_EXPERIMENTAL",
            "diagnostics_complete": True,
            "stages": stages,
            "transfers": transfers,
            "outputs": {
                "solve": raw["outputs"]["solve"],
                "power_state": state, "power": power,
            },
            "output_units": {
                "solve": raw["output_units"]["solve"],
                "power_state": "not_applicable", "power": units,
            },
        })
        result.update(completed)
    except Exception:  # noqa: BLE001 - contain execution and returned-contract failures
        result.update({
            "status": "EXECUTION_FAILED",
            "diagnostics_complete": False,
            "reasons": ["Solved DC power execution failed."],
            "stages": [], "transfers": {}, "outputs": {}, "output_units": {},
        })
    return deepcopy(result)
