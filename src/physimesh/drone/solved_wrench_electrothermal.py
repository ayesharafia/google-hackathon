import math
import re
from copy import deepcopy

from . import electrothermal_mission as em
from . import solved_wrench_power as sp
from . import thermal as th
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "solved_wrench_electrothermal_mission_experimental"


def _power_request(segment):
    return {
        "evaluation": sp.EVALUATION,
        "solve": deepcopy(segment["solve"]),
        "conversion": deepcopy(segment["conversion"]),
    }


def _preflight(request):
    _json(request, budget=65536)
    snapshot = deepcopy(request)

    def number(value):
        return _normal(value)

    def source(value, limit=2000):
        _require(type(value) is str and 0 < len(value.strip()) and len(value) <= limit)

    def exact(value, keys):
        _require(type(value) is dict)
        _require(all(type(key) is str for key in value) and set(value) == set(keys))

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
    initial = number(body["initial_temperature_k"])
    _require(mass > 0 and cp > 0 and initial > 0)
    _require(0 <= number(body["lumped_biot_number"]) <= 0.1)
    source(body["property_source"])
    _require(th.checked_product(mass, cp) > 0)
    segments = snapshot["segments"]
    _require(type(segments) is list and 1 <= len(segments) <= 16)
    seen = set()
    work = 0
    for segment in segments:
        exact(segment, ("id", "duration_s", "solve", "conversion", "thermal"))
        source(segment["id"], 64)
        _require(segment["id"] not in seen)
        seen.add(segment["id"])
        _require(number(segment["duration_s"]) > 0)
        thermal = segment["thermal"]
        exact(thermal, (
            "ambient_temperature_k", "conductance_w_k",
            "heat_fraction_of_electrical_input", "heat_source",
        ))
        _require(number(thermal["ambient_temperature_k"]) > 0)
        _require(number(thermal["conductance_w_k"]) >= 0)
        _require(0 <= number(thermal["heat_fraction_of_electrical_input"]) <= 1)
        source(thermal["heat_source"])
        core = sp._preflight(_power_request(segment))
        annuli = sum(
            node["inputs"]["annuli"]
            for node in core["solve"]["assembly_template"]["graph"]["nodes"]
            if node["model"] == "isolated_hover_bemt_experimental"
        )
        work += annuli * (core["solve"]["max_evaluations"] + 1)
    _require(work <= 32768)
    fraction = _normal(1 - reserve)
    _require(fraction > 0)
    budget = th.checked_product(usable, fraction)
    _require(budget > 0)
    held = th.checked_difference(usable, budget)
    _require(held >= 0)
    if reserve > 0:
        _require(held > 0 and budget < usable)
    return snapshot


def _solve_outputs(outputs, units, spec):
    def field(obj, key):
        return obj[key]

    def vector(value, name):
        return sp.ws.ra._vector(value)

    _require(type(outputs) is dict and set(outputs) == {
        "outcome", "evaluations_used", "candidates",
        "selected_candidate", "assembly",
    })
    used = outputs["evaluations_used"]
    _require(type(used) is int and 2 <= used <= field(spec, "max_evaluations"))
    candidates = outputs["candidates"]
    _require(type(candidates) is list and len(candidates) == used)
    bounds = field(spec, "rotor_speed_bounds")
    for candidate in candidates:
        _require(type(candidate) is dict)
        for value in candidate.values():
            if type(value) is list:
                for number in value:
                    _normal(number)
            else:
                _normal(value)
        speeds = candidate["angular_speeds_rad_s"]
        _require(type(speeds) is list and len(speeds) == len(bounds))
        for speed, bracket in zip(speeds, bounds):
            _require(type(speed) is not bool and _normal(speed) > 0
                     and bracket["angular_speed_bracket_rad_s"][0] <= speed
                     <= bracket["angular_speed_bracket_rad_s"][1])
        for key in ("net_force_body_n", "net_moment_cg_body_nm"):
            vector(candidate[key], key)
        expected = sp.ws._candidate(spec, speeds, {"outputs": {
            "net_force_body_n": candidate["net_force_body_n"],
            "net_moment_cg_body_nm": candidate["net_moment_cg_body_nm"],
        }})
        _require(candidate == expected)
    selected = outputs["selected_candidate"]
    _require(type(selected) is dict and selected == candidates[-1]
             and selected == min(candidates, key=lambda c: c["max_scaled_residual"]))
    for value in selected.values():
        if type(value) is list:
            for number in value:
                _normal(number)
        else:
            _normal(value)
    _require(outputs["outcome"] == "RESIDUAL_MET"
             if selected["max_scaled_residual"] <= 1
             else outputs["outcome"] in ("EVALUATION_LIMIT", "SOLVER_STOPPED"))
    _require(type(units) is dict and units == {
        "outcome": "not_applicable", "evaluations_used": "1",
        "candidates": [sp.ws._candidate_units() for _ in candidates],
        "selected_candidate": sp.ws._candidate_units(),
        "assembly": sp.ls._assembly_units(),
    })
    assembly = outputs["assembly"]
    _require(type(assembly) is dict and set(assembly) == {
        "rotors", "gravity_force_body_n", "net_force_body_n", "net_moment_cg_body_nm",
    })
    rotors = assembly["rotors"]
    template = field(field(spec, "assembly_template"), "rotors")
    _require(type(rotors) is list and len(rotors) == len(template))
    for rotor, reference in zip(rotors, template):
        _require(type(rotor) is dict and set(rotor) == {
            "node", "force_body_n", "reaction_torque_body_nm", "moment_cg_body_nm",
        })
        _require(rotor["node"] == field(reference, "node"))
        for key in ("force_body_n", "reaction_torque_body_nm", "moment_cg_body_nm"):
            vector(rotor[key], key)
    for key in ("gravity_force_body_n", "net_force_body_n", "net_moment_cg_body_nm"):
        vector(assembly[key], key)
    for i in range(3):
        force = math.fsum([r["force_body_n"][i] for r in rotors]
                          + [assembly["gravity_force_body_n"][i]])
        moment = math.fsum(r["moment_cg_body_nm"][i] for r in rotors)
        _require(math.isclose(force, assembly["net_force_body_n"][i],
                             rel_tol=1e-12, abs_tol=1e-12))
        _require(math.isclose(moment, assembly["net_moment_cg_body_nm"][i],
                             rel_tol=1e-12, abs_tol=1e-12))
    for key in ("net_force_body_n", "net_moment_cg_body_nm"):
        _require(assembly[key] == selected[key])
    return selected


def _power_outputs(power, units, spec, conversion, selected):
    _require(type(power) is dict)
    _require(set(power) == {
        "rotors", "total_shaft_power_w",
        "total_electrical_power_w", "auxiliary_power_w",
    })
    speeds = selected["angular_speeds_rad_s"]
    nodes = [r["node"] for r in spec["assembly_template"]["rotors"]]
    n = len(nodes)
    _require(type(units) is dict)
    _require(units == sp._power_units(n))
    rows = power["rotors"]
    _require(type(rows) is list)
    _require(len(rows) == n)
    _require(len(spec["assembly_template"]["rotors"]) == n)
    _require(len(conversion["rotors"]) == n)
    row_keys = {
        "node", "angular_speed_rad_s", "shaft_power_w",
        "shaft_torque_nm", "conversion_efficiency", "electrical_power_w",
    }
    shaft_powers = []
    electrical_powers = []
    for i, row in enumerate(rows):
        _require(type(row) is dict)
        _require(set(row) == row_keys)
        template = spec["assembly_template"]["rotors"][i]
        converted = conversion["rotors"][i]
        _require(row["node"] == nodes[i])
        _require(row["node"] == template["node"])
        _require(row["node"] == converted["node"])
        for key in row_keys - {"node"}:
            _require(type(row[key]) is not bool)
        omega = row["angular_speed_rad_s"]
        shaft = row["shaft_power_w"]
        torque = row["shaft_torque_nm"]
        eta = row["conversion_efficiency"]
        electrical = row["electrical_power_w"]
        _require(_normal(omega) > 0)
        _require(omega == speeds[i])
        _require(0 < _normal(eta) <= 1)
        _require(eta == converted["conversion_efficiency"])
        _require(_normal(shaft) >= 0)
        _require(_normal(torque) >= 0)
        _require(math.isclose(
            _normal(shaft), _normal(torque * omega),
            rel_tol=1e-12, abs_tol=1e-12,
        ))
        _require(_normal(electrical) >= 0)
        _require(electrical == _normal(shaft / eta))
        shaft_powers.append(shaft)
        electrical_powers.append(electrical)
    auxiliary = power["auxiliary_power_w"]
    _require(type(auxiliary) is not bool)
    _require(_normal(auxiliary) >= 0)
    _require(auxiliary == conversion["auxiliary_power_w"])
    total_shaft = power["total_shaft_power_w"]
    total_electrical = power["total_electrical_power_w"]
    _require(type(total_shaft) is not bool)
    _require(type(total_electrical) is not bool)
    _require(_normal(total_shaft) >= 0)
    _require(_normal(total_electrical) >= 0)
    _require(total_shaft == sp._power_sum(shaft_powers))
    _require(
        total_electrical == sp._power_sum(electrical_powers + [auxiliary])
    )


def _validated_power_result(raw, request):
    sp.ls.ld._valid(raw, sp.EVALUATION, request)
    out, units = raw["outputs"], raw["output_units"]
    keys = {"solve", "power_state", "power"}
    _require(type(out) is dict and set(out) == keys)
    _require(type(units) is dict and set(units) == keys)
    _require(units["power_state"] == "not_applicable")

    spec = request["solve"]
    selected = _solve_outputs(out["solve"], units["solve"], spec)
    expected_stages = [("solve", spec)]
    transfers = raw["transfers"]
    _require(type(transfers) is dict)

    if out["solve"]["outcome"] != "RESIDUAL_MET":
        _require(out["power_state"] == "NOT_RUN_RESIDUAL_UNMET")
        _require(out["power"] is None)
        _require(units["power"] is None)
        _require(transfers == {})
    else:
        _require(out["power_state"] == "COMPUTED_AT_RESIDUAL_MET_POINT")
        _power_outputs(
            out["power"], units["power"], spec,
            request["conversion"], selected,
        )
        speeds = selected["angular_speeds_rad_s"]
        _require(transfers == {
            "angular_speeds_rad_s": speeds,
            "source": "solve_selected_candidate",
        })
        expected_stages.append(("power_graph", sp._power_graph(spec, speeds)))

        rotors = out["solve"]["assembly"]["rotors"]
        templates = spec["assembly_template"]["rotors"]
        rows = out["power"]["rotors"]
        for rotor, template, row in zip(rotors, templates, rows, strict=True):
            _require(rotor["node"] == row["node"] == template["node"])
            axis = sp.ws.ra._unit(template["axis_body"])
            signed_torque = _normal(
                -template["rotation_sign"] * row["shaft_torque_nm"]
            )
            reaction = rotor["reaction_torque_body_nm"]
            _require(len(reaction) == len(axis) == 3)
            for actual, component in zip(reaction, axis, strict=True):
                expected = _normal(signed_torque * component)
                _require(math.isclose(
                    _normal(actual), expected, rel_tol=1e-12, abs_tol=1e-12,
                ))

    stages = raw["stages"]
    _require(type(stages) is list and len(stages) == len(expected_stages))
    for stage, (stage_id, stage_input) in zip(
        stages, expected_stages, strict=True,
    ):
        _require(type(stage) is dict and set(stage) == {
            "stage_id", "request_sha256", "result_sha256",
        })
        _require(stage["stage_id"] == stage_id)
        _require(stage["request_sha256"] == sha256_record(stage_input))
        result_hash = stage["result_sha256"]
        _require(
            type(result_hash) is str
            and re.fullmatch(r"[0-9a-f]{64}", result_hash) is not None
        )
    return deepcopy(raw)


def _energy(snapshot, rows):
    rows = list(rows)
    declared_segments = snapshot["segments"]
    _require(len(rows) == len(declared_segments))

    usable = _normal(snapshot["usable_energy_j"])
    reserve = _normal(snapshot["reserve_fraction"])
    _require(math.isfinite(usable) and usable >= 0)
    _require(math.isfinite(reserve) and 0 <= reserve <= 1)
    budget = th.checked_product(usable, 1 - reserve)
    held = th.checked_difference(usable, budget)

    energy_segments, thermal_segments, transfers = [], [], []
    energies, durations, seen = [], [], set()
    for declared, row in zip(declared_segments, rows):
        segment_id = declared["id"]
        _require(row["segment_id"] == segment_id)
        _require(segment_id not in seen)
        seen.add(segment_id)

        duration = _normal(row["duration_s"])
        _require(duration == _normal(declared["duration_s"]))
        _require(math.isfinite(duration) and duration >= 0)
        electric = _normal(row["power"]["total_electrical_power_w"])
        _require(math.isfinite(electric) and electric >= 0)

        thermal = declared["thermal"]
        fraction = _normal(thermal["heat_fraction_of_electrical_input"])
        _require(math.isfinite(fraction) and 0 <= fraction <= 1)
        heat = th.checked_product(electric, fraction)
        _require(0 <= heat <= electric)
        if fraction > 0 and electric > 0:
            _require(heat > 0)

        segment_energy = th.checked_product(electric, duration)
        energies.append(segment_energy)
        durations.append(duration)
        cumulative = sp._power_sum(energies)
        energy_segments.append({
            "segment_id": segment_id,
            "duration_s": duration,
            "electrical_power_w": electric,
            "segment_energy_j": segment_energy,
            "cumulative_energy_j": cumulative,
            "remaining_budget_j": th.checked_difference(budget, cumulative),
        })
        thermal_segments.append({
            "duration_s": duration,
            "ambient_temperature_k": deepcopy(thermal["ambient_temperature_k"]),
            "heat_input_w": heat,
            "conductance_w_k": deepcopy(thermal["conductance_w_k"]),
        })
        transfers.append({
            "segment_id": segment_id,
            "electrical_power_w": electric,
            "heat_fraction_of_electrical_input": fraction,
            "heat_input_w": heat,
            "heat_source": deepcopy(thermal["heat_source"]),
        })

    total = sp._power_sum(energies)
    remaining = th.checked_difference(budget, total)
    energy = {
        "segments": energy_segments,
        "elapsed_s": sp._power_sum(durations),
        "total_energy_j": total,
        "total_energy_wh": th.checked_quotient(total, 3600),
        "held_reserve_j": held,
        "mission_budget_j": budget,
        "remaining_budget_j": remaining,
        "budget_status": (
            "WITHIN_DECLARED_ENERGY" if remaining >= 0
            else "EXCEEDS_DECLARED_ENERGY"
        ),
    }
    thermalreq = {
        "evaluation": "lumped_thermal_screening",
        **deepcopy(snapshot["thermal_body"]),
        "segments": thermal_segments,
    }
    return energy, thermalreq, transfers


def _energy_units():
    return {
        "segments": {
            "segment_id": "not_applicable",
            "duration_s": "s",
            "electrical_power_w": "W",
            "segment_energy_j": "J",
            "cumulative_energy_j": "J",
            "remaining_budget_j": "J",
        },
        "elapsed_s": "s",
        "total_energy_j": "J",
        "total_energy_wh": "Wh",
        "held_reserve_j": "J",
        "mission_budget_j": "J",
        "remaining_budget_j": "J",
        "budget_status": "not_applicable",
    }


def evaluate_solved_wrench_electrothermal(request):
    result = {
        "evaluation": EVALUATION,
        "status": "GRAPH_INVALID",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "diagnostics_complete": False,
        "reasons": [],
        "stages": [],
        "transfers": [],
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Scientifically unqualified experimental computation.",
            "Caller-declared isolated static segments.",
            "No flight dynamics, mass closure, or heat feedback.",
            "No physical validation or aircraft feasibility established.",
            "Heat fraction is caller-declared, not inferred as 1 - eta.",
            "Hashes do not establish physical proof or runtime identity.",
            (
                "diagnostics_complete describes the returned workflow decision; "
                "a stopped mission contains partial power rows, not full-mission "
                "energy or thermal results."
            ),
        ],
    }
    errors = (
        ValueError, TypeError, OverflowError, UnicodeError,
        RecursionError, KeyError, ZeroDivisionError,
    )
    try:
        snapshot = _preflight(request)
    except errors:
        result["reasons"] = ["Invalid solved wrench electrothermal request."]
        return deepcopy(result)
    try:
        result["request_sha256"] = sha256_record(snapshot)
        stages, rows, powerunits = [], [], []
        transfers = []
        energy, thermal = None, None
        energy_units, thermal_units = None, None
        state = "STOPPED_AT_UNMET_SEGMENT"
        for index, segment in enumerate(snapshot["segments"]):
            powerreq = _power_request(segment)
            raw = sp.evaluate_solved_wrench_power(deepcopy(powerreq))
            _validated_power_result(raw, powerreq)
            stages.append({
                "stage_id": f"power_{index}",
                "request_sha256": sha256_record(powerreq),
                "result_sha256": sha256_record(raw),
            })
            rows.append({
                "segment_id": segment["id"],
                "duration_s": segment["duration_s"],
                "power": raw["outputs"]["power"],
                "solve": raw["outputs"]["solve"],
                "power_state": raw["outputs"]["power_state"],
            })
            powerunits.append({
                "segment_id": "not_applicable",
                "duration_s": "s",
                "power": raw["output_units"]["power"],
                "solve": raw["output_units"]["solve"],
                "power_state": "not_applicable",
            })
            if raw["outputs"]["solve"]["outcome"] != "RESIDUAL_MET":
                break
        else:
            energy, thermalreq, transfers = _energy(snapshot, rows)
            raw = th.screen_thermal(deepcopy(thermalreq))
            em._validated_thermal(raw, thermalreq)
            _require(raw["outputs"]["elapsed_s"] == energy["elapsed_s"])
            stages.append({
                "stage_id": "thermal",
                "request_sha256": sha256_record(thermalreq),
                "result_sha256": sha256_record(raw),
            })
            thermal = raw["outputs"]
            energy_units = _energy_units()
            thermal_units = raw["output_units"]
            state = "COMPUTED_FROM_RESIDUAL_MET_SEGMENTS"
        completed = deepcopy({
            "status": "COMPUTED_EXPERIMENTAL",
            "diagnostics_complete": True,
            "stages": stages,
            "transfers": transfers,
            "outputs": {
                "mission_state": state,
                "power_segments": rows,
                "energy": energy,
                "thermal": thermal,
            },
            "output_units": {
                "mission_state": "not_applicable",
                "power_segments": powerunits,
                "energy": energy_units,
                "thermal": thermal_units,
            },
        })
        result.update(completed)
    except Exception:  # noqa: BLE001 - contain execution and contract failures
        result.update({
            "status": "EXECUTION_FAILED",
            "diagnostics_complete": False,
            "reasons": ["Solved wrench electrothermal execution failed."],
            "stages": [], "transfers": [], "outputs": {}, "output_units": {},
        })
    return deepcopy(result)
