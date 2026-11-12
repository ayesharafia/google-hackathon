"""Bounded standalone V141 actual-work/quota audit; no conditional benchmark.

Fixture preparation evaluates real synthetic endpoint signs before its digest is frozen.
Configured-quota crossing is a separate run; no lowered quota or fabricated solve is used.
"""

import argparse
import hashlib
import json
import math
import resource
import signal
import time
from copy import deepcopy
from itertools import pairwise
from pathlib import Path

from physimesh.drone import stable_polar_rotor as rotor
from physimesh.drone import stable_section_residual as residual
from physimesh.drone import stable_section_solve as solve

_ENCODER = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    hashing = hashlib.sha256()
    for chunk in _ENCODER.iterencode(value):
        hashing.update(chunk.encode("utf-8"))
    return hashing.hexdigest()


def metrics(value):
    """Independent whole-object measurement; root1, dictionary keys counted as nodes."""
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
    size = sum(len(chunk.encode("utf-8")) for chunk in _ENCODER.iterencode(value))
    return {"nodes": nodes, "depth": depth, "serialized_bytes": size}


def resource_request(*, maximum_shape=False):
    boundaries = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
    annuli = []
    for inner, outer in pairwise(boundaries):
        radius = math.fsum((inner, 0.5 * math.fsum((outer, -inner))))
        lower = max(math.radians(0.1), 2 * math.atan((1 - radius) / (256 * radius)))
        count = 256 if maximum_shape else 3
        rows = [{"alpha_rad": -1.5 + 3 * i / (count - 1), "cl": 4.0, "cd": 0.1}
                for i in range(count)]
        re_values = [1000.0 * 10**i for i in range(8)] if maximum_shape else [1000.0, 1e9]
        polar = {"airfoil_id": "synthetic-resource", "source": "synthetic resource fixture; no dataset",
                 "source_kind": "synthetic", "uncertainty_status": "unknown",
                 "sampled_mach_number": 0.1, "declared_mach_interval": [0, 0.9],
                 "reynolds_tables": [{"reynolds_number": re, "rows": deepcopy(rows)} for re in re_values]}
        if maximum_shape:
            polar.update(airfoil_id="x" + "\x00" * 127, source="x" + "\x00" * 1999,
                         uncertainty_status="x" + "\x00" * 1999)
        annuli.append({"radial_inner_m": inner, "radial_outer_m": outer, "chord_m": 0.01,
                       "pitch_rad": 0.5, "polar": polar,
                       "solve": {"psi_lower_rad": lower, "psi_upper_rad": math.radians(20),
                                 "angle_tolerance_rad": 1e-30, "residual_tolerance_m2_s": 1e-30,
                                 "max_evaluations": 32}})
    return {"evaluation": rotor.EVALUATION, "numerical_policy": deepcopy(rotor._POLICY),
            "rotor": {"tip_radius_m": 1.0, "hub_radius_m": 0.2, "blade_count": 2,
                      "angular_speed_rad_s": 40.0, "imposed_axial_velocity_m_s": 0,
                      "density_kg_m3": 1.2, "dynamic_viscosity_pa_s": 1.8e-5,
                      "speed_of_sound_m_s": 343, "geometry_source": "fixed synthetic resource geometry",
                      "uncertainty_status": "unknown"}, "annuli": annuli}


def prepare_fixture(request):
    """Actual endpoint checks, no measured targets or solver-response fabrication."""
    checks = []
    actual_requests, _ = rotor._preflight(request)
    for index, actual in enumerate(actual_requests):
        endpoints = []
        for name in ("psi_lower_rad", "psi_upper_rad"):
            prescribed = deepcopy(actual["residual_template"])
            prescribed["section"]["psi_rad"] = actual["solve"][name]
            result = residual.evaluate_stable_section_residual(prescribed)
            assert result["status"] == "COMPUTED_EXPERIMENTAL", (index, name, result["reasons"])
            solve._guard_residual(result, prescribed)
            output = result["outputs"]
            factor = output["factor_representation"]
            assert output["residual_state"] == "COMPUTED" and factor is not None
            assert factor["correction_m2_s"] > 0 and 2**-20 <= factor["f"] <= 512
            endpoints.append({"endpoint": name, "psi_rad": prescribed["section"]["psi_rad"],
                              "f": factor["f"], "correction_m2_s": factor["correction_m2_s"],
                              "residual_m2_s": output["residual_m2_s"]})
        assert endpoints[0]["residual_m2_s"] < 0 < endpoints[1]["residual_m2_s"], (index, endpoints)
        checks.append({"annulus_index": index, "endpoints": endpoints})
    return {"fixture_sha256": digest(request), "preparation_actual_residual_calls": 16,
            "endpoint_checks": checks,
            "scope": "Synthetic resource preparation only; fixed geometry/Cl/chord, no historical benchmark."}


class _AuditDeadline(BaseException):
    """Independent wall limit, propagated through model ordinary-Exception handlers."""


def _deadline(signum, frame):
    raise _AuditDeadline


def set_process_limits(wall_seconds):
    resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024**2, 1536 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    signal.signal(signal.SIGALRM, _deadline)
    signal.setitimer(signal.ITIMER_REAL, wall_seconds)


class _AttemptSpies:
    """Forward every actual call; observe parent operations without replacing admission."""

    def __init__(self):
        self.children = []
        self.residual_calls = 0
        self.raw_ids = {}
        self.by_request_hash = {}
        self.copy_events, self.hash_events, self.guard_events, self.guard_successes = [], [], [], []
        self.snapshot_attempts, self.snapshot_successes = [], []
        self.originals = []

    def _patch(self, target, name, replacement):
        self.originals.append((target, name, getattr(target, name)))
        setattr(target, name, replacement)

    def install(self):
        actual_solve = solve.evaluate_stable_section_solve
        actual_residual = residual.evaluate_stable_section_residual
        parent_copy, parent_hash = rotor.deepcopy, rotor.sha256_record
        parent_guard, parent_snapshot = rotor._guard_solve, rotor._snapshot_child

        def solve_call(request):
            index = len(self.children)
            info = {"attempt_index": index, "request_sha256": digest(request)}
            self.children.append(info)
            before = self.residual_calls
            value = actual_solve(request)
            info.update(raw_metrics=metrics(value), status=value["status"],
                        residual_calls=self.residual_calls - before,
                        returned_residual_count=value["residual_result_count"],
                        solve_state=value["outputs"].get("solve_state"))
            self.raw_ids[id(value)] = index
            self.by_request_hash[value["request_sha256"]] = index
            return value

        def residual_call(request):
            self.residual_calls += 1
            return actual_residual(request)

        def copying(value, *args, **kwargs):
            if (id(value) in self.raw_ids and type(value) is dict
                    and value.get("evaluation") == solve.EVALUATION
                    and self.by_request_hash.get(value.get("request_sha256")) == self.raw_ids[id(value)]):
                self.copy_events.append(self.raw_ids[id(value)])
            return parent_copy(value, *args, **kwargs)

        def hashing(value):
            if (type(value) is dict and value.get("evaluation") == solve.EVALUATION
                    and value.get("status") == "COMPUTED_EXPERIMENTAL"):
                self.hash_events.append(self.by_request_hash.get(value.get("request_sha256")))
            return parent_hash(value)

        def guarding(value, request):
            index = self.by_request_hash.get(value.get("request_sha256"))
            self.guard_events.append(index)
            result = parent_guard(value, request)
            self.guard_successes.append(index)
            return result

        def snapshotting(value, quota):
            index = self.raw_ids.get(id(value))
            self.snapshot_attempts.append(index)
            result = parent_snapshot(value, quota)
            self.snapshot_successes.append(index)
            return result

        self._patch(solve, "evaluate_stable_section_solve", solve_call)
        self._patch(residual, "evaluate_stable_section_residual", residual_call)
        self._patch(rotor, "deepcopy", copying)
        self._patch(rotor, "sha256_record", hashing)
        self._patch(rotor, "_guard_solve", guarding)
        self._patch(rotor, "_snapshot_child", snapshotting)

    def restore(self):
        for target, name, original in reversed(self.originals):
            setattr(target, name, original)

    def report(self):
        return {"actual_solve_attempts": len(self.children), "actual_residual_attempts": self.residual_calls,
                "children": self.children, "parent_raw_child_copy_events": self.copy_events,
                "parent_whole_child_hash_events": self.hash_events,
                "parent_guard_attempts": self.guard_events,
                "parent_successful_guard_events": self.guard_successes,
                "parent_snapshot_attempts": self.snapshot_attempts,
                "parent_snapshot_successes": self.snapshot_successes}


def run_audit(*, maximum_shape, output_path, wall_seconds):
    """Prepare/freeze the synthetic fixture, then measure one actual composition."""
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    request = resource_request(maximum_shape=maximum_shape)
    report = {"audit_status": "PREPARING", "fixture": "maximum_shape" if maximum_shape else "small_polar",
              "process_limits": {"address_space_bytes": 1536 * 1024**2,
                                 "cpu_seconds": 600, "wall_seconds": wall_seconds},
              "quota": {"canonical_whole_child_bytes": rotor._CHILD_BYTES_MAX,
                        "whole_child_nodes": rotor._CHILD_NODES_MAX},
              "scope": "Synthetic resource audit only; no historical/conditional benchmark or physical validation."}

    def persist():
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    persist()
    spies = _AttemptSpies()
    result = None
    try:
        report["preparation"] = prepare_fixture(request)
        frozen_digest = report["preparation"]["fixture_sha256"]
        report["request_metrics"] = metrics(request)
        report["audit_status"] = "RUNNING_FROZEN_FIXTURE"
        persist()
        spies.install()
        eval_wall, eval_cpu = time.perf_counter(), time.process_time()
        try:
            result = rotor.evaluate_stable_polar_rotor(request)
        finally:
            report["evaluation_wall_seconds"] = time.perf_counter() - eval_wall
            report["evaluation_cpu_seconds"] = time.process_time() - eval_cpu
            spies.restore()
        report.update(spies.report())
        report["fixture_unchanged_after_evaluation"] = digest(request) == frozen_digest
        report["response_status"] = result["status"]
        report["response_reasons"] = result["reasons"]
        report["accepted_section_solves"] = result["section_solve_result_count"]
        report["accepted_residuals"] = result["residual_result_count"]
        report["accepted_loads"] = result["load_result_count"]
        report["accepted_lookups"] = result["lookup_result_count"]
        report["response_metrics"] = metrics(result)
        report["response_units_metrics"] = metrics(result["output_units"])
        report["response_hashes"] = {key: result[key] for key in ("request_sha256", "evaluation_sha256")}
        report["actual_children_total_metrics"] = {
            "serialized_bytes": sum(info["raw_metrics"]["serialized_bytes"] for info in spies.children),
            "nodes": sum(info["raw_metrics"]["nodes"] for info in spies.children)}
        accepted = result["section_solve_result_count"]
        report["accepted_children_total_metrics"] = {
            "serialized_bytes": sum(info["raw_metrics"]["serialized_bytes"] for info in spies.children[:accepted]),
            "nodes": sum(info["raw_metrics"]["nodes"] for info in spies.children[:accepted])}
        errors = []
        if not report["fixture_unchanged_after_evaluation"]:
            errors.append("Frozen request changed.")
        if len(spies.children) != 8 or spies.residual_calls != 256:
            errors.append("Actual attempts did not reach eight solves /256 residuals; inspect per-child states/counts.")
        if any(info.get("residual_calls") != 32 or info.get("returned_residual_count") != 32
               or info.get("solve_state") != "EVALUATION_BUDGET_EXHAUSTED" for info in spies.children):
            errors.append("At least one actual annulus did not exhaust32 genuine residual calls.")
        if maximum_shape:
            if result["status"] != "EXECUTION_FAILED" or result["reasons"] != ["RESOURCE_BUDGET_EXCEEDED"]:
                errors.append("Configured cumulative quota crossing not observed; no quota alteration permitted.")
            rejected = accepted
            report["first_rejected_attempt_index"] = rejected
            report["rejected_parent_operations"] = {
                "raw_child_copies": spies.copy_events.count(rejected),
                "whole_child_hashes": spies.hash_events.count(rejected),
                "guard_attempts": spies.guard_events.count(rejected),
                "successful_guards": spies.guard_successes.count(rejected)}
            if any(report["rejected_parent_operations"].values()):
                errors.append("Rejected child received a parent copy/hash/guard.")
            if result["outputs"] != {} or result["output_units"] != {}:
                errors.append("Resource receipt did not clear payload atomically.")
        else:
            if (result["status"] != "COMPUTED_EXPERIMENTAL" or accepted != 8
                    or result["residual_result_count"] != 256):
                errors.append("Small-polar composition did not admit eight whole solves /256 residuals.")
            if result["outputs"].get("integrated") is not None:
                errors.append("Nonconverged fixture unexpectedly produced integrated totals.")
            if any(spies.copy_events.count(i) != 1 or spies.guard_events.count(i) != 1
                   or spies.guard_successes.count(i) != 1 for i in range(8)):
                errors.append("Expected one raw parent copy and one successful independent guard per admitted solve.")
        if result["request_sha256"] != frozen_digest:
            errors.append("Request hash does not bind the frozen fixture.")
        if result["evaluation_sha256"] != digest({k: v for k, v in result.items() if k != "evaluation_sha256"}):
            errors.append("Response hash mismatch.")
        report["verification_errors"] = errors
        report["audit_status"] = "PASSED" if not errors else "UNRESOLVED"
    except BaseException as error:  # noqa: BLE001 -- persist wall-abort receipt; CLI exits nonzero.
        spies.restore()
        report.update(spies.report())
        report["audit_status"] = "ABORTED"
        report["abort_type"] = type(error).__name__
        report["verification_errors"] = ["Process/fixture/evaluation audit interrupted; do not relax caps or claim completion."]
    finally:
        report["total_wall_seconds"] = time.perf_counter() - started_wall
        report["total_cpu_seconds"] = time.process_time() - started_cpu
        report["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report["qualification_gaps"] = [
            "Measured synthetic cases only, not maximum allocation or RAM/API/time/concurrency proof.",
            "Child evaluator allocated/hashed its returned result before parent quota admission.",
            "Request copies, wrappers and expanded units are outside retained-child quota; root export ceiling is separate.",
            "RSS is a Linux process high-water mark including imports and audit instrumentation."]
        persist()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--maximum-shape", action="store_true")
    parser.add_argument("--wall-seconds", type=int, default=90)
    options = parser.parse_args()
    if not 1 <= options.wall_seconds <= 720:
        parser.error("wall-seconds must be1..720")
    set_process_limits(options.wall_seconds)
    report = run_audit(maximum_shape=options.maximum_shape, output_path=options.output,
                       wall_seconds=options.wall_seconds)
    signal.setitimer(signal.ITIMER_REAL, 0)
    print(json.dumps({key: report.get(key) for key in (
        "audit_status", "actual_solve_attempts", "actual_residual_attempts", "accepted_section_solves",
        "accepted_residuals", "response_status", "response_reasons", "response_metrics",
        "evaluation_wall_seconds", "peak_rss_kib", "verification_errors")}, sort_keys=True))
    raise SystemExit(0 if report["audit_status"] == "PASSED" else 1)
