import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from physimesh.drone.ledger_dynamics_refinement import (
    EVALUATION,
    evaluate_ledger_dynamics_refinement,
)
from physimesh.drone.model_graph_execution import _json
from physimesh.drone.provenance import sha256_record

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/ledger-dynamics-refinement"
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "evaluation": EVALUATION,
        "schema": "ledger_dynamics_timestep_refinement_v1",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "ledger_properties_source": "single declared frozen ledger",
        "forbidden_duplicates": [
            "dynamics.assembly_template.mass_kg",
            "dynamics.assembly_template.cg_body_m",
            "dynamics.inertia_body_kg_m2",
        ],
        "provenance_boundaries": {
            "reconstructed_guard_metadata": "inherited, not independently recovered",
            "nested_result_sha256": "syntax only, not independently rebound",
            "nested_request_sha256": "rebound to canonical requests",
            "top_stage_sha256": "refinement stages bind complete actual raw ledger-rotor bridge result records; inner bridge stages bind ledger and frozen-dynamics records",
        },
        "limits": {
            "body_bytes": 131072,
            "json_values": 65536,
            "ledger_rotor_dynamics_json_values": 49152,
            "json_depth": 10,
            "json_container_items": 256,
            "json_string_length": 2000,
            "json_integer_bits": 1023,
            "ledger_json_values": 16384,
            "frozen_dynamics_json_values": 32768,
            "assembly_json_values": 16384,
            "rotors": 15,
            "nodes": 16,
            "targets": 32,
            "aggregate_hover_annuli": 8192,
            "dt_s": {"exclusive_minimum": 0},
            "steps": {"type": "integer", "minimum": 1, "maximum": 250},
            "max_actual_refined_steps": 1000,
            "actual_resolutions": 3,
        },
        "frame": "body_forward_left_up",
        "world_frame": "east_north_up",
        "initial_body_alignment": "FLU initially aligned with ENU",
        "initial_quaternion": [1, 0, 0, 0],
        "assembly_gravity_direction_body": [0, 0, -1],
        "moment_convention": "(center-cg)crossF-signQaxis",
        "refinement": {
            "resolutions": 3,
            "step_factors": [1, 2, 4],
            "timestep_factors": [1, 0.5, 0.25],
            "horizon": "identical floating-point horizon required",
            "differences": "Euclidean vector norms and sign-invariant quaternion chord, not rotation angle",
            "observed_order": "log2(d01)-log2(d12) when both positive, otherwise null",
            "qualification": "differences and observed order are not accuracy, tolerance or physical qualification",
        },
        "integration": {
            "method": "RK4",
            "stage_state": "raw",
            "normalized_stage_callback": False,
            "body_wrench": "constant",
            "rotor_body_force": "gravity excluded",
            "rotor_body_moment": "about the center of gravity",
            "gravity": "separate ENU contribution applied once",
            "mass": "constant",
            "inertia_body_kg_m2": "constant",
            "air": "not updated",
            "rpm": "not updated",
        },
        "required_root": [
            "evaluation",
            "dynamics",
        ],
        "limitations": [
            "Experimental isolated ledger dynamics timestep refinement.",
            "Rotor body force and center-of-gravity moment remain frozen.",
            "Mass and body inertia remain constant; air and RPM are not updated.",
            "RK4 uses raw stage states with a constant body wrench.",
            "No normalized-stage callback.",
            "No trajectory history.",
            "No inflow evolution or rotor interference.",
            "No trim, control, or stability assessment.",
            "No energy, thermal, or mass-closure assessment.",
            "No flight qualification, safety assessment, or deployment qualification.",
            "Provenance boundaries are data-integrity limits, not physical validation.",
            "No end-to-end verified nested provenance.",
            "No API qualification.",
            "Three fresh full ledger/assembly/dynamics evaluations are performed; no cached physics.",
        ],
    }


@router.post("/evaluate")
async def evaluate(request: Request):
    raw = await request.body()
    try:
        body = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
        if type(body) is not dict:
            raise ValueError("Expected object")
        _json(body, budget=65536)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(422, "Invalid ledger dynamics refinement request.") from None
    result = await run_in_threadpool(evaluate_ledger_dynamics_refinement, body)
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result


from starlette.responses import JSONResponse


class LedgerDynamicsRefinementBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/")
            != "/api/drone/ledger-dynamics-refinement/evaluate"
        ):
            return await self.app(scope, receive, send)

        declared = dict(scope["headers"]).get(b"content-length")
        try:
            if declared and (int(declared) < 0 or int(declared) > 131072):
                return await JSONResponse(
                    {"detail": "request byte budget exceeded"}, status_code=413
                )(scope, receive, send)
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
                if total > 131072:
                    raise HTTPException(
                        status_code=413, detail="request byte budget exceeded"
                    )
            return message

        await self.app(scope, bounded_receive, send)
