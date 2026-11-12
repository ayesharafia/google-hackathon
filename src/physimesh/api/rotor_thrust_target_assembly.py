import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from physimesh.drone.model_graph_execution import _json
from physimesh.drone.provenance import sha256_record
from physimesh.drone.rotor_thrust_target_assembly import (
    EVALUATION,
    evaluate_rotor_thrust_target_assembly,
)

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/rotor-thrust-target-assembly"
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "evaluation": EVALUATION,
        "schema": "prescribed_rotor_thrust_target_assembly_v1",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "required_root": ["evaluation", "assembly_template", "targets"],
        "target_fields": [
            "node",
            "target_thrust_n",
            "angular_speed_bracket_rad_s",
            "absolute_thrust_tolerance_n",
            "max_evaluations",
        ],
        "limits": {
            "body_bytes": 131072,
            "json_values": 32768,
            "json_depth": 10,
            "json_container_items": 256,
            "json_string_length": 2000,
            "json_integer_bits": 1023,
            "rotors": 15,
            "per_rotor_annuli": 512,
            "max_evaluations": {"type": "integer", "minimum": 2, "maximum": 64},
            "inverse_aggregate_annuli": 32768,
            "final_aggregate_annuli": 8192,
        },
        "angular_speed_unit": "rad/s",
        "completion_status": "COMPUTED_EXPERIMENTAL",
        "limitations": [
            "Thrust targets are caller-prescribed; no thrust allocation or aircraft trim is performed.",
            "Omit hover angular speed from assembly_template; targets must follow assembly rotor order.",
            "A common air density is bound into the inverse evaluations; the final assembly recomputes air properties.",
            "Every inverse evaluation must return TARGET_RESIDUAL_MET; otherwise the operation fails atomically with EXECUTION_FAILED.",
            "Best-candidate thrust and torque checks establish consistency only, not physical validation.",
            "Inner candidate result_sha256 checks validate syntax only; whole raw stage hashes identify actual records, not validation or qualification.",
            "Uses existing isolated-hover physics; adds no new physics or rotor-interference model.",
            "COMPUTED_EXPERIMENTAL indicates completed computation and does not establish installed-flight validity, power or thermal feasibility, mass closure, or qualification.",
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
        _json(body, budget=32768)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(422, "Invalid rotor thrust target assembly request.") from None
    result = await run_in_threadpool(evaluate_rotor_thrust_target_assembly, body)
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result


class RotorThrustTargetAssemblyBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/")
            != "/api/drone/rotor-thrust-target-assembly/evaluate"
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
