import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from physimesh.drone.ledger_solved_sensitivity import (
    EVALUATION,
    evaluate_ledger_solved_sensitivity,
)
from physimesh.drone.model_graph_execution import _json
from physimesh.drone.provenance import sha256_record

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/ledger-solved-sensitivity"
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "catalog": "actual_ledger_solved_sensitivity_bridge",
        "schema_version": "ledger_solved_wrench_sensitivity_v1",
        "evaluation": EVALUATION,
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "required_root": ["evaluation", "ledger", "analysis_template"],
        "root_fields_exact": True,
        "field_shape": {
            "ledger": "An actual ledger request.",
            "analysis_template": {
                "shape": "An accepted solved-wrench-sensitivity request.",
                "required_root": [
                    "evaluation", "solve", "sensitivity_settings"
                ],
                "solve.assembly_template": (
                    "Must omit mass and CG; the actual ledger supplies "
                    "the frozen mass and CG."
                ),
                "sensitivity_settings_fields": [
                    "perturbations",
                    "force_scale_n",
                    "moment_scale_nm",
                    "relative_singular_value_cutoff",
                ],
            },
        },
        "limits": {
            "body_bytes": 131072,
            "json_values": 65536,
            "nested_analysis_json_values": 49152,
            "nested_solver_json_values": 32768,
            "nested_sensitivity_json_values": 32768,
            "json_depth": 10,
            "json_container_items": 256,
            "json_string_length": 2000,
            "json_integer_bits": 1023,
            "rotors": 15,
            "per_rotor_annuli": 512,
            "max_solver_evaluations": {
                "type": "integer",
                "minimum": 2,
                "maximum": 64,
            },
            "planned_assembly_calls": 155,
            "combined_annuli": 32768,
        },
        "sensitivity_states": [
            "COMPUTED_AT_RESIDUAL_MET_POINT",
            "NOT_RUN_RESIDUAL_UNMET",
        ],
        "completion_status": "COMPUTED_EXPERIMENTAL",
        "limitations": {
            "execution": {
                "sequence": ["actual_ledger", "actual_analysis"],
                "actual_ledger_calls": 1,
                "actual_analysis_calls": 1,
                "mass_cg": "Frozen from the actual ledger before analysis.",
                "inertia_report_used": False,
                "solver_outcomes": (
                    "All three actual solver outcomes are supported."
                ),
                "sensitivity_condition": (
                    "Sensitivity runs only for RESIDUAL_MET."
                ),
                "residual_unmet": {
                    "completion_status": "COMPUTED_EXPERIMENTAL",
                    "sensitivity_state": "NOT_RUN_RESIDUAL_UNMET",
                    "sensitivity_probes_run": False,
                    "sensitivity_probe_count": 0,
                    "sensitivity": None,
                },
            },
            "nominal_consistency": (
                "At the selected speeds, the actual fresh nominal assembly "
                "must equal the solve final assembly."
            ),
            "combined_annuli_work": {
                "constraint": (
                    "sum_annuli * (max_evaluations + 1 + 6 * N) <= 32768"
                ),
                "includes": [
                    "all finite-difference assemblies",
                    "reserved final assembly",
                    "sensitivity probes",
                ],
            },
            "perturbations": [
                "h must be positive.",
                "lo - h must be strictly positive.",
                "Perturbation endpoints must be representable.",
                "These conditions are checked again at the selected speeds.",
            ],
            "svd_interpretation": {
                "dimensionless": True,
                "scales": "caller-supplied",
                "cutoff": "caller-supplied relative singular-value cutoff",
                "does_not_establish": [
                    "control authority",
                    "trim",
                    "stability",
                    "global feasibility",
                    "an error certificate",
                ],
            },
            "hash_evidence": {
                "outer_hashes": "Whole actual raw payload hashes.",
                "inner_result_hashes": "Syntax validation only.",
                "nested_raw_records_present": False,
                "plus_minus_raw_payloads_present": False,
                "independent_central_difference_proven": False,
            },
            "no_claims": [
                "new physics",
                "physical qualification",
                "numerical qualification",
                "deployment readiness",
            ],
        },
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
        raise HTTPException(422, "Invalid ledger solved sensitivity request.") from None
    result = await run_in_threadpool(evaluate_ledger_solved_sensitivity, body)
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result


class LedgerSolvedSensitivityBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/")
            != "/api/drone/ledger-solved-sensitivity/evaluate"
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
