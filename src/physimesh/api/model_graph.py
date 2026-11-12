"""Strict, bounded HTTP access to the code-owned experimental graph executor."""

import json
import math

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from physimesh.drone.model_graph_execution import (
    EVALUATION,
    adapter_metadata,
    evaluate_model_graph,
)
from physimesh.drone.provenance import sha256_record
from physimesh.drone.reference_air_graph import (
    EVALUATION as AIR_EVALUATION,
)
from physimesh.drone.reference_air_graph import (
    adapter_metadata as air_adapter_metadata,
)
from physimesh.drone.reference_air_graph import (
    evaluate_reference_air_graph,
)

PREFIX = "/api/drone/model-graph"
MAX_BODY_BYTES = 128 * 1024
INVALID = "Invalid model graph request."
router = APIRouter(prefix=PREFIX)


class ModelGraphBodyLimit:
    """Apply the existing receive-counting style before the graph body is read."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] != "POST"
                or scope["path"].rstrip("/") != PREFIX + "/evaluate"):
            return await self.app(scope, receive, send)
        declared = dict(scope["headers"]).get(b"content-length")
        try:
            if declared and (int(declared) < 0 or int(declared) > MAX_BODY_BYTES):
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
                if total > MAX_BODY_BYTES:
                    raise HTTPException(413, "request byte budget exceeded")
            return message

        return await self.app(scope, bounded_receive, send)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Nonfinite JSON constant")


def _bounded_json(value):
    remaining = 4096

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 10:
            raise ValueError("JSON resource limit")
        kind = type(item)
        if kind is str:
            if len(item) > 2000:
                raise ValueError("String limit")
            item.encode("utf-8")
        elif kind is int:
            if item.bit_length() > 1023:
                raise ValueError("Integer limit")
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError("Nonfinite number")
        elif kind in (dict, list):
            if len(item) > 256:
                raise ValueError("Container limit")
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise ValueError("String keys required")
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
        elif item is not None and kind is not bool:
            raise ValueError("Builtin JSON required")

    visit(value, 1)


def _exact(value, keys):
    if type(value) is not dict or value.keys() != keys:
        raise ValueError("Exact object required")


def _schema(body):
    """Reject HTTP shape/type errors; graph semantics remain the core's decision."""
    _bounded_json(body)
    _exact(body, {"evaluation", "nodes", "connections", "targets"})
    if type(body["evaluation"]) is not str:
        raise ValueError("String evaluation required")
    metadata = air_adapter_metadata() if body["evaluation"] == AIR_EVALUATION else adapter_metadata()
    for key in ("nodes", "connections", "targets"):
        if type(body[key]) is not list:
            raise ValueError("List required")
    for node in body["nodes"]:
        _exact(node, {"id", "model", "inputs"})
        if (type(node["id"]) is not str or type(node["model"]) is not str
                or type(node["inputs"]) is not dict):
            raise ValueError("Node types")
        adapter = metadata.get(node["model"])
        if adapter is None:
            continue  # Unknown semantic adapters are refused by the core.
        allowed = adapter["inputs"].keys() | set(adapter["literal_fields"])
        if not node["inputs"].keys() <= allowed:
            raise ValueError("Unknown input field")
        for key, value in node["inputs"].items():
            if key in adapter["inputs"]:
                if key == "pitch_root_rad" and value is None:
                    continue
                kinds = (int,) if adapter["inputs"][key]["kind"] == "integer" else (int, float)
                if type(value) not in kinds:
                    raise ValueError("Numeric literal required")
            elif key == "coefficient_envelope":
                _exact(value, {"mach_min", "mach_max", "reynolds_min", "reynolds_max",
                               "lift_coefficient_min", "lift_coefficient_max"})
                if any(type(v) not in (int, float) for v in value.values()):
                    raise ValueError("Numeric bounds required")
            elif type(value) is not str or not value.strip():
                raise ValueError("Nonblank literal declaration required")
    for edge in body["connections"]:
        _exact(edge, {"from_node", "from_port", "to_node", "to_port"})
        if any(type(v) is not str for v in edge.values()):
            raise ValueError("Named connection required")
    for target in body["targets"]:
        _exact(target, {"node", "port"})
        if any(type(v) is not str for v in target.values()):
            raise ValueError("Named target required")


@router.get("/catalog")
def catalog() -> dict:
    return {
        "evaluation": EVALUATION,
        "schema_version": "bounded_model_graph_v1",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "adapters": adapter_metadata(),
        "evaluations": {
            EVALUATION: {
                "adapters": adapter_metadata(),
                "schema_version": "bounded_model_graph_v1",
                "limitations": [
                    "Experimental; both evaluations share the existing caps and authentication.",
                ],
            },
            AIR_EVALUATION: {
                "adapters": air_adapter_metadata(),
                "schema_version": "bounded_model_graph_v1",
                "limitations": [
                    "Experimental; both evaluations share the existing caps and authentication.",
                ],
            },
        },
        "limits": {"body_bytes": MAX_BODY_BYTES, "nodes": 16, "connections": 64,
                   "targets": 32, "annuli_per_hover": 2048, "aggregate_hover_annuli": 8192,
                   "blade_count": 32, "json_depth": 10, "json_values": 4096,
                   "container_items": 256, "string_characters": 2000, "integer_bits": 1023},
        "limitations": [
            "Experimental serial scalar SI DAG; only these code-owned adapters are available.",
            "All nodes are validated; only selected targets and their ancestors execute.",
            "Geometry and declarations are literal; vector, frame and unit conversions are unsupported.",
            "Component domain guards still apply; declarations and hashes are not validation evidence.",
            "Stateless computation; no full M3 model registry or aircraft qualification claim.",
        ],
    }


@router.post("/evaluate")
async def evaluate(request: Request) -> dict:
    raw = await request.body()  # ModelGraphBodyLimit bounds every receive before buffering.
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        _schema(body)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(422, INVALID) from None
    result = await run_in_threadpool(
        evaluate_reference_air_graph if body["evaluation"] == AIR_EVALUATION else evaluate_model_graph,
        body,
    )
    if "request_sha256" in result:
        result["input_sha256"] = result["request_sha256"]
        result["evaluation_sha256"] = sha256_record(result)
    return result
