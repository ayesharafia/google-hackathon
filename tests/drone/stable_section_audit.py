"""Bounded standalone actual32/max-shape audit; run with --output PATH.

Measures this fixture, not a proof of all admitted allocations or API readiness.
"""

import argparse
import json
import resource
import time
from copy import deepcopy
from pathlib import Path

from test_stable_section_residual import reference_summary, residual_request

from physimesh.drone import section_load as load
from physimesh.drone import stable_section_residual as residual
from physimesh.drone import stable_section_solve as solve


def metrics(value):
    """Independent node/depth/compact UTF8 accounting, no full serialized copy."""
    nodes, depth = 0, 0

    def visit(item, level):
        nonlocal nodes, depth
        nodes += 1
        depth = max(depth, level)
        if type(item) is dict:
            for key, child in item.items():
                visit(key, level + 1)
                visit(child, level + 1)
        elif type(item) is list:
            for child in item:
                visit(child, level + 1)

    visit(value, 1)
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    size = sum(len(chunk.encode("utf-8")) for chunk in encoder.iterencode(value))
    return {"nodes_including_keys": nodes, "depth": depth, "serialized_bytes": size}


def maximum_shape_request():
    template = residual_request()
    del template["section"]["psi_rad"]
    table_limits = load._polar.section_polar_catalog()["limits"]["tables"]
    row_count, table_count = table_limits["rows_max"], table_limits["max"]
    rows = [{"alpha_rad": -1.5 + 3 * i / (row_count - 1), "cl": 4, "cd": 0.1}
            for i in range(row_count)]
    polar = template["polar"]
    polar.update(airfoil_id="x" + "\x00" * 127, source="x" + "\x00" * 1999,
                 uncertainty_status="x" + "\x00" * 1999)
    polar["reynolds_tables"] = [{"reynolds_number": 1000.0 * 10**i, "rows": deepcopy(rows)}
                                for i in range(table_count)]
    return {"evaluation": solve.EVALUATION, "numerical_policy": deepcopy(solve._POLICY),
            "residual_template": template,
            "solve": {"psi_lower_rad": 0.35, "psi_upper_rad": 0.9,
                      "angle_tolerance_rad": 1e-30, "residual_tolerance_m2_s": 1e-30,
                      "max_evaluations": 32}}


def run_audit(*, baseline=False):
    request = maximum_shape_request()
    if baseline:
        request["residual_template"]["polar"] = residual_request()["polar"]
    original, calls = residual.evaluate_stable_section_residual, 0

    def counted(actual_request):
        nonlocal calls
        calls += 1
        return original(actual_request)

    residual.evaluate_stable_section_residual = counted
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    start = time.perf_counter()
    try:
        result = solve.evaluate_stable_section_solve(request)
    finally:
        residual.evaluate_stable_section_residual = original
    elapsed = time.perf_counter() - start
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert result["outputs"]["solve_state"] == "EVALUATION_BUDGET_EXHAUSTED"
    rows = result["outputs"]["evaluations"]
    assert result["residual_result_count"] == len(rows) == calls == 32
    # Every retained actual child passed the production independent full guard.
    first = rows[0]["result"]
    tables = request["residual_template"]["polar"]["reynolds_tables"]
    load._walk(first["outputs"]["actual_load_request"])
    load._walk(first["outputs"]["actual_load_result"], output=True)
    report = {"fixture": "baseline" if baseline else "maximum_admitted_shape",
              "status": result["status"], "solve_state": result["outputs"]["solve_state"],
              "actual_calls": calls, "guarded_rows": len(rows), "tables": len(tables),
              "rows_per_table": len(tables[0]["rows"]),
              "actual_polar_table_limits": load._polar.section_polar_catalog()["limits"]["tables"],
              "actual_v133_limits": load.section_load_catalog()["limits"],
              "request": metrics(request), "response": metrics(result),
              "response_units": metrics(result["output_units"]),
              "one_residual_response": metrics(first),
              "actual_v133_request": metrics(first["outputs"]["actual_load_request"]),
              "actual_v133_response": metrics(first["outputs"]["actual_load_result"]),
              "evaluator_wall_seconds": elapsed, "peak_rss_kib_before": rss_before,
              "peak_rss_kib_after": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "limits": result["limits"], "references": [reference_summary(n) for n in (80, 120)],
              "gaps": ["Maximum table/row and escaped declaration string counts, not maximal numeric token bytes.",
                       "Observed Linux process RSS high-water mark includes interpreter/imports; not incremental allocation.",
                       "One bounded fixture does not prove all admitted allocation, runtime or serialization maxima.",
                       "Canonical hashing uses whole serialized temporaries after streaming byte checks; no API acceptance claim."]}
    report["units_fraction_of_response_bytes"] = (report["response_units"]["serialized_bytes"]
                                                 / report["response"]["serialized_bytes"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline", action="store_true")
    options = parser.parse_args()
    # Bound this experiment independently of the proposed model limits.
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (75, 75))
    report = run_audit(baseline=options.baseline)
    Path(options.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("actual_calls", "guarded_rows", "response",
                      "evaluator_wall_seconds", "peak_rss_kib_after")}, sort_keys=True))
