"""Bounded HTTP adapter for the actual experimental DC electrothermal mission."""

import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from physimesh.drone import solved_dc_electrothermal as mission
from physimesh.drone.provenance import sha256_record

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/solved-dc-electrothermal"
MAX_BODY_BYTES = 131072
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "catalog": "actual_solved_dc_electrothermal_bridge",
        "evaluation": mission.EVALUATION,
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "required_root": [
            "evaluation", "usable_energy_j", "reserve_fraction", "thermal_body", "segments",
        ],
        "root_fields_exact": True,
        "field_shape": {
            "schema_reference": "physimesh.drone.solved_dc_electrothermal._preflight",
            "thermal_body": {
                "fields_exact": True,
                "required": ["mass_kg", "specific_heat_j_kg_k", "initial_temperature_k",
                             "lumped_biot_number", "property_source"],
                "constraints": "Positive mass, specific heat and temperature; Biot in [0,0.1]; nonblank source.",
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
                    "schema_reference": "physimesh.drone.solved_dc_power._preflight (accepted V96)",
                    "fields_exact": True,
                    "required": ["evaluation", "solve", "motors", "auxiliary"],
                    "evaluation": "solved_static_wrench_dc_power_experimental",
                    "solve_reference": "physimesh.drone.static_wrench_solve._preflight",
                    "motor_reference": "physimesh.drone.dc_motor._preflight",
                    "declarations": "Ordered motors with parameters, declared limits, motor-loss capture "
                                    "fractions/sources; auxiliary power, heat fraction and source.",
                },
            },
            "energy": "Positive usable_energy_j; reserve_fraction in [0,1); finite supported arithmetic.",
        },
        "limits": {
            "body_bytes": MAX_BODY_BYTES,
            "json_depth": 12, "json_values": 65536, "root_depth": 1,
            "json_container_items": 256, "json_string_length": 2000, "json_integer_bits": 1023,
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
            "execution": "All segments preflight before execution; each reached actual V96 point runs once.",
            "loads": "Motor operating points use selected solve speed and validated shaft torque.",
            "energy": "Selected total electrical power times duration; reserve withheld once. "
                      "Captured heat is not an additional electrical charge; auxiliary is included once.",
            "heat": "Captured motor loss plus declared auxiliary heat drives one chronological lumped "
                    "thermal evaluation after all residuals meet; no temperature feedback to points.",
            "residual_unmet": {
                "status": "COMPUTED_EXPERIMENTAL", "mission_state": "STOPPED_AT_UNMET_SEGMENT",
                "power_segments": "Reached prefix including the first unmet segment.",
                "energy": None, "thermal": None, "energy_units": None, "thermal_units": None,
                "transfers": [],
            },
            "all_met_mission_state": "COMPUTED_FROM_RESIDUAL_MET_SEGMENTS",
            "hashes": "Request/result provenance only; no physical proof or runtime identity.",
            "no_claims": ["aircraft feasibility", "physical validation", "numerical qualification",
                          "thermal adequacy", "continuous ratings", "production readiness"],
        },
    }


@router.post("/evaluate")
async def evaluate(request: Request):
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        if type(body) is not dict:
            raise ValueError("Expected object")
        mission._mission_json(body)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(422, "Invalid solved DC electrothermal request.") from None
    result = await run_in_threadpool(mission.evaluate_solved_dc_electrothermal, body)
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result


class SolvedDCElectrothermalBodyLimit:
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
