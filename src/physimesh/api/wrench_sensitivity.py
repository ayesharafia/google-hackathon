import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from physimesh.drone.model_graph_execution import _json
from physimesh.drone.provenance import sha256_record
from physimesh.drone.wrench_sensitivity import (
    EVALUATION,
    evaluate_wrench_sensitivity,
)

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/wrench-sensitivity"
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "evaluation": EVALUATION,
        "schema": "static_wrench_sensitivity_v1",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "required_root": [
            "evaluation",
            "assembly",
            "perturbations",
            "force_scale_n",
            "moment_scale_nm",
            "relative_singular_value_cutoff",
        ],
        "perturbation_fields": [
            "node",
            "half_step_rad_s",
            "speed_scale_rad_s",
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
            "planned_assembly_calls": 91,
            "aggregate_annuli": 32768,
        },
        "angular_speed_unit": "rad/s",
        "force_unit": "N",
        "moment_unit": "N*m",
        "force_jacobian_unit": "N/(rad/s)",
        "moment_jacobian_unit": "N*m/(rad/s)",
        "normalized_jacobian_unit": "dimensionless",
        "completion_status": "COMPUTED_EXPERIMENTAL",
        "limitations": [
            "Uses a fixed probe schedule: one fresh nominal assembly evaluation and six fresh assembly evaluations per rotor, for 1 + 6*N actual calls with N rotors.",
            "For each rotor, central differences evaluate nominal angular speed plus and minus h, h/2, and h/4, where h is half_step_rad_s; each call evaluates the complete common-air rotor assembly.",
            "assembly must be complete and include nominal rotor angular speeds; perturbations must contain one entry per rotor in assembly rotor order, with matching node identifiers.",
            "Nominal angular speeds, half_step_rad_s, and speed_scale_rad_s must be positive; all six perturbed speeds must be positive, representable, and distinct from one another and the nominal speed. Zero-speed and failed-rotor cases are unsupported.",
            "Geometry, air, mass, CG, and all other rotor speeds remain fixed during each rotor's probes.",
            "Planned work is (1 + 6*N) times the sum of rotor annuli and must not exceed aggregate_annuli; the schedule permits at most 91 actual assembly calls.",
            "Force Jacobian entries are derivatives of net body force with respect to rotor angular speed in N/(rad/s); moment Jacobian entries are derivatives of net moment about CG in N*m/(rad/s).",
            "The dimensionless Jacobian multiplies each rotor column by its caller-supplied positive speed_scale_rad_s and divides force rows by positive force_scale_n and moment rows by positive moment_scale_nm.",
            "Rank counts singular values strictly greater than relative_singular_value_cutoff times the largest singular value of the dimensionless Jacobian; an all-zero Jacobian has rank zero. Rank depends on caller-supplied scales and cutoff.",
            "Three finite-difference resolution levels provide two adjacent-resolution changes; these changes are not error estimates or proof of convergence.",
            "Local sensitivity and numerical rank do not establish control authority, trim, stability, global feasibility, or physical qualification.",
            "Hashes identify the actual whole input and actual raw stage records; inner graph result_sha256 checks validate SHA-256 syntax only. These hashes do not establish physical validity or qualification.",
            "Uses existing isolated-hover physics; adds no new physics or rotor-interference model.",
            "COMPUTED_EXPERIMENTAL indicates completed fixed-probe computation and does not establish physical validation, numerical qualification, runtime identity, installed-flight validity, power or thermal feasibility, mass closure, aircraft feasibility, or API deployment qualification.",
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
        raise HTTPException(422, "Invalid wrench sensitivity request.") from None
    result = await run_in_threadpool(evaluate_wrench_sensitivity, body)
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result


class WrenchSensitivityBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/")
            != "/api/drone/wrench-sensitivity/evaluate"
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
