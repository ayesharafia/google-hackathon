"""Frozen declared ledger bridge to the accepted V99 DC thermal mission.

This is experimental scientific engineering arithmetic, not a discovery or a
physical, numerical, runtime, feasibility, or aircraft qualification.
"""

import math
import re
from copy import deepcopy

from . import ledger_static_wrench as ls
from . import mass
from . import mass_ledger_request as ml
from . import solved_dc_electrothermal as mission
from .graph_mission import _require
from .provenance import sha256_record

EVALUATION = "ledger_solved_dc_electrothermal_mission_experimental"


def _outer_json(value):
    remaining = 98304

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        _require(remaining >= 0 and depth <= 13)
        kind = type(item)
        if kind is str:
            _require(len(item) <= 2000)
            item.encode("utf-8")
        elif kind is int:
            _require(item.bit_length() <= 1023)
        elif kind is float:
            _require(math.isfinite(item))
        elif kind in (dict, list):
            _require(len(item) <= 256)
            if kind is dict:
                for key, child in item.items():
                    _require(type(key) is str)
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
        else:
            _require(item is None or kind is bool)

    visit(value, 1)


def _exact(value, keys):
    _require(type(value) is dict)
    _require(all(type(key) is str for key in value) and set(value) == set(keys))


def _equal(actual, expected):
    _require(mission._typed_equal(actual, expected))


def _mission_input(snapshot, outputs):
    request = deepcopy(snapshot["mission_template"])
    for segment in request["segments"]:
        assembly = segment["point"]["solve"]["assembly_template"]
        assembly["mass_kg"] = deepcopy(outputs["total_mass_kg"])
        assembly["cg_body_m"] = deepcopy(outputs["cg_body_m"])
    return request


def _preflight(request):
    _outer_json(request)
    snapshot = deepcopy(request)
    _exact(snapshot, ("evaluation", "ledger", "mission_template"))
    _equal(snapshot["evaluation"], EVALUATION)
    ml._preflight(snapshot["ledger"])
    template = snapshot["mission_template"]
    _exact(template, (
        "evaluation", "usable_energy_j", "reserve_fraction", "thermal_body", "segments",
    ))
    segments = template["segments"]
    _require(type(segments) is list and 1 <= len(segments) <= 16)
    for segment in segments:
        _exact(segment, ("id", "duration_s", "point", "thermal"))
        point = segment["point"]
        _exact(point, ("evaluation", "solve", "motors", "auxiliary"))
        _require(type(point["solve"]) is dict)
        assembly = point["solve"]["assembly_template"]
        # No caller mass/CG may compete with the frozen ledger transfer.
        _exact(assembly, (
            "evaluation", "graph", "air_node", "rotors",
            "gravity_direction_body", "property_source",
        ))
    # Structural validation only: placeholders never enter reported results or
    # evaluator calls. V99 retains its own JSON and independent child guards,
    # global annuli work bound, reserve/capacity and nonloss duration checks.
    mission._preflight(_mission_input(snapshot, {
        "total_mass_kg": 1, "cg_body_m": [0, 0, 0],
    }))
    return snapshot


def _envelope(raw, evaluation, request, *, with_stages):
    keys = {
        "evaluation", "status", "evidence_level", "physical_validation",
        "numerical_qualification", "runtime_identity", "aircraft_status",
        "feasibility", "diagnostics_complete", "reasons", "outputs",
        "output_units", "limitations", "request_sha256",
    }
    if with_stages:
        keys.update(("stages", "transfers"))
    _exact(raw, keys)
    expected = {
        "evaluation": evaluation, "status": "COMPUTED_EXPERIMENTAL",
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None,
        "diagnostics_complete": True, "reasons": [],
        "request_sha256": sha256_record(request),
    }
    for key, value in expected.items():
        _equal(raw[key], value)
    limitations = raw["limitations"]
    _require(type(limitations) is list and len(limitations) <= 256)
    for text in limitations:
        _require(type(text) is str and len(text) <= 2000)
        text.encode("utf-8")


def _validated_ledger(raw, request):
    # Validate the actual returned ledger envelope, then bind every property to
    # declared items. No second ledger evaluator is invoked.
    ls.ld._valid(raw, ml.EVALUATION, request)
    _envelope(raw, ml.EVALUATION, request, with_stages=False)
    outputs = ls.ld._ledger_outputs(raw)
    entries = [mass.MassItem(
        name=item["name"], category=item["category"], mass_kg=item["mass_kg"],
        cg_body_m=tuple(item["cg_body_m"]),
        inertia_own_cg_body_kgm2=tuple(
            tuple(row) for row in item["inertia_own_cg_body_kgm2"]
        ),
    ) for item in request["items"]]
    summary = mass.summarize(entries, need_inertia=True)
    _require(summary.complete)
    expected = {
        "total_mass_kg": float(summary.total_mass_kg),
        "cg_body_m": [float(value) for value in summary.cg_body_m.tolist()],
        "inertia_cg_body_kgm2": [
            [float(value) for value in row] for row in summary.inertia_cg_body_kgm2.tolist()
        ],
        "payload_kg": float(summary.payload_kg),
        "by_category_kg": {key: float(value) for key, value in summary.by_category.items()},
    }
    _equal(outputs, expected)
    return outputs


def _stage(stage, stage_id, request, *, nested=False):
    keys = {"stage_id", "request_sha256", "result_sha256"}
    if nested:
        keys.add("stages")
    _exact(stage, keys)
    _equal(stage["stage_id"], stage_id)
    _equal(stage["request_sha256"], sha256_record(request))
    digest = stage["result_sha256"]
    _require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None)
    # Child raw envelopes are absent from retained V99 slices. Their result
    # digests are opaque; no reconstructed preimage or authentication is claimed.


def _point_stages(stages, request, rows, selected):
    """Validate actual retained point stages without constructing an envelope.

    This is the stage-only portion of V99's independent point validation:
    requests are reconstructed from the instantiated mission and selected solve.
    Point transfers and solver-internal stages are not retained by V99 and are
    consequently neither invented nor claimed to have been inspected here.
    """
    dp = mission.dp
    spec = request["solve"]
    expected = [("solved_wrench_power", dp._shaft_request(request))]
    nested_expected = [("solve", spec)]
    if rows is not None:
        speeds = selected["angular_speeds_rad_s"]
        nested_expected.append(("power_graph", dp.sp._power_graph(spec, speeds)))
        for index, (entry, row, omega) in enumerate(zip(
            request["motors"], rows, speeds, strict=True,
        )):
            expected.append((f"motor_{index}", dp._motor_request(
                entry, omega, row["shaft_torque_nm"],
            )))
    _require(type(stages) is list and len(stages) == len(expected))
    for index, (stage, (stage_id, child_request)) in enumerate(zip(stages, expected, strict=True)):
        _stage(stage, stage_id, child_request, nested=index == 0)
    nested = stages[0]["stages"]
    _require(type(nested) is list and len(nested) == len(nested_expected))
    for stage, (stage_id, child_request) in zip(nested, nested_expected, strict=True):
        _stage(stage, stage_id, child_request)


def _validated_mission(raw, request):
    # This checks the ACTUAL envelope. Retained slice validators below do not
    # establish envelope status, qualification, request provenance, or stages.
    _envelope(raw, mission.EVALUATION, request, with_stages=True)
    out, units = raw["outputs"], raw["output_units"]
    keys = ("mission_state", "power_segments", "energy", "thermal")
    _exact(out, keys)
    _exact(units, keys)
    _equal(units["mission_state"], "not_applicable")
    declared = request["segments"]
    rows, row_units, stages = out["power_segments"], units["power_segments"], raw["stages"]
    _require(type(rows) is list and 1 <= len(rows) <= len(declared))
    _require(type(row_units) is list and len(row_units) == len(rows))
    _require(type(stages) is list and len(rows) <= len(stages) <= len(rows) + 1)
    unmet = False
    for index, (row, unit, segment) in enumerate(zip(
        rows, row_units, declared[:len(rows)], strict=True,
    )):
        _require(not unmet)
        _exact(row, ("segment_id", "duration_s", "solve", "power_state", "power"))
        _exact(unit, ("segment_id", "duration_s", "solve", "power_state", "power"))
        # Bound each retained slice independently, without imposing a new global
        # output budget on legitimate multi-segment V99 results.
        mission._mission_json(row)
        mission._mission_json(unit)
        _equal(row["segment_id"], segment["id"])
        _equal(row["duration_s"], segment["duration_s"])
        _equal(unit["segment_id"], "not_applicable")
        _equal(unit["duration_s"], "s")
        point = segment["point"]
        # Only output slices are assembled here; never synthetic child envelopes.
        point_out = {key: row[key] for key in ("solve", "power_state", "power")}
        point_units = {key: unit[key] for key in point_out}
        motors, selected = mission._point_output_values(point_out, point_units, point)
        # The accepted slice helper checks bounds and all candidate values, but
        # selected-candidate equality alone can equate bools with numbers.
        _equal(row["solve"]["selected_candidate"], row["solve"]["candidates"][-1])
        _stage(stages[index], f"point_{index}", point, nested=True)
        _point_stages(stages[index]["stages"], point, motors, selected)
        unmet = motors is None
    if unmet:
        _equal(out["mission_state"], "STOPPED_AT_UNMET_SEGMENT")
        _require(len(stages) == len(rows))
        for key in ("energy", "thermal"):
            _equal(out[key], None)
            _equal(units[key], None)
        _equal(raw["transfers"], [])
    else:
        _require(len(rows) == len(declared) and len(stages) == len(rows) + 1)
        _equal(out["mission_state"], "COMPUTED_FROM_RESIDUAL_MET_SEGMENTS")
        energy, thermal_request, transfers = mission._energy(request, rows)
        _equal(out["energy"], energy)
        _equal(units["energy"], mission._energy_units())
        _equal(raw["transfers"], transfers)
        mission._mission_json(out["thermal"])
        mission._mission_json(units["thermal"])
        mission._heat_output_values(out["thermal"], units["thermal"], thermal_request)
        _equal(out["thermal"]["elapsed_s"], energy["elapsed_s"])
        _stage(stages[-1], "thermal", thermal_request)
    return raw


def evaluate_ledger_solved_dc_electrothermal(request):
    result = {
        "evaluation": EVALUATION, "status": "GRAPH_INVALID",
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        "reasons": [], "stages": [], "transfers": {}, "outputs": {}, "output_units": {},
        "limitations": [
            "Experimental scientific engineering arithmetic; no discovery claim.",
            "Frozen declared ledger; no fuel consumption or payload/mass evolution.",
            "Ledger inertia is reported but unused; thermal body mass is separately declared.",
            "Static mission points do not establish flight trim or aircraft feasibility.",
            "Physical validation, numerical qualification and runtime identity are not established.",
            "Retained child result digests are opaque; absent child raw envelopes are not reconstructed.",
            "Energy and thermal screens inherit the accepted V99 model limitations.",
        ],
    }
    try:
        snapshot = _preflight(request)
        request_hash = sha256_record(snapshot)
    except Exception:  # noqa: BLE001 - fail closed, but propagate BaseException
        result["reasons"] = ["Invalid ledger solved DC electrothermal request."]
        return deepcopy(result)
    result["request_sha256"] = request_hash
    try:
        ledger_request = snapshot["ledger"]
        ledger_raw = ml.evaluate_mass_ledger(deepcopy(ledger_request))
        ledger_outputs = _validated_ledger(ledger_raw, ledger_request)
        instantiated = _mission_input(snapshot, ledger_outputs)
        # Validate the entire actual mission before its sole evaluator call.
        mission._preflight(instantiated)
        mission_raw = mission.evaluate_solved_dc_electrothermal(deepcopy(instantiated))
        _validated_mission(mission_raw, instantiated)
        completed = deepcopy({
            "status": "COMPUTED_EXPERIMENTAL", "diagnostics_complete": True,
            "stages": [
                {"stage_id": "ledger", "request_sha256": sha256_record(ledger_request),
                 "result_sha256": sha256_record(ledger_raw)},
                {"stage_id": "mission", "request_sha256": sha256_record(instantiated),
                 "result_sha256": sha256_record(mission_raw), "stages": deepcopy(mission_raw["stages"])},
            ],
            "transfers": {
                "mass_cg": [{
                    "segment_id": segment["id"], "mass_kg": ledger_outputs["total_mass_kg"],
                    "cg_body_m": deepcopy(ledger_outputs["cg_body_m"]),
                    "source": "validated_frozen_mass_ledger",
                } for segment in instantiated["segments"]],
                "mission": deepcopy(mission_raw["transfers"]),
            },
            "outputs": {
                "ledger": deepcopy(ledger_raw["outputs"]), "mission": deepcopy(mission_raw["outputs"]),
            },
            "output_units": {
                "ledger": deepcopy(ledger_raw["output_units"]),
                "mission": deepcopy(mission_raw["output_units"]),
            },
        })
        result.update(completed)
    except Exception:  # noqa: BLE001 - atomic failure; no partial stages or transfers
        result.update({
            "status": "EXECUTION_FAILED", "diagnostics_complete": False,
            "reasons": ["Ledger solved DC electrothermal execution failed."],
            "stages": [], "transfers": {}, "outputs": {}, "output_units": {},
        })
    return deepcopy(result)
