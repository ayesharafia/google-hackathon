"""Bounded HTTP adapter for the actual frozen-ledger DC thermal mission."""

import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from physimesh.drone import ledger_solved_dc_electrothermal as ledger_mission
from physimesh.drone.provenance import sha256_record

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/ledger-solved-dc-electrothermal"
MAX_BODY_BYTES = 131072
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "catalog": "actual_ledger_solved_dc_electrothermal_bridge",
        "evaluation": ledger_mission.EVALUATION,
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "required_root": ["evaluation", "ledger", "mission_template"],
        "root_fields_exact": True,
        "field_shape": {
            "schema_reference": "physimesh.drone.ledger_solved_dc_electrothermal._preflight",
            "ledger": {
                "schema_reference": "physimesh.drone.mass_ledger_request._preflight",
                "fields_exact": True,
                "required": ["evaluation", "items", "property_source"],
                "evaluation": ledger_mission.ml.EVALUATION,
                "property_source": "Nonblank string, at most 2000 characters.",
                "items": {
                    "fields_exact": True,
                    "required": ["name", "category", "mass_kg", "cg_body_m",
                                 "inertia_own_cg_body_kgm2"],
                    "name": "Unique nonblank string, at most 128 characters.",
                    "categories": list(ledger_mission.mass.CATEGORIES),
                    "categories_required": "All six categories must be represented; zero mass items are allowed.",
                    "mass_kg": "Nonnegative finite number; actual ledger total must be positive.",
                    "cg_body_m": "Three finite body-frame coordinates in metres.",
                    "inertia_own_cg_body_kgm2": "Declared 3 by 3 body-frame tensor in kg*m^2; "
                                                 "admissibility follows the accepted mass kernel.",
                },
            },
            "mission_template": {
                "schema_reference": "physimesh.drone.solved_dc_electrothermal._preflight",
                "fields_exact": True,
                "required": ["evaluation", "usable_energy_j", "reserve_fraction", "thermal_body", "segments"],
                "evaluation": ledger_mission.mission.EVALUATION,
                "energy": "Positive usable_energy_j; reserve_fraction in [0,1); finite supported arithmetic.",
                "thermal_body": {
                    "fields_exact": True,
                    "required": ["mass_kg", "specific_heat_j_kg_k", "initial_temperature_k",
                                 "lumped_biot_number", "property_source"],
                    "constraints": "Positive mass, specific heat and temperature; Biot in [0,0.1]; "
                                   "nonblank source. This mass is separately declared and is not ledger mass.",
                },
                "segments": {
                    "fields_exact": True,
                    "required": ["id", "duration_s", "point", "thermal"],
                    "constraints": "Unique nonblank IDs up to 64 characters; positive duration; chronological order.",
                    "thermal": {
                        "fields_exact": True,
                        "required": ["ambient_temperature_k", "conductance_w_k"],
                        "constraints": "Positive ambient temperature; nonnegative conductance.",
                    },
                    "point": {
                        "fields_exact": True,
                        "required": ["evaluation", "solve", "motors", "auxiliary"],
                        "evaluation": "solved_static_wrench_dc_power_experimental",
                        "schema_reference": "physimesh.drone.solved_dc_power._preflight",
                        "solve_reference": "physimesh.drone.static_wrench_solve._preflight",
                        "solve.assembly_template": {
                            "fields_exact": True,
                            "required": ["evaluation", "graph", "air_node", "rotors",
                                         "gravity_direction_body", "property_source"],
                            "must_omit": ["mass_kg", "cg_body_m"],
                            "transfer": "Actual validated frozen ledger mass and CG supply every point; "
                                        "caller values are rejected even if equal to the ledger.",
                        },
                        "motor_reference": "physimesh.drone.dc_motor._preflight",
                        "declarations": "Ordered motors matching solve rotors with parameters, declared limits, "
                                        "motor-loss capture fractions and sources; auxiliary power, "
                                        "heat fraction and source. All accepted child contracts apply.",
                    },
                },
            },
        },
        "limits": {
            "body_bytes": MAX_BODY_BYTES,
            "body_bytes_constraint": "Independent HTTP bound on actual received bytes, including UTF-8 encoding "
                                     "and whitespace. A valid 16-segment, 128-item model request can exceed it; "
                                     "the shape maxima do not promise HTTP acceptance in all combinations.",
            "json_depth": 13, "json_values": 98304, "root_depth": 1,
            "json_values_count": "Visited values including dictionary keys.",
            "json_container_items": 256, "json_string_length": 2000, "json_integer_bits": 1023,
            "ledger": {"json_depth": 10, "json_values": 16384,
                       "items": {"minimum": 1, "maximum": 128}},
            "mission": {"json_depth": 12, "json_values": 65536},
            "segments": {"minimum": 1, "maximum": 16},
            "combined_annuli": 32768,
            "combined_annuli_constraint": "sum(segment_annuli * (segment_max_evaluations + 1)) <= 32768",
            "per_point": {
                "json_depth": 10, "json_values": 49152, "solver_json_values": 32768,
                "motor_json_values": 4096, "rotors": 15, "per_rotor_annuli": 512,
                "max_evaluations": {"type": "integer", "minimum": 2, "maximum": 64},
                "combined_annuli": 32768,
                "combined_annuli_constraint": "point_annuli * (max_evaluations + 1) <= 32768",
            },
        },
        "limitations": {
            "execution": {
                "adapter": "One actual V100 evaluator call in the threadpool; no model duplication.",
                "preflight": "Ledger and all mission segments, including global work, preflight before any "
                             "evaluator. The complete mission with actual ledger mass/CG is preflighted again "
                             "before the mission evaluator.",
                "sequence": ["actual_ledger", "actual_mission"],
                "actual_ledger_calls": 1,
                "actual_mission_calls": 1,
                "call_condition": "After preflight and successful validation of preceding results; "
                                  "failures can stop execution before these calls.",
                "points": "Each reached actual DC point runs once; later points stop at the first unmet residual.",
                "inertia_report_used": False,
                "thermal_body_mass": "Separately declared; never replaced by ledger mass.",
            },
            "mass_cg": "Actual validated ledger mass and CG are frozen across every segment; "
                       "no fuel consumption, payload changes or mass evolution.",
            "loads": "Motor operating points use selected solve speed and validated shaft torque.",
            "energy": "Electrical energy uses selected total electrical power times duration, independently "
                      "of captured heat. Reserve is withheld once and auxiliary power is included once. "
                      "Captured heat is not an additional electrical charge.",
            "heat": "Captured motor loss plus declared auxiliary heat drives one chronological lumped "
                    "thermal evaluation after all residuals meet; no temperature feedback to points.",
            "output_shape": {
                "outputs": ["ledger", "mission"],
                "output_units": ["ledger", "mission"],
                "mission_fields": ["mission_state", "power_segments", "energy", "thermal"],
                "mission_path": "outputs.mission",
                "mission_units_path": "output_units.mission",
            },
            "residual_unmet": {
                "status": "COMPUTED_EXPERIMENTAL",
                "mission_path": "outputs.mission",
                "mission_state": "STOPPED_AT_UNMET_SEGMENT",
                "power_segments": "Reached chronological prefix including the first unmet segment.",
                "energy": None, "thermal": None, "energy_units": None, "thermal_units": None,
                "mission_transfers_path": "transfers.mission",
                "mission_transfers": [],
                "mass_cg_transfers": "Retained for every declared segment, including unreached segments.",
            },
            "all_met_mission_state": "COMPUTED_FROM_RESIDUAL_MET_SEGMENTS",
            "failures": "Model preflight returns GRAPH_INVALID. Execution or returned-contract failures "
                        "return EXECUTION_FAILED with empty outputs, units, stages and transfers.",
            "hashes": "Request/result provenance only; no physical proof or runtime identity. Retained "
                      "child result digests are opaque; absent raw child envelopes are not reconstructed.",
            "no_claims": ["aircraft feasibility", "flight trim", "physical validation", "numerical qualification",
                          "runtime identity", "thermal adequacy", "continuous ratings", "battery qualification",
                          "ESC qualification", "installed-system qualification", "production readiness"],
        },
    }


@router.post("/evaluate")
async def evaluate(request: Request):
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        if type(body) is not dict:
            raise ValueError("Expected object")
        ledger_mission._outer_json(body)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(422, "Invalid ledger solved DC electrothermal request.") from None
    result = await run_in_threadpool(ledger_mission.evaluate_ledger_solved_dc_electrothermal, body)
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result


class LedgerSolvedDCElectrothermalBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] != "POST"
                or scope["path"].rstrip("/") != PREFIX + "/evaluate"):
            return await self.app(scope, receive, send)
        declared = dict(scope["headers"]).get(b"content-length")
        try:
            if declared is not None:
                length = int(declared)
                if length < 0 or length > MAX_BODY_BYTES:
                    return await JSONResponse(
                        {"detail": "request byte budget exceeded"}, status_code=413
                    )(scope, receive, send)
                if not declared.isdigit():
                    raise ValueError("Invalid content length")
        except ValueError:
            return await JSONResponse(
                {"detail": "invalid content length"}, status_code=400
            )(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > MAX_BODY_BYTES:
                    raise HTTPException(413, "request byte budget exceeded")
            return message

        return await self.app(scope, bounded_receive, send)
