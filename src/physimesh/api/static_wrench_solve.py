import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from physimesh.drone.model_graph_execution import _json
from physimesh.drone.provenance import sha256_record
from physimesh.drone.static_wrench_solve import (
    EVALUATION,
    evaluate_static_wrench_solve,
)

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/static-wrench-solve"
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "evaluation": EVALUATION,
        "schema": "bounded_static_wrench_solve_v1",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "required_root": [
            "evaluation",
            "assembly_template",
            "rotor_speed_bounds",
            "required_net_force_body_n",
            "required_net_moment_cg_body_nm",
            "absolute_force_tolerance_n",
            "absolute_moment_tolerance_nm",
            "max_evaluations",
        ],
        "speed_bound_fields": [
            "node",
            "angular_speed_bracket_rad_s",
            "initial_angular_speed_rad_s",
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
            "aggregate_annuli": 32768,
        },
        "angular_speed_unit": "rad/s",
        "force_unit": "N",
        "moment_unit": "N*m",
        "solver_outcomes": [
            "RESIDUAL_MET",
            "EVALUATION_LIMIT",
            "SOLVER_STOPPED",
        ],
        "completion_status": "COMPUTED_EXPERIMENTAL",
        "limitations": [
            "Uses SciPy least_squares with method='trf' for a bounded local solve of rotor angular speeds; every probe performs an actual common-air rotor assembly evaluation.",
            "The six residuals are the three net body-force errors and three net moments-about-CG errors, normalized by caller-supplied positive absolute force and moment tolerances.",
            "Geometry, air, mass, and CG remain fixed throughout the solve.",
            "Omit hover angular speed from assembly_template; rotor_speed_bounds must follow assembly rotor order.",
            "max_evaluations counts all actual assembly calls, including finite-difference probes and a reserved fresh final evaluation; max_evaluations times the sum of rotor annuli must not exceed aggregate_annuli.",
            "The locally best candidate is selected by the smallest maximum absolute scaled residual; selected-candidate and fresh-final equality checks establish computational consistency only.",
            "RESIDUAL_MET requires all six absolute scaled residuals from the fresh final evaluation to be at most 1; COMPUTED_EXPERIMENTAL alone does not imply that residual tolerances were met.",
            "A local result establishes neither uniqueness nor a global solution; failure to meet residual tolerances does not establish global infeasibility.",
            "Inner graph result_sha256 checks validate syntax only; full actual raw stage hashes identify records and are not physical proof or qualification.",
            "Uses existing isolated-hover physics; adds no new physics or rotor-interference model.",
            "COMPUTED_EXPERIMENTAL indicates completed computation and does not establish physical trim, control authority, installed-flight validity, power or thermal feasibility, mass closure, or qualification.",
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
        raise HTTPException(422, "Invalid static wrench solve request.") from None
    result = await run_in_threadpool(evaluate_static_wrench_solve, body)
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result


class StaticWrenchSolveBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/")
            != "/api/drone/static-wrench-solve/evaluate"
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
