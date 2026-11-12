import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from physimesh.drone.model_graph_execution import _json
from physimesh.drone.provenance import sha256_record
from physimesh.drone.rotor_assembly import (
    EVALUATION,
    evaluate_rotor_assembly,
)

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/rotor-assembly"
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "evaluation": EVALUATION,
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "limits": {
            "body_bytes": 131072,
            "json_values": 16384,
            "json_depth": 10,
            "rotors": 15,
            "nodes": 16,
            "targets": 32,
            "aggregate_hover_annuli": 8192,
        },
        "frame": "body_forward_left_up",
        "moment_convention": "(center-cg)crossF-signQaxis",
        "required_root": [
            "evaluation",
            "graph",
            "air_node",
            "rotors",
            "mass_kg",
            "cg_body_m",
            "gravity_direction_body",
            "property_source",
        ],
        "limitations": [
            "Isolated rotor superposition.",
            "No interference, trim, or safety assessment.",
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
        _json(body, budget=16384)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(422, "Invalid rotor assembly request.") from None
    result = await run_in_threadpool(evaluate_rotor_assembly, body)
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result


from starlette.responses import JSONResponse


class RotorAssemblyBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") != "/api/drone/rotor-assembly/evaluate"
        ):
            return await self.app(scope, receive, send)

        declared = dict(scope["headers"]).get(b"content-length")
        try:
            if declared and (int(declared) < 0 or int(declared) > 131072):
                return await JSONResponse({"detail": "request byte budget exceeded"}, status_code=413)(
                    scope, receive, send
                )
        except ValueError:
            return await JSONResponse({"detail": "invalid content length"}, status_code=400)(
                scope, receive, send
            )

        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > 131072:
                    raise HTTPException(status_code=413, detail="request byte budget exceeded")
            return message

        await self.app(scope, bounded_receive, send)
