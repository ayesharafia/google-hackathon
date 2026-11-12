import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from physimesh.drone.hover_thrust_target import (
    EVALUATION,
    evaluate_hover_thrust_target,
)
from physimesh.drone.model_graph_execution import _json
from physimesh.drone.provenance import sha256_record

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/hover-thrust-target"
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "evaluation": EVALUATION,
        "schema": "isolated_hover_thrust_target_v1",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "required_root": [
            "evaluation",
            "rotor_template",
            "target_thrust_n",
            "angular_speed_bracket_rad_s",
            "absolute_thrust_tolerance_n",
            "max_evaluations",
        ],
        "limits": {
            "body_bytes": 131072,
            "json_values": 8192,
            "json_depth": 10,
            "json_container_items": 256,
            "json_string_length": 2000,
            "json_integer_bits": 1023,
            "max_evaluations": {"type": "integer", "minimum": 2, "maximum": 64},
            "annuli": 512,
            "aggregate_annuli": 32768,
        },
        "angular_speed_unit": "rad/s",
        "completion_status": "COMPUTED_EXPERIMENTAL",
        "outcomes": [
            "TARGET_RESIDUAL_MET",
            "TARGET_NOT_BRACKETED",
            "EVALUATION_LIMIT",
            "FLOATING_POINT_STAGNATION",
        ],
        "inverse_evaluation": {
            "method": "Bisection using actual isolated-hover forward evaluations within the supplied angular-speed bracket.",
            "residual": "Computed forward thrust minus target_thrust_n, in newtons.",
            "acceptance": "TARGET_RESIDUAL_MET means the absolute computed thrust residual is within absolute_thrust_tolerance_n.",
            "scaling": False,
            "extrapolation": False,
            "monotonicity": "Observed monotonic samples do not prove global monotonicity or uniqueness of a solution.",
        },
        "data_hashes": "Hashes identify actual records; record identity does not establish validation or qualification.",
        "limitations": [
            "Experimental inverse evaluation of an isolated-hover rotor model.",
            "Angular speeds are expressed in rad/s, not RPM.",
            "The forward model uses a small-angle approximation under isolated-hover assumptions.",
            "No additional loss corrections or rotor interference are modeled.",
            "No Reynolds-number-dependent or Mach-number-dependent airfoil polars are modeled.",
            "Meeting the model residual tolerance does not establish physical accuracy, aircraft trim, or power feasibility.",
            "Shaft power does not establish electrical power; electrical power is not inferred.",
            "COMPUTED_EXPERIMENTAL indicates a completed computation, not feasibility.",
            "TARGET_NOT_BRACKETED concerns the supplied bracket and does not prove that no solution exists elsewhere.",
            "EVALUATION_LIMIT and FLOATING_POINT_STAGNATION do not establish that the requested residual tolerance was met.",
            "No API or deployment qualification.",
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
        _json(body, budget=8192)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(422, "Invalid hover thrust target request.") from None
    result = await run_in_threadpool(evaluate_hover_thrust_target, body)
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result


from starlette.responses import JSONResponse


class HoverThrustTargetBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/")
            != "/api/drone/hover-thrust-target/evaluate"
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
