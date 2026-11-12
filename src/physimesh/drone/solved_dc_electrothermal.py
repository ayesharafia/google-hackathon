import math
import re
from copy import deepcopy

from . import electrothermal_mission as em
from . import solved_dc_power as dp
from . import solved_wrench_electrothermal as se
from . import thermal as th
from .graph_mission import _normal, _require
from .provenance import sha256_record

EVALUATION = "solved_dc_electrothermal_mission_experimental"


def _mission_json(value):
    remaining = 65536

    def visit(v, depth):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 12:
            raise ValueError("JSON depth or node budget exceeded")
        kind = type(v)
        if kind is str:
            if len(v) > 2000:
                raise ValueError("JSON string limit exceeded")
            v.encode("utf-8")
        elif kind is int:
            if v.bit_length() > 1023:
                raise ValueError("JSON integer limit exceeded")
        elif kind is float:
            if not math.isfinite(v):
                raise ValueError("Nonfinite JSON number")
        elif kind in (list, dict):
            if len(v) > 256:
                raise ValueError("JSON container limit exceeded")
            if kind is dict:
                for key, item in v.items():
                    if type(key) is not str:
                        raise ValueError("JSON keys must be strings")
                    visit(key, depth + 1)
                    visit(item, depth + 1)
            else:
                for item in v:
                    visit(item, depth + 1)
        elif v is not None and kind is not bool:
            raise ValueError("Builtin JSON required")
    visit(value, 1)


def _preflight(request):
    _mission_json(request)
    snapshot = deepcopy(request)

    def exact(value, keys):
        _require(type(value) is dict)
        _require(all(type(key) is str for key in value) and set(value) == set(keys))

    def source(value, limit=2000):
        _require(type(value) is str and bool(value.strip()) and len(value) <= limit)

    def number(value):
        _require(type(value) in (int, float))
        return _normal(value)

    exact(snapshot, (
        "evaluation", "usable_energy_j", "reserve_fraction", "thermal_body", "segments",
    ))
    _require(type(snapshot["evaluation"]) is str and snapshot["evaluation"] == EVALUATION)
    usable = number(snapshot["usable_energy_j"])
    reserve = number(snapshot["reserve_fraction"])
    _require(usable > 0 and 0 <= reserve < 1)
    body = snapshot["thermal_body"]
    exact(body, (
        "mass_kg", "specific_heat_j_kg_k", "initial_temperature_k",
        "lumped_biot_number", "property_source",
    ))
    mass = number(body["mass_kg"])
    cp = number(body["specific_heat_j_kg_k"])
    _require(mass > 0 and cp > 0 and number(body["initial_temperature_k"]) > 0)
    _require(0 <= number(body["lumped_biot_number"]) <= 0.1)
    source(body["property_source"])
    _require(th.checked_product(mass, cp) > 0)
    segments = snapshot["segments"]
    _require(type(segments) is list and 1 <= len(segments) <= 16)
    seen, work = set(), 0
    for segment in segments:
        exact(segment, ("id", "duration_s", "point", "thermal"))
        source(segment["id"], 64)
        _require(segment["id"] not in seen)
        seen.add(segment["id"])
        _require(number(segment["duration_s"]) > 0)
        thermal = segment["thermal"]
        exact(thermal, ("ambient_temperature_k", "conductance_w_k"))
        _require(number(thermal["ambient_temperature_k"]) > 0)
        _require(number(thermal["conductance_w_k"]) >= 0)
        point = dp._preflight(segment["point"])
        segment["point"] = point
        annuli = sum(
            node["inputs"]["annuli"]
            for node in point["solve"]["assembly_template"]["graph"]["nodes"]
            if node["model"] == "isolated_hover_bemt_experimental"
        )
        work += annuli * (point["solve"]["max_evaluations"] + 1)
    _require(work <= 32768)
    fraction = _normal(th.checked_difference(1, reserve))
    _require(fraction > 0)
    budget = th.checked_product(usable, fraction)
    _require(budget > 0)
    held = th.checked_difference(usable, budget)
    _require(held >= 0)
    if reserve > 0:
        _require(held > 0 and budget < usable)
    dp.sp._power_sum(segment["duration_s"] for segment in segments)
    return snapshot


def _typed_equal(actual, expected):
    if type(expected) in (int, float):
        return type(actual) in (int, float) and _normal(actual) == expected
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return (all(type(key) is str for key in actual) and actual.keys() == expected.keys()
                and all(_typed_equal(actual[key], value) for key, value in expected.items()))
    if type(expected) is list:
        return (len(actual) == len(expected)
                and all(_typed_equal(a, e) for a, e in zip(actual, expected, strict=True)))
    return type(expected) in (type(None), str, bool) and actual == expected


def _point_outputs(raw, request):
    # Output checks only; complete stage/transfer/provenance validation is separate.
    dp.sp.ls.ld._valid(raw, dp.EVALUATION, request)
    rows, selected = _point_output_values(raw["outputs"], raw["output_units"], request)
    if rows is None:
        _require(_typed_equal(raw["transfers"], {"solved_wrench_power": {}}))
        stages = raw["stages"]
        _require(type(stages) is list and len(stages) == 1)
        _require(type(stages[0]) is dict and stages[0].get("stage_id") == "solved_wrench_power")
    return rows, selected


def _point_output_values(out, units, request):
    keys = {"solve", "power_state", "power"}
    _require(type(out) is dict and set(out) == keys)
    _require(type(units) is dict and all(type(key) is str for key in units)
             and set(units) == keys)
    _require(_typed_equal(units["power_state"], "not_applicable"))
    spec = request["solve"]
    selected = se._solve_outputs(out["solve"], units["solve"], spec)
    _require(_typed_equal(units["solve"], {
        "outcome": "not_applicable", "evaluations_used": "1",
        "candidates": [dp.sp.ws._candidate_units() for _ in out["solve"]["candidates"]],
        "selected_candidate": dp.sp.ws._candidate_units(),
        "assembly": dp.sp.ls._assembly_units(),
    }))
    if out["solve"]["outcome"] != "RESIDUAL_MET":
        _require(_typed_equal(out["power_state"], "NOT_RUN_RESIDUAL_UNMET"))
        _require(out["power"] is None and units["power"] is None)
        return deepcopy((None, selected))
    _require(_typed_equal(out["power_state"], "COMPUTED_AT_RESIDUAL_MET_POINT"))
    entries = request["motors"]
    _require(_typed_equal(units["power"], dp._power_units(len(entries))))
    power = out["power"]
    _require(type(power) is dict and set(power) == set(dp._power_units(len(entries))))
    rows = power["motors"]
    templates = spec["assembly_template"]["rotors"]
    rotors = out["solve"]["assembly"]["rotors"]
    speeds = selected["angular_speeds_rad_s"]
    _require(type(rows) is list and len(rows) == len(entries) == len(templates) == len(speeds))
    expected_rows = []
    for row, entry, template, rotor, omega in zip(
        rows, entries, templates, rotors, speeds, strict=True,
    ):
        _require(type(row) is dict and set(row) == {
            "node", "angular_speed_rad_s", "shaft_torque_nm", "motor",
            "allocated_heat_w", "unallocated_loss_w",
        })
        _require(entry["node"] == template["node"] == rotor["node"])
        torque = _normal(row["shaft_torque_nm"])
        _require(_normal(omega) > 0 and torque >= 0)
        motor = dp.dc._compute(dp._motor_request(entry, omega, torque))
        _require(_typed_equal(row["motor"], motor))
        _require(math.isclose(motor["shaft_power_w"], th.checked_product(torque, omega),
                             rel_tol=1e-12, abs_tol=1e-12))
        axis = dp.sp.ws.ra._unit(template["axis_body"])
        signed = th.checked_product(-template["rotation_sign"], torque)
        for actual, component in zip(rotor["reaction_torque_body_nm"], axis, strict=True):
            _require(math.isclose(_normal(actual), th.checked_product(signed, component),
                                 rel_tol=1e-12, abs_tol=1e-12))
        loss = motor["total_loss_w"]
        heat = th.checked_product(loss, entry["heat_fraction_of_motor_loss"])
        remaining = th.checked_difference(loss, heat)
        _require(0 <= heat <= loss and remaining >= 0)
        expected_row = {
            "node": entry["node"], "angular_speed_rad_s": omega,
            "shaft_torque_nm": torque, "motor": motor,
            "allocated_heat_w": heat, "unallocated_loss_w": remaining,
        }
        _require(_typed_equal(row, expected_row))
        expected_rows.append(expected_row)
    expected = {"motors": expected_rows}
    for name, field in (("total_shaft_power_w", "shaft_power_w"),
                        ("total_motor_electrical_power_w", "electrical_power_w"),
                        ("total_motor_loss_w", "total_loss_w")):
        expected[name] = dp.dc._power_sum(row["motor"][field] for row in expected_rows)
    for name, field in (("total_allocated_motor_heat_w", "allocated_heat_w"),
                        ("total_unallocated_motor_loss_w", "unallocated_loss_w")):
        expected[name] = dp.dc._power_sum(row[field] for row in expected_rows)
    auxiliary = request["auxiliary"]
    aux_power = auxiliary["power_w"]
    aux_heat = th.checked_product(aux_power, auxiliary["heat_fraction"])
    _require(0 <= aux_heat <= aux_power)
    expected["auxiliary_electrical_power_w"] = aux_power
    expected["auxiliary_heat_w"] = aux_heat
    expected["total_electrical_power_w"] = dp.dc._power_sum([
        expected["total_motor_electrical_power_w"], aux_power,
    ])
    expected["total_allocated_heat_w"] = dp.dc._power_sum([
        expected["total_allocated_motor_heat_w"], aux_heat,
    ])
    _require(_typed_equal(power, expected))
    return deepcopy((expected_rows, selected))


def _validated_point(raw, request):
    rows, selected = _point_outputs(raw, request)
    spec = request["solve"]
    expected_stages = [("solved_wrench_power", dp._shaft_request(request))]
    expected_nested = [("solve", spec)]
    transfers = {"solved_wrench_power": {}}
    if rows is not None:
        speeds = selected["angular_speeds_rad_s"]
        expected_nested.append(("power_graph", dp.sp._power_graph(spec, speeds)))
        transfers["solved_wrench_power"] = {
            "angular_speeds_rad_s": speeds, "source": "solve_selected_candidate",
        }
        transfers["motors"] = []
        for index, (entry, row, omega) in enumerate(zip(
            request["motors"], rows, speeds, strict=True,
        )):
            motor_request = dp._motor_request(entry, omega, row["shaft_torque_nm"])
            expected_stages.append((f"motor_{index}", motor_request))
            transfers["motors"].append({
                "node": entry["node"],
                "operating_point": motor_request["operating_point"],
                "source": "validated_selected_shaft_power_row",
                "heat_fraction_of_motor_loss": entry["heat_fraction_of_motor_loss"],
                "heat_source": entry["heat_source"],
            })
        auxiliary = request["auxiliary"]
        transfers["auxiliary"] = {
            **deepcopy(auxiliary),
            "heat_w": th.checked_product(auxiliary["power_w"], auxiliary["heat_fraction"]),
        }
    stages = raw["stages"]
    _require(type(stages) is list and len(stages) == len(expected_stages))
    for index, (stage, (stage_id, stage_request)) in enumerate(zip(
        stages, expected_stages, strict=True,
    )):
        keys = {"stage_id", "request_sha256", "result_sha256"}
        if index == 0:
            keys.add("stages")
        _require(type(stage) is dict and set(stage) == keys)
        _require(_typed_equal(stage["stage_id"], stage_id))
        _require(_typed_equal(stage["request_sha256"], sha256_record(stage_request)))
        digest = stage["result_sha256"]
        _require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None)
    nested = stages[0]["stages"]
    _require(type(nested) is list and len(nested) == len(expected_nested))
    for stage, (stage_id, stage_request) in zip(nested, expected_nested, strict=True):
        _require(type(stage) is dict and set(stage) == {
            "stage_id", "request_sha256", "result_sha256",
        })
        _require(_typed_equal(stage["stage_id"], stage_id))
        _require(_typed_equal(stage["request_sha256"], sha256_record(stage_request)))
        digest = stage["result_sha256"]
        _require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None)
    _require(_typed_equal(raw["transfers"], transfers))
    return deepcopy(raw)


def _energy(snapshot, rows):
    declared = snapshot["segments"]
    _require(type(rows) is list and len(rows) == len(declared))
    usable, reserve = _normal(snapshot["usable_energy_j"]), _normal(snapshot["reserve_fraction"])
    _require(usable > 0 and 0 <= reserve < 1)
    fraction = _normal(th.checked_difference(1, reserve))
    _require(fraction > 0)
    budget = th.checked_product(usable, fraction)
    held = th.checked_difference(usable, budget)
    _require(budget > 0 and held >= 0 and (reserve == 0 or held > 0))
    energy_rows, thermal_rows, transfers, energies, durations = [], [], [], [], []
    for segment, row in zip(declared, rows, strict=True):
        _require(type(row) is dict and set(row) == {
            "segment_id", "duration_s", "power", "solve", "power_state",
        })
        _require(_typed_equal(row["segment_id"], segment["id"]))
        _require(_typed_equal(row["duration_s"], segment["duration_s"]))
        _require(type(row["solve"]) is dict and row["solve"]["outcome"] == "RESIDUAL_MET")
        _require(_typed_equal(row["power_state"], "COMPUTED_AT_RESIDUAL_MET_POINT"))
        duration = _normal(row["duration_s"])
        power = row["power"]
        _require(type(power) is dict)
        electric = _normal(power["total_electrical_power_w"])
        heat = _normal(power["total_allocated_heat_w"])
        _require(duration > 0 and electric >= 0 and heat >= 0)
        energy_j = th.checked_product(electric, duration)
        energies.append(energy_j)
        durations.append(duration)
        cumulative = dp.sp._power_sum(energies)
        energy_rows.append({
            "segment_id": segment["id"], "duration_s": duration,
            "electrical_power_w": electric, "segment_energy_j": energy_j,
            "cumulative_energy_j": cumulative,
            "remaining_budget_j": th.checked_difference(budget, cumulative),
        })
        thermal_rows.append({
            "duration_s": duration,
            "ambient_temperature_k": segment["thermal"]["ambient_temperature_k"],
            "heat_input_w": heat, "conductance_w_k": segment["thermal"]["conductance_w_k"],
        })
        transfers.append({
            "segment_id": segment["id"], "electrical_power_w": electric,
            "heat_input_w": heat, "source": "validated_dc_power_loss_allocation",
        })
    total = dp.sp._power_sum(energies)
    remaining = th.checked_difference(budget, total)
    energy = {
        "segments": energy_rows, "elapsed_s": dp.sp._power_sum(durations),
        "total_energy_j": total, "total_energy_wh": th.checked_quotient(total, 3600),
        "held_reserve_j": held, "mission_budget_j": budget, "remaining_budget_j": remaining,
        "budget_status": "WITHIN_DECLARED_ENERGY" if remaining >= 0 else "EXCEEDS_DECLARED_ENERGY",
    }
    thermalreq = {
        "evaluation": "lumped_thermal_screening", **deepcopy(snapshot["thermal_body"]),
        "segments": thermal_rows,
    }
    return energy, thermalreq, transfers


def _energy_units():
    return se._energy_units()


def _validated_heat(raw, request):
    em._validated_thermal(raw, request)
    _heat_output_values(raw["outputs"], raw["output_units"], request)
    return deepcopy(raw)


def _heat_output_values(outputs, units, request):
    row_units = {
        "index": "1", "duration_s": "s", "cumulative_elapsed_s": "s",
        "start_temperature_k": "K", "end_temperature_k": "K",
        "ambient_temperature_k": "K", "heat_input_j": "J",
        "thermal_storage_change_j": "J", "convective_exchange_j": "J",
        "energy_balance_residual_j": "J",
    }
    expected_units = {
        "segments": row_units, "elapsed_s": "s",
        "final_temperature_k": "K", "maximum_temperature_k": "K",
        "total_heat_input_j": "J", "total_storage_change_j": "J",
        "total_convective_exchange_j": "J", "total_energy_balance_residual_j": "J",
    }
    _require(_typed_equal(units, expected_units))
    _require(type(outputs) is dict and all(type(key) is str for key in outputs)
             and set(outputs) == set(expected_units))
    rows = outputs["segments"]
    _require(type(rows) is list and len(rows) == len(request["segments"]) and bool(rows))
    for key in outputs.keys() - {"segments"}:
        _normal(outputs[key])
    mass, cp, previous = (
        th._number(_normal(request[key]))
        for key in ("mass_kg", "specific_heat_j_kg_k", "initial_temperature_k")
    )
    capacity = th.checked_product(mass, cp)
    _require(capacity > 0 and previous > 0)
    elapsed, maximum, expected_rows = 0.0, previous, []
    for index, (row, segment) in enumerate(zip(
        rows, request["segments"], strict=True,
    )):
        _require(type(row) is dict and all(type(key) is str for key in row)
                 and set(row) == set(row_units))
        _require(type(row["index"]) is int and row["index"] == index)
        for key in row_units.keys() - {"index"}:
            _normal(row[key])
        _require(all(row[key] > 0 for key in (
            "duration_s", "cumulative_elapsed_s", "start_temperature_k",
            "end_temperature_k", "ambient_temperature_k",
        )))
        _require(row["duration_s"] == segment["duration_s"]
                 and row["ambient_temperature_k"] == segment["ambient_temperature_k"])
        if row["heat_input_j"] != segment["heat_input_w"] * segment["duration_s"]:
            raise ValueError("Thermal row heat input does not match the segment")
        if (row["energy_balance_residual_j"] != row["heat_input_j"]
                - row["thermal_storage_change_j"] - row["convective_exchange_j"]):
            raise ValueError("Thermal row energy balance residual is inconsistent")
        _require(row["cumulative_elapsed_s"] == elapsed + row["duration_s"]
                 and row["start_temperature_k"] == previous)
        duration, ambient, heat, conductance = (
            th._number(_normal(segment[key]))
            for key in ("duration_s", "ambient_temperature_k", "heat_input_w", "conductance_w_k")
        )
        _require(duration > 0 and ambient > 0 and heat >= 0 and conductance >= 0)
        end, input_j, stored, convective, residual = th.integrate_segment(
            capacity, previous, ambient, heat, conductance, duration,
        )
        new_elapsed = _normal(elapsed + duration)
        _require(new_elapsed > elapsed)
        expected_row = {
            "index": index, "duration_s": duration, "cumulative_elapsed_s": new_elapsed,
            "start_temperature_k": previous, "end_temperature_k": end,
            "ambient_temperature_k": ambient, "heat_input_j": input_j,
            "thermal_storage_change_j": stored, "convective_exchange_j": convective,
            "energy_balance_residual_j": residual,
        }
        _require(_typed_equal(row, expected_row))
        expected_rows.append(expected_row)
        elapsed, previous, maximum = new_elapsed, end, max(maximum, end)
    expected = {
        "segments": expected_rows, "elapsed_s": elapsed,
        "final_temperature_k": previous, "maximum_temperature_k": maximum,
    }
    for total, field in (
        ("total_heat_input_j", "heat_input_j"),
        ("total_storage_change_j", "thermal_storage_change_j"),
        ("total_convective_exchange_j", "convective_exchange_j"),
    ):
        _require(outputs[total] == math.fsum(row[field] for row in rows))
        expected[total] = _normal(math.fsum(row[field] for row in expected_rows))
    _require(outputs["total_energy_balance_residual_j"] == outputs["total_heat_input_j"]
             - outputs["total_storage_change_j"] - outputs["total_convective_exchange_j"])
    expected["total_energy_balance_residual_j"] = _normal(
        expected["total_heat_input_j"] - expected["total_storage_change_j"]
        - expected["total_convective_exchange_j"]
    )
    _require(_typed_equal(outputs, expected))
    return deepcopy(outputs)


def evaluate_solved_dc_electrothermal(request):
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
        "transfers": [],
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Scientifically unqualified experimental mission computation; physical validation is not established.",
            "Chronological static point models do not establish installed-flight trim or aircraft feasibility.",
            "Caller-declared constant-parameter DC equivalent; no BLDC phase conversion or ESC execution.",
            "Declared motor-loss capture and auxiliary heat fractions are unverified thermal allocations.",
            "Constant-property lumped thermal screening has no temperature feedback to point models.",
            "No battery, bus current, SOC, regeneration, control authority or actual aircraft validation.",
            "Declared limits and energy screens do not establish continuous ratings or thermal adequacy.",
            "Hashes record actual request/result provenance, not physical proof or runtime identity.",
        ],
    }
    errors = (
        ValueError, TypeError, OverflowError, UnicodeError,
        RecursionError, KeyError, ZeroDivisionError,
    )
    try:
        snapshot = _preflight(request)
    except errors:
        result["reasons"] = ["Invalid solved DC electrothermal request."]
        return deepcopy(result)
    try:
        result["request_sha256"] = sha256_record(snapshot)
        stages, rows, powerunits, transfers = [], [], [], []
        energy, thermal, energy_units, thermal_units = None, None, None, None
        state = "STOPPED_AT_UNMET_SEGMENT"
        for index, segment in enumerate(snapshot["segments"]):
            point_request = segment["point"]
            raw = dp.evaluate_solved_dc_power(deepcopy(point_request))
            raw = _validated_point(raw, point_request)
            stages.append({
                "stage_id": f"point_{index}",
                "request_sha256": sha256_record(point_request),
                "result_sha256": sha256_record(raw),
                "stages": raw["stages"],
            })
            rows.append({
                "segment_id": segment["id"], "duration_s": segment["duration_s"],
                "power": raw["outputs"]["power"], "solve": raw["outputs"]["solve"],
                "power_state": raw["outputs"]["power_state"],
            })
            powerunits.append({
                "segment_id": "not_applicable", "duration_s": "s",
                "power": raw["output_units"]["power"], "solve": raw["output_units"]["solve"],
                "power_state": raw["output_units"]["power_state"],
            })
            if raw["outputs"]["solve"]["outcome"] != "RESIDUAL_MET":
                break
        else:
            energy, thermalreq, transfers = _energy(snapshot, rows)
            raw = th.screen_thermal(deepcopy(thermalreq))
            raw = _validated_heat(raw, thermalreq)
            _require(_typed_equal(raw["outputs"]["elapsed_s"], energy["elapsed_s"]))
            stages.append({
                "stage_id": "thermal", "request_sha256": sha256_record(thermalreq),
                "result_sha256": sha256_record(raw),
            })
            thermal, thermal_units = raw["outputs"], raw["output_units"]
            energy_units = _energy_units()
            state = "COMPUTED_FROM_RESIDUAL_MET_SEGMENTS"
        completed = deepcopy({
            "status": "COMPUTED_EXPERIMENTAL", "diagnostics_complete": True,
            "stages": stages, "transfers": transfers,
            "outputs": {
                "mission_state": state, "power_segments": rows,
                "energy": energy, "thermal": thermal,
            },
            "output_units": {
                "mission_state": "not_applicable", "power_segments": powerunits,
                "energy": energy_units, "thermal": thermal_units,
            },
        })
        result.update(completed)
    except Exception:  # noqa: BLE001 - contain execution and returned-contract failures
        result.update({
            "status": "EXECUTION_FAILED", "diagnostics_complete": False,
            "reasons": ["Solved DC electrothermal execution failed."],
            "stages": [], "transfers": [], "outputs": {}, "output_units": {},
        })
    return deepcopy(result)
