"""Bounded HTTP transport for the actual V112 static tabulated-rotor assembly."""

import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from physimesh.drone import tabulated_rotor_assembly as workflow

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/tabulated-rotor-assembly"
MAX_BODY_BYTES = 131072
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "catalog": workflow.tabulated_rotor_assembly_catalog(),
        "transport": {
            "limits": {
                "body_bytes": MAX_BODY_BYTES,
                "body_bytes_constraint": "Independent limit on actual received request bytes, including "
                                         "UTF-8 encoding and whitespace; not a JSON node or response limit.",
                "input_json_reference": "catalog.limits.input_json",
                "response_json_reference": "catalog.limits.output_json",
                "model_shape_reference": "catalog.limits.core_work",
                "independent_bounds": "Model shape maxima do not promise HTTP acceptance in all combinations. "
                                      "Response JSON has its own workflow budget, not the request byte budget.",
            },
            "parsing": "Strict UTF-8 JSON object; duplicate keys and nonfinite constants rejected; "
                       "actual workflow input JSON walker runs before evaluation.",
            "execution": "One actual evaluate_tabulated_rotor_assembly call in the threadpool; "
                         "actual air once and actual forward adapter/core once per rotor. "
                         "Full V112 response, units, validated-envelope count and nullable hashes unchanged.",
            "http_status": "Parser failures are generic 422; structured workflow results are HTTP 200. "
                           "200 alone establishes neither computational nor physical success; "
                           "see catalog.response_contract for statuses and nullable hash semantics.",
            "nested_response": "Full guarded raw air and full guarded forward result once per rotor row. "
                               "Forward result units cover only nested outputs. Stages contain inputs and "
                               "digests without duplicate results. Counts record validated envelopes, "
                               "including valid refusal, not attempts or execution attestation. "
                               "Failures are atomic under the unchanged V112 contract.",
            "ordering": "Existing authentication precedes body consumption and parsing. The byte limit "
                        "also matches trailing slashes; existing authentication and router redirect "
                        "ordering remains unchanged. Hosted authorization allows only canonical paths.",
        },
    }


@router.post("/evaluate")
async def evaluate(request: Request):
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        if type(body) is not dict:
            raise ValueError("Expected object")
        workflow._json(body, workflow._LIMITS["input_json"])
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(422, "Invalid tabulated rotor assembly request.") from None
    return await run_in_threadpool(workflow.evaluate_tabulated_rotor_assembly, body)


class TabulatedRotorAssemblyBodyLimit:
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
