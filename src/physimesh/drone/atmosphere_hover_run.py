"""Run the accepted fixed experimental workflow; hashes identify data only.

CLI: one UTF-8 JSON document (at most 65536 bytes), one canonical JSON line.
Integer tokens are limited to 1024 digits and finite binary-float magnitude.
Exit codes: computed 0, workflow refusal/failure 1, strict input error 2.
Logical schema refusals are MODEL_INAPPLICABLE, hence exit 1.
No physical validation, freshness, portability, replay, or M3 claim is made.
"""

import json
import math
import platform
import sys
from copy import deepcopy

import numpy
import scipy

from . import atmosphere_hover_workflow as workflow
from .provenance import canonical_json, sha256_record

_STATUSES = {
    "COMPUTED_EXPERIMENTAL", "MODEL_INAPPLICABLE", "SOLVER_UNSUPPORTED",
    "NUMERICAL_FAILED",
}


def _valid_result(result):
    """Check the fixed component envelope without duplicating solver schemas."""
    if not workflow._finite_json(result, max_nodes=100000, max_depth=16,
                                 max_items=2048) or type(result) is not dict:
        return False
    base = workflow._response("MODEL_INAPPLICABLE", None)
    if not base.keys() <= result.keys() <= base.keys() | {"inputs_sha256", "stage_failure"}:
        return False
    for key in ("schema_version", "evaluation", "physical_validation",
                "numerical_qualification", "evidence_level", "aircraft_status",
                "feasibility", "bindings", "limits", "limitations"):
        if result[key] != base[key]:
            return False
    if type(result["status"]) is not str or result["status"] not in _STATUSES:
        return False
    for key in ("reasons", "transfers", "stages"):
        if type(result[key]) is not list:
            return False
    if any(type(reason) is not str for reason in result["reasons"]):
        return False
    if any(type(result[key]) is not dict for key in ("outputs", "output_units")):
        return False
    if result["failed_stage"] not in (None, "atmosphere", "hover"):
        return False
    if "stage_failure" in result and type(result["stage_failure"]) is not dict:
        return False
    if "inputs_sha256" in result:
        digest = result["inputs_sha256"]
        if type(digest) is not str or len(digest) != 64:
            return False
        if any(char not in "0123456789abcdef" for char in digest):
            return False
    expected_stages = ("atmosphere", "hover")
    if len(result["stages"]) > len(expected_stages):
        return False
    for stage_id, stage in zip(expected_stages, result["stages"]):
        if (type(stage) is not dict or stage.keys() != {
                "stage_id", "model_id", "inputs", "inputs_sha256", "result", "result_sha256"}
                or stage["stage_id"] != stage_id
                or stage["model_id"] != base["bindings"][stage_id]
                or stage["inputs_sha256"] != sha256_record(stage["inputs"])
                or stage["result_sha256"] != sha256_record(stage["result"])):
            return False
    if result["status"] == "COMPUTED_EXPERIMENTAL":
        return ("inputs_sha256" in result and not result["reasons"]
                and result["failed_stage"] is None and len(result["stages"]) == 2
                and result["outputs"].keys() == {"atmosphere", "hover"}
                and result["output_units"].keys() == {"atmosphere", "hover"})
    return bool(result["reasons"]) and not result["outputs"] and not result["output_units"]


def _record(result):
    snapshot = deepcopy(result)
    return {
        "schema_version": "atmosphere_hover_run_v1",
        "kind": "fixed_experimental_workflow",
        "status": snapshot["status"],
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "bindings": deepcopy(snapshot["bindings"]),
        "environment": {
            "python_version": platform.python_version(),
            "numpy_version": numpy.__version__,
            "scipy_version": scipy.__version__,
            "runtime_code_identity": "NOT_ESTABLISHED",
            "portability": "NOT_ESTABLISHED",
            "replay": "NOT_ESTABLISHED",
        },
        "hash_semantics": "Canonical data identity; not validation or freshness.",
        "result": snapshot,
        "result_sha256": sha256_record(snapshot),
    }


def run_record(request):
    """Call only the accepted workflow; never serialize arbitrary Python input."""
    snapshot = deepcopy(request) if workflow._finite_json(request) else None
    digest = sha256_record(snapshot) if snapshot is not None else None
    result = workflow.evaluate_atmosphere_hover(
        deepcopy(snapshot) if snapshot is not None else request
    )
    if (not _valid_result(result)
            or ("inputs_sha256" in result and result["inputs_sha256"] != digest)):
        result = workflow._response("NUMERICAL_FAILED", "Invalid fixed workflow result.")
    record = _record(result)
    if "inputs_sha256" in result:
        record["request"] = snapshot
        record["request_sha256"] = digest
    return record


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate key")
        value[key] = item
    return value


def _float(token):
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("Nonfinite number")
    return value


def _integer(token):
    if len(token.lstrip("-")) > 1024:
        raise ValueError("Integer token too long")
    value = int(token)
    if not math.isfinite(value):
        raise ValueError("Nonfinite integer magnitude")
    return value


def _constant(token):
    raise ValueError("Nonstandard JSON constant")


def main(stdin=None, stdout=None):
    """Use binary stdin by default; emit only a canonical JSON line to stdout."""
    source = sys.stdin.buffer if stdin is None else stdin
    target = sys.stdout if stdout is None else stdout
    try:
        raw = source.read(65537)
        if type(raw) is not bytes or len(raw) > 65536:
            raise ValueError("Expected bounded binary input")
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                             parse_constant=_constant, parse_float=_float,
                             parse_int=_integer)
    except (ValueError, OverflowError, RecursionError, UnicodeError):
        result = workflow._response("INPUT_ERROR", "Invalid strict JSON input.")
        record = _record(result)
        code = 2
    else:
        record = run_record(payload)
        code = 0 if record["status"] == "COMPUTED_EXPERIMENTAL" else 1
    target.write(canonical_json(record) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
