"""Bounded HTTP transport for retained V142/V143 disk-pressure operations."""

import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from physimesh.drone import polar_rotor as _rotor
from physimesh.drone import polar_rotor_disk_pressure as _pressure
from physimesh.drone import polar_rotor_disk_pressure_export as _exporter

from .model_graph import _constant, _pairs

PREFIX = "/api/drone/disk-pressure"
MAX_BODY_BYTES = 16777216
router = APIRouter(prefix=PREFIX)


@router.get("/catalog")
async def catalog():
    return {
        "catalog": {
            "schema_version": "disk_pressure_transport_v1",
            "operations": {
                "derive": {"path": PREFIX + "/derive", "method": "POST",
                           "evaluation": "polar_rotor_disk_pressure",
                           "schema_version": "polar_rotor_disk_pressure_v1",
                           "input": "Sealed evaluate_polar_rotor response; all sections converged.",
                           "output": "Sealed V142 derived annulus pressure jumps and both mean loadings."},
                "export": {"path": PREFIX + "/export", "method": "POST",
                           "evaluation": "polar_rotor_disk_pressure_export",
                           "schema_version": "polar_rotor_disk_pressure_export_v1",
                           "input": "Sealed V142 derivation response with all required labels retained.",
                           "output": "Sealed V143 canonical report, SHA256 digest and UTF-8 byte length."},
            },
            "state_text": _pressure._STATE_TEXT,
            "limitations": [_pressure._STATE_TEXT,
                            "Canonical digests bind JSON content, not provenance authenticity."],
            "physical_validation": "NOT_ESTABLISHED", "numerical_qualification": "NOT_ESTABLISHED",
            "runtime_identity": "NOT_ESTABLISHED", "aircraft_status": None, "feasibility": None,
        },
        "transport": {
            "limits": {
                "body_bytes": MAX_BODY_BYTES,
                "body_bytes_constraint": "Independent limit on actual received request bytes, including "
                                         "UTF-8 encoding and whitespace; not a JSON node or response limit.",
                "input_json_reference": "polar_rotor._walk(body, output=True) output-JSON limits "
                                        "for sealed producer response bodies",
                "response_json_reference": "V142/V143 output JSON walker limits",
                "model_shape_reference": "V142/V143 sealed-envelope preflights",
                "independent_bounds": "This transport has its own larger 16 MiB cap: a sealed polar-rotor "
                                      "response may exceed the V137 1 MiB evaluate budget; V136 responses "
                                      "have their own budget. Larger inputs are refused with HTTP 413; "
                                      "callers derive from smaller annulus counts. Sealed producer response "
                                      "bodies use polar_rotor output-JSON walker limits, not the evaluate "
                                      "input-JSON limits. JSON shape limits "
                                      "apply independently and do not promise HTTP acceptance.",
            },
            "parsing": "Strict UTF-8 JSON object; duplicate keys and nonfinite constants rejected; "
                       "request bodies are sealed producer responses validated with "
                       "polar_rotor._walk(body, output=True) under output-JSON walker limits, "
                       "not the evaluate input-JSON limits, before workflow dispatch.",
            "execution": "One derive_disk_pressure or export_disk_pressure_report call in the threadpool; "
                         "sealed outputs, units, counts, statuses, reasons, labels and hashes unchanged. "
                         "No physical model is run.",
            "http_status": "Parser failures are generic 422; byte-budget refusals are 413; every structured "
                           "workflow result is HTTP 200. HTTP 200 alone establishes neither computational "
                           "nor physical success; inspect the workflow status, reasons and limitations.",
            "ordering": "Existing authentication precedes body consumption and parsing. The byte limit "
                        "also matches trailing slashes; existing authentication and router redirect "
                        "ordering remains unchanged. Hosted authorization allows only canonical paths.",
        },
    }


@router.post("/derive")
async def derive(request: Request):
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        if type(body) is not dict:
            raise ValueError("Expected object")
        _rotor._walk(body, output=True)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(422, "Invalid disk pressure request.") from None
    return await run_in_threadpool(_pressure.derive_disk_pressure, body)


@router.post("/export")
async def export(request: Request):
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        if type(body) is not dict:
            raise ValueError("Expected object")
        _rotor._walk(body, output=True)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise HTTPException(422, "Invalid disk pressure request.") from None
    return await run_in_threadpool(_exporter.export_disk_pressure_report, body)


class DiskPressureBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] != "POST"
                or scope["path"].rstrip("/") not in (PREFIX + "/derive", PREFIX + "/export")):
            return await self.app(scope, receive, send)
        declared = dict(scope["headers"]).get(b"content-length")
        try:
            if declared is not None:
                if not declared.isdigit():
                    raise ValueError("Invalid content length")
                if int(declared) > MAX_BODY_BYTES:
                    raise ValueError("Request byte budget exceeded")
        except ValueError:
            return await JSONResponse(
                {"detail": "request byte budget exceeded"}, status_code=413
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
