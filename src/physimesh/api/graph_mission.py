import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from physimesh.drone.electrothermal_mission import (
    EVALUATION as ELECTROTHERMAL_EVALUATION,
)
from physimesh.drone.electrothermal_mission import (
    evaluate_electrothermal_mission,
)
from physimesh.drone.graph_mission import EVALUATION, evaluate_graph_mission
from physimesh.drone.model_graph_execution import _json
from physimesh.drone.multi_rotor_mission import (
    EVALUATION as MULTI_ROTOR_EVALUATION,
)
from physimesh.drone.multi_rotor_mission import (
    evaluate_multi_rotor_mission,
)
from physimesh.drone.provenance import sha256_record

from .model_graph import _constant, _pairs

PREFIX = '/api/drone/graph-mission'
MAX_BODY_BYTES = 128 * 1024
INVALID = 'Invalid graph mission request.'
router = APIRouter(prefix=PREFIX)


class GraphMissionBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or scope.get('method') != 'POST'
                or scope.get('path', '').rstrip('/') != PREFIX + '/evaluate'):
            await self.app(scope, receive, send)
            return

        content_length = dict(scope.get('headers', [])).get(b'content-length')
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                response = JSONResponse(
                    {'detail': 'Invalid Content-Length.'}, status_code=400)
                await response(scope, receive, send)
                return
            if declared < 0 or declared > MAX_BODY_BYTES:
                response = JSONResponse(
                    {'detail': 'Request byte budget exceeded.'}, status_code=413)
                await response(scope, receive, send)
                return

        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > MAX_BODY_BYTES:
                    raise HTTPException(413, 'Request byte budget exceeded.')
            return message

        await self.app(scope, bounded_receive, send)

@router.get("/catalog")
async def graph_mission_catalog():
    return {
        "evaluation": EVALUATION,
        "schema_version": "constant_condition_graph_mission_v1",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "evaluations": {
            EVALUATION: {
                "json_values": 32768,
                "schema_version": "constant_condition_graph_mission_v1",
                "required_fields": [
                    "evaluation", "usable_energy_j", "reserve_fraction", "segments",
                ],
                "limitations": [
                    "Constant-condition evaluation only.",
                    "Inputs and results are unverified.",
                    "No feasibility determination.",
                ],
            },
            ELECTROTHERMAL_EVALUATION: {
                "json_values": 49152,
                "schema_version": "constant_condition_electrothermal_mission_v1",
                "required_fields": [
                    "evaluation", "energy_mission", "thermal_body", "thermal_segments",
                ],
                "limitations": [
                    "Constant-condition evaluation only.",
                    "Inputs and results are unverified.",
                    "No feasibility determination.",
                ],
            },
            MULTI_ROTOR_EVALUATION: {
                "json_values": 32768,
                "schema_version": "constant_condition_multi_rotor_mission_v1",
                "required_fields": [
                    "evaluation", "usable_energy_j", "reserve_fraction", "segments",
                ],
                "limitations": [
                    "Constant-condition evaluation only.",
                    "Isolated-rotor energy sums only.",
                    "Common auxiliary power is counted once.",
                    "Reserve is held once.",
                    "No aircraft verdict.",
                ],
            },
        },
        "limits": {
            "body_bytes": 128 * 1024, "segments": 32, "total_nodes": 128,
            "total_hover_annuli": 8192, "json_values": 32768, "json_depth": 10,
        },
        "energy_convention": "usable joules before a reserve fraction held once",
        "segment_fields": [
            "id", "duration_s", "graph", "power_node", "power_port",
            "conversion_efficiency", "auxiliary_power_w", "conversion_source",
        ],
        "power_bindings": {
            "isolated_hover_bemt_experimental": "shaft_power_w",
            "fixed_wing_aerodynamic_screening": "drag_power_w",
        },
        "limitations": [
            "Caller conversion efficiency, auxiliary power, and energy are unverified.",
            "No dynamic mass, thermal, or force closure.",
            "No feasibility determination.",
        ],
    }

@router.post("/evaluate")
async def graph_mission_evaluate(request: Request):
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        _json(body, budget=(
            49152 if type(body) is dict
            and body.get("evaluation") == ELECTROTHERMAL_EVALUATION
            else 32768
        ))
        if type(body) is not dict:
            raise ValueError
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(status_code=422, detail=INVALID) from None
    result = await run_in_threadpool(
        evaluate_multi_rotor_mission
        if body.get("evaluation") == MULTI_ROTOR_EVALUATION
        else evaluate_electrothermal_mission
        if body.get("evaluation") == ELECTROTHERMAL_EVALUATION
        else evaluate_graph_mission,
        body,
    )
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result
