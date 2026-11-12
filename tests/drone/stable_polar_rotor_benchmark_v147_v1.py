"""V147 v1: untuned, owner-executed R0; authoring only, acceptance pending.

Development: /tmp/venv311/bin/python tests/drone/stable_polar_rotor_benchmark_v147_v1.py --self-test
Owner R0: same script --run-r0 --output-dir NEW_DIRECTORY --expected-harness-sha256 REVIEWED_SHA256

Self-test calls public catalogs only, never evaluators or private preflights. R0
uses a fresh output directory as its exclusive attempt marker; it cannot resume.
The owner must designate that directory once per reviewed hash. Global prevention
of another directory/copy would require an external persistent admission ledger.
No app persistence, monkeypatches, solver-private access, network or fitted inputs.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import resource
import signal
import sys
import time
from collections import Counter
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

# Keep direct-script repo imports read-only, including their bytecode caches.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from physimesh.drone import polar_rotor as legacy
from physimesh.drone import stable_polar_rotor as stable

VERSION = "v147_stable_rotor_benchmark_v1"
LABEL = ("numerical difference between two unvalidated solvers on identical synthetic inputs; "
         "not an error estimate, not physical accuracy, not a validation result.")
BUDGET_COMPARABILITY = (
    "Budget comparability: legacy admits max_evaluations 2..16 per annulus with aggregate <= 128 per rotor; "
    "the stable contract admits 2..32 per annulus with aggregate <= 256. "
    "This declared family pins max_evaluations 16 for every annulus, worst case 8x16=128, "
    "so every case is admitted identically under both contracts and the stable higher ceilings are never exercised: "
    "measured convergence differences on this family cannot be explained by allowed work. "
    "Actual residual evaluations used are reported per case per solver alongside convergence counts."
)
CONTRACT_BUDGETS = {"legacy": {"per_annulus_min": 2, "per_annulus_max": 16, "aggregate_max": 128},
                    "stable": {"per_annulus_min": 2, "per_annulus_max": 32, "aggregate_max": 256}}
REVISION_NOTE = ("Pre-admission spec amendment: 12 primary + 12 stress = 24 total unchanged; "
                 "verbatim budget-comparability argument, adjacent work/convergence reporting, "
                 "and explicit one-contract-only admission-refusal enumeration. R0 not executed by author.")
CAPS = {"wall_seconds": 120.0, "cpu_seconds": 120.0,
        "scope": "Per case: both evaluators, deep copies, raw retention and parent response checks; "
                 "CPU is child plus parent. Final receipts/log/manifest generation is outside the cap.",
        "order": ["legacy", "stable"], "overrun": "Failure, never retry or resume."}
SOLVE = {"psi_lower_rad": 0.35, "psi_upper_rad": 0.9, "angle_tolerance_rad": 0.001,
         "residual_tolerance_m2_s": 0.01, "max_evaluations": 16}
POLICY = {"id": "stable_deficit_binary64_v1", "f_min": 2**-20, "f_max": 512}
COUNTS = ("section_solve_result_count", "residual_result_count", "load_result_count", "lookup_result_count")
TOTALS = {"total_thrust_n": "N", "total_torque_nm": "N*m", "shaft_power_w": "W"}
ENCODER = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
NOT_ESTABLISHED = [
    "Physical validation, physical accuracy, aircraft qualification or feasibility.",
    "An error estimate, uncertainty bound, GCI or mesh/discretization convergence.",
    "TN626 evidence, measured data, CFD fields, or changes to the legacy 36 null results.",
    "Stable-solver acceptance, production readiness or superiority.",
    "Runtime outside this fixed synthetic family, machine and declared caps.",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    hashing = hashlib.sha256()
    for chunk in ENCODER.iterencode(value):
        hashing.update(chunk.encode("utf-8"))
    return hashing.hexdigest()


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    """Commit complete native JSON; interrupted .partial files remain explicit evidence."""
    partial = path.with_name(path.name + ".partial")
    require(not path.exists(), f"Artifact already exists: {path.name}")
    with partial.open("x", encoding="utf-8", newline="") as stream:
        for chunk in ENCODER.iterencode(value):
            stream.write(chunk)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(partial, path)  # Atomic no-overwrite publication within the declared directory.
    partial.unlink()


def catalogs():
    result = {"legacy": legacy.polar_rotor_catalog(), "stable": stable.stable_polar_rotor_catalog()}
    require(result["legacy"]["schema_version"] == "polar_rotor_v1", "Legacy schema drift")
    require(result["stable"]["schema_version"] == "stable_polar_rotor_v1", "Stable schema drift")
    require(digest(result["stable"]["numerical_policy"]) == digest(POLICY), "Stable policy drift")
    return result


def case_family():
    """Literal fixture provenance: tests/drone/test_polar_rotor.py::request_data.

    Flat polars, chord and source text match that fixture. Only the declared cl,
    annulus partition, stress pitch/axial velocity vary. Rational equal-width
    boundaries are each rounded once to float; shared edges reuse that value.
    """
    cases = []
    for family, pitch, axial in (("base", 0.5, 5), ("stress", 0.65, 8.0)):
        for cl in (1.0, 2.0, 4.0):
            for count in (1, 2, 4, 8):
                boundaries = [float(Fraction(1, 5) + Fraction(2 * i, 5 * count)) for i in range(count + 1)]
                rotor = {"tip_radius_m": 0.6, "hub_radius_m": 0.2, "blade_count": 2,
                         "angular_speed_rad_s": 50, "imposed_axial_velocity_m_s": axial,
                         "density_kg_m3": 1.2, "dynamic_viscosity_pa_s": 1.8e-5,
                         "speed_of_sound_m_s": 343, "geometry_source": "invented fixture; no dataset",
                         "uncertainty_status": "unknown"}
                polar = {"airfoil_id": "invented-synthetic", "source": "invented fixture; no dataset",
                         "source_kind": "synthetic", "uncertainty_status": "unknown",
                         "sampled_mach_number": 0.1, "declared_mach_interval": [0, 0.9],
                         "reynolds_tables": [{"reynolds_number": re, "rows": [
                             {"alpha_rad": alpha, "cl": cl, "cd": 0.1} for alpha in (-1.5, 0.0, 1.5)]}
                             for re in (1000.0, 10000000.0)]}
                annuli = [{"radial_inner_m": boundaries[i], "radial_outer_m": boundaries[i + 1],
                           "chord_m": 0.1, "pitch_rad": pitch, "polar": deepcopy(polar),
                           "solve": deepcopy(SOLVE)} for i in range(count)]
                request = {"evaluation": "polar_rotor_experimental", "rotor": rotor, "annuli": annuli}
                stable_request = {**deepcopy(request), "evaluation": "stable_polar_rotor_experimental",
                                  "numerical_policy": deepcopy(POLICY)}
                cases.append({"id": f"{family}_cl{int(cl)}_annuli{count}", "family": family,
                              "cl": cl, "annuli": count, "requests": {"legacy": request, "stable": stable_request}})
    return cases


def native_limits(value, limits):
    nodes = 0

    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        require(nodes <= limits["max_nodes_including_keys"] and depth <= limits["max_depth"], "JSON quota")
        kind = type(item)
        if kind is dict:
            require(len(item) <= limits["max_container_items"], "Object quota")
            for key, child in item.items():
                require(type(key) is str, "Non-string key")
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif kind is list:
            require(len(item) <= limits["max_container_items"], "Array quota")
            for child in item:
                visit(child, depth + 1)
        elif kind is str:
            require(len(item) <= limits["max_string_characters"], "String quota")
            item.encode("utf-8", "strict")
        elif kind is int:
            require(item.bit_length() <= limits["max_integer_bits"], "Integer quota")
        elif kind is float:
            require(math.isfinite(item) and (item == 0 or abs(item) >= sys.float_info.min), "Float boundary")
        else:
            raise ValueError("Foreign or non-schema native type; this family has no bool/null fields")

    visit(value, 1)
    size = sum(len(chunk.encode("utf-8")) for chunk in ENCODER.iterencode(value))
    require(size <= limits.get("max_serialized_bytes", size), "Serialized quota")


def preflight(case, solver, catalog):
    """Independent static family/schema check, NOT producer-private admission or a solve."""
    request = case["requests"][solver]
    native_limits(request, catalog["limits"]["input_json"])
    require(set(request) == set(catalog["required_fields"]), "Request keys")
    require(request["evaluation"] == catalog["evaluation"], "Evaluation identity")
    if solver == "stable":
        require(digest(request["numerical_policy"]) == digest(POLICY), "Policy mapping")
    rotor, rows = request["rotor"], request["annuli"]
    require(set(rotor) == set(catalog["input_units"]["rotor"]), "Rotor keys")
    require(len(rows) == case["annuli"] and len(rows) in (1, 2, 4, 8), "Annulus count")
    require(rotor["hub_radius_m"] == 0.2 and rotor["tip_radius_m"] == 0.6, "Hub/tip")
    require(type(rotor["blade_count"]) is int and rotor["blade_count"] == 2, "Blades")
    for key, expected in (("angular_speed_rad_s", 50), ("density_kg_m3", 1.2),
                          ("dynamic_viscosity_pa_s", 1.8e-5), ("speed_of_sound_m_s", 343)):
        require(type(rotor[key]) in (int, float) and rotor[key] == expected, "Physical fixture drift")
    require(rotor["imposed_axial_velocity_m_s"] == (5 if case["family"] == "base" else 8.0), "Axial")
    require(rotor["geometry_source"] == "invented fixture; no dataset" and rotor["uncertainty_status"] == "unknown",
            "Geometry source drift")
    previous = rotor["hub_radius_m"]
    for index, row in enumerate(rows):
        require(set(row) == set(catalog["input_units"]["annuli"]), "Annulus keys")
        inner, outer = row["radial_inner_m"], row["radial_outer_m"]
        require(type(inner) is float and type(outer) is float and inner == previous < outer, "Edges")
        require(outer == float(Fraction(1, 5) + Fraction(2 * (index + 1), 5 * len(rows))), "Equal split")
        require(row["chord_m"] == 0.1 and row["pitch_rad"] == (0.5 if case["family"] == "base" else 0.65),
                "Chord/pitch")
        require(digest(row["solve"]) == digest(SOLVE), "Fixed solve block drift")
        require(set(row["polar"]) == set(catalog["input_units"]["annuli"]["polar"]), "Polar keys")
        polar = row["polar"]
        require(polar["airfoil_id"] == "invented-synthetic" and polar["source_kind"] == "synthetic", "Provenance")
        require(polar["source"] == "invented fixture; no dataset" and polar["uncertainty_status"] == "unknown",
                "Polar source drift")
        require(polar["sampled_mach_number"] == 0.1 and polar["declared_mach_interval"] == [0, 0.9], "Mach")
        require(len(polar["reynolds_tables"]) == 2, "Re tables")
        for table, re in zip(polar["reynolds_tables"], (1000.0, 10000000.0), strict=True):
            require(set(table) == {"reynolds_number", "rows"} and table["reynolds_number"] == re, "Re")
            require(table["rows"] == [{"alpha_rad": alpha, "cl": case["cl"], "cd": 0.1}
                                      for alpha in (-1.5, 0.0, 1.5)], "Flat polar drift")
        previous = outer
    require(previous == rotor["tip_radius_m"], "Full span")
    bounds = CONTRACT_BUDGETS[solver]
    require(all(bounds["per_annulus_min"] <= row["solve"]["max_evaluations"] <= bounds["per_annulus_max"]
                for row in rows), "Per-annulus contract budget")
    require(sum(row["solve"]["max_evaluations"] for row in rows) <= bounds["aggregate_max"], "Aggregate solve budget")


def check_family(cases, contracts):
    require(len(cases) == 24 and len({case["id"] for case in cases}) == 24, "Declared family size")
    expected = {(family, cl, count) for family in ("base", "stress") for cl in (1.0, 2.0, 4.0)
                for count in (1, 2, 4, 8)}
    require({(case["family"], case["cl"], case["annuli"]) for case in cases} == expected, "Full declared grid")
    for case in cases:
        for solver in ("legacy", "stable"):
            preflight(case, solver, contracts[solver])
        physical = [{key: value for key, value in request.items() if key not in ("evaluation", "numerical_policy")}
                    for request in case["requests"].values()]
        require(digest(physical[0]) == digest(physical[1]), "Identical native physical inputs required")


def budget_comparability(cases):
    largest = {}
    for solver in ("legacy", "stable"):
        budgets = [[row["solve"]["max_evaluations"] for row in case["requests"][solver]["annuli"]]
                   for case in cases]
        require(all(value == 16 for values in budgets for value in values), "Declared 16-per-annulus budget")
        largest[solver] = max(map(sum, budgets))
        require(largest[solver] == 128, "Declared worst case must be 8 x 16 = 128")
    return {"contract_bounds": CONTRACT_BUDGETS, "declared_per_annulus": 16,
            "largest_requested_aggregate": largest, "stable_higher_ceilings_exercised": False,
            "attribution_rule": "No improvement is attributed to the stable kernel by this harness. "
                                "Budget comparability requires equal requested work; any one-contract-only "
                                "admission refusal remains a reported KIND difference."}


def sources():
    paths = sorted((ROOT / "src/physimesh/drone").glob("*.py"))
    paths.append(ROOT / "tests/drone/test_polar_rotor.py")
    return {str(path.relative_to(ROOT)): file_digest(path) for path in paths}


class CapExceeded(BaseException):
    """Not swallowed by the evaluators' ordinary-Exception boundaries."""


def cap_signal(signum, frame):
    raise CapExceeded("wall" if signum == signal.SIGALRM else "cpu")


def timers(wall, cpu):
    signal.signal(signal.SIGALRM, cap_signal)
    signal.signal(signal.SIGPROF, cap_signal)
    signal.setitimer(signal.ITIMER_REAL, max(wall, 1e-6))
    signal.setitimer(signal.ITIMER_PROF, max(cpu, 1e-6))


def disarm():
    signal.setitimer(signal.ITIMER_REAL, 0)
    signal.setitimer(signal.ITIMER_PROF, 0)


def worker(case, directory):
    calls, errors = {}, []
    resource.setrlimit(resource.RLIMIT_CPU, (int(CAPS["cpu_seconds"]) + 1,) * 2)
    timers(CAPS["wall_seconds"], CAPS["cpu_seconds"])
    try:
        for solver, evaluate in (("legacy", legacy.evaluate_polar_rotor),
                                 ("stable", stable.evaluate_stable_polar_rotor)):
            started_wall, started_cpu = time.perf_counter(), time.process_time()
            calls[solver] = {"attempted": True, "returned": False}
            try:
                response = evaluate(deepcopy(case["requests"][solver]))
                calls[solver]["returned"] = True
            except Exception as error:  # noqa: BLE001 -- continue the other solver once; no retry.
                errors.append({"solver": solver, "type": type(error).__name__, "detail": str(error)})
                continue
            finally:
                calls[solver].update(wall_seconds=time.perf_counter() - started_wall,
                                     cpu_seconds=time.process_time() - started_cpu)
            # Preserve the whole public object before interpreting it; never reseal/repair it.
            save(directory / f"{solver}.response.json", response)
    except BaseException as error:  # noqa: BLE001 -- retain a failure receipt, never retry a call.
        errors.append({"type": type(error).__name__, "detail": str(error)})
    finally:
        disarm()
        save(directory / "worker.json", {"calls": calls, "errors": errors})
    return 1 if errors else 0


def measurement(response, request, solver):
    require(type(response) is dict, "Response root")
    output = response["outputs"]
    state = output.get("rotor_state")
    rows = output.get("annuli", [])
    child_key = "solve_result" if solver == "legacy" else "actual_solve_result"
    states = [{"annulus_index": row["annulus_index"], "solve_state": row[child_key]["outputs"]["solve_state"]}
              for row in rows]
    totals = None
    if state == "COMPUTED":
        integrated, units = output["integrated"], response["output_units"]["integrated"]
        if solver == "legacy":
            raw, units = integrated["totals"], units["totals"]
            totals = {"total_thrust_n": raw["thrust_n"], "total_torque_nm": raw["torque_nm"],
                      "shaft_power_w": raw["shaft_power_w"]}
            require(units == {"thrust_n": "N", "torque_nm": "N*m", "shaft_power_w": "W"}, "Legacy units")
        else:
            totals = {key: integrated[key] for key in TOTALS}
            require(units == TOTALS, "Stable units")
        require(all(type(value) is float and math.isfinite(value) for value in totals.values()), "Totals")
    for key in COUNTS:
        require(type(response[key]) is int and response[key] >= 0, "Count type")
    sealed = response.get("evaluation_sha256")
    seal_ok = type(sealed) is str and sealed == digest({
        key: value for key, value in response.items() if key != "evaluation_sha256"})
    bound = response.get("request_sha256") == digest(request)
    return {"status": response["status"], "rotor_state": state,
            **{key: response[key] for key in COUNTS}, "section_states": states,
            "converged_annuli": sum(row["solve_state"] == "CONVERGED" for row in states),
            "work_and_convergence": {
                "converged_annuli": sum(row["solve_state"] == "CONVERGED" for row in states),
                "actual_residual_evaluations_used": (None if response["status"] == "EXECUTION_FAILED"
                                                     else response["residual_result_count"]),
                "reported_accepted_residual_result_count": response["residual_result_count"],
                "requested_per_annulus_max": SOLVE["max_evaluations"],
                "requested_aggregate_max": sum(row["solve"]["max_evaluations"] for row in request["annuli"]),
                "count_scope": "Producer-reported retained evaluations; EXECUTION_FAILED exposes only "
                               "accepted counts, so total residual work including rejected work is unknown.",
            },
            "totals": totals, "output_units": TOTALS if totals is not None else None,
            "reasons": deepcopy(response["reasons"]), "self_seal_verified": seal_ok,
            "request_digest_verified": bound}


def compare(measured):
    kinds = {}
    for solver in ("legacy", "stable"):
        value = measured.get(solver)
        kinds[solver] = None if value is None else {
            key: value[key] for key in ("status", "rotor_state", "section_solve_result_count",
                                       "converged_annuli", "section_states", "reasons")}
    differences = None
    if all(measured.get(solver, {}).get("totals") is not None for solver in ("legacy", "stable")):
        differences = {}
        for key, unit in TOTALS.items():
            delta = math.fsum((measured["stable"]["totals"][key], -measured["legacy"]["totals"][key]))
            require(math.isfinite(delta), "Unrepresentable signed delta")
            differences[key] = {"signed_stable_minus_legacy": delta, "absolute": abs(delta), "unit": unit}
    known = all(value is not None for value in kinds.values())
    refused = [solver for solver, value in kinds.items()
               if value is not None and value["status"] in ("MODEL_INAPPLICABLE", "SOLVER_UNSUPPORTED")]
    return {"label": LABEL, "deltas": differences,
            "delta_availability": "BOTH_COMPUTED" if differences is not None else "UNAVAILABLE_NO_PAIRED_TOTALS",
            "admission_refusal_solvers": refused,
            "one_contract_only_admission_refusal": len(refused) == 1 if known else None,
            "kind_difference": kinds["legacy"] != kinds["stable"] if known else None, "outcomes_by_solver": kinds}


def run_case(case, directory):
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    pid, reaped, usage = None, False, None
    report = {"case": case["id"], "measurements": {}, "errors": [], "comparison": compare({})}
    try:
        timers(CAPS["wall_seconds"], CAPS["cpu_seconds"])
        pid = os.fork()
        if pid == 0:
            try:
                os._exit(worker(case, directory))
            except BaseException:  # noqa: BLE001 -- parent records interrupted/missing worker artifacts.
                os._exit(2)
        _, status, usage = os.wait4(pid, 0)
        reaped = True
        child_cpu = usage.ru_utime + usage.ru_stime
        remaining_cpu = CAPS["cpu_seconds"] - child_cpu - (time.process_time() - start_cpu)
        if remaining_cpu <= 0:
            raise CapExceeded("cpu")
        signal.setitimer(signal.ITIMER_PROF, remaining_cpu)
        report["worker_exit_code"] = os.waitstatus_to_exitcode(status)
        if status != 0:
            report["errors"].append("Worker failed or exceeded its cap; attempt consumed, no retry.")
        for solver in ("legacy", "stable"):
            path = directory / f"{solver}.response.json"
            if not path.exists():
                report["errors"].append(f"{solver}: no complete returned response retained")
                continue
            response = json.loads(path.read_text(encoding="utf-8"))
            report["measurements"][solver] = measurement(response, case["requests"][solver], solver)
            if not all(report["measurements"][solver][key] for key in ("self_seal_verified", "request_digest_verified")):
                report["errors"].append(f"{solver}: response seal/request binding not established; raw object retained")
        if (directory / "worker.json").exists():
            report["worker"] = json.loads((directory / "worker.json").read_text(encoding="utf-8"))
            for solver, value in report["measurements"].items():
                value["evaluation_usage"] = report["worker"]["calls"].get(solver)
        report["comparison"] = compare(report["measurements"])
    except BaseException as error:  # Failure consumes this case; never retry or substitute data.
        report["errors"].append({"type": type(error).__name__, "detail": str(error)})
        if pid is not None and not reaped:
            try:
                observed, status, usage = os.wait4(pid, os.WNOHANG)
                if observed == 0:
                    os.kill(pid, signal.SIGKILL)
                    _, status, usage = os.wait4(pid, 0)
                reaped = True
            except ChildProcessError:
                pass  # Already reaped just before interruption; do not signal a recycled PID.
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        disarm()
        report["wall_seconds"] = time.perf_counter() - start_wall
        report["cpu_seconds"] = time.process_time() - start_cpu + (0 if usage is None else usage.ru_utime + usage.ru_stime)
        if report["wall_seconds"] > CAPS["wall_seconds"] or report["cpu_seconds"] > CAPS["cpu_seconds"]:
            report["errors"].append("Measured case cap overrun: failure, never retry.")
        save(directory / "case.json", report)
    return report


def inventory(output):
    return {str(path.relative_to(output)): {"sha256": file_digest(path), "bytes": path.stat().st_size}
            for path in sorted(output.rglob("*")) if path.is_file() and path.name not in ("manifest.json", "manifest.sha256")}


def run_r0(output, expected):
    harness = Path(__file__).resolve()
    pinned = file_digest(harness)
    require(expected == pinned, "Reviewed harness SHA256 mismatch; R0 not admitted")
    require(output.parent.is_dir() and not output.exists(), "Output must be a NEW directory; never resume/reuse R0")
    output.mkdir()  # Exclusive admission: any subsequent failure consumes this output directory.
    save(output / "R0-attempt.json", {
        "harness_sha256": pinned, "version": VERSION, "attempt": "R0", "caps": CAPS,
        "revision_note": REVISION_NOTE,
        "revision_rule": "Any failure consumes R0. Corrections require a new versioned harness hash "
                         "and a narrow diff note; no retries or resumption of this attempt."})
    reports, errors = [], []
    before = {}
    with (output / "run.log").open("x", encoding="utf-8") as log:
        def emit(value):
            line = ENCODER.encode(value)
            log.write(line + "\n")
            log.flush()
            print(line, flush=True)

        # Plain text retains the spec's exact wording and line breaks in stdout and run.log.
        log.write(BUDGET_COMPARABILITY + "\n")
        log.flush()
        print(BUDGET_COMPARABILITY, flush=True)
        try:
            before = sources()
            contracts, cases = catalogs(), case_family()
            check_family(cases, contracts)
            declared_budget = budget_comparability(cases)
            with (output / "harness.py").open("xb") as source_copy:
                source_copy.write(harness.read_bytes())
            plan = [{key: value for key, value in case.items() if key != "requests"} for case in cases]
            # Freeze all 48 native requests before the first evaluator call.
            for case in cases:
                directory = output / case["id"]
                directory.mkdir()
                for solver, request in case["requests"].items():
                    save(directory / f"{solver}.request.json", request)
            save(output / "plan.json", {"cases": plan, "caps": CAPS, "catalogs": contracts, "sources": before,
                                        "budget_comparability": declared_budget,
                                        "budget_comparability_argument": BUDGET_COMPARABILITY})
            emit({"version": VERSION, "attempt": "R0", "harness_sha256": pinned, "caps": CAPS,
                  "budget_comparability_argument": BUDGET_COMPARABILITY,
                  "label": LABEL, "status": "authoring only, acceptance pending"})
            for case in cases:
                report = run_case(case, output / case["id"])
                reports.append(report)
                emit(report)
            if sources() != before or file_digest(harness) != pinned:
                errors.append("Harness or recorded source files changed during execution")
        except BaseException as error:  # noqa: BLE001 -- preserve incomplete candidate packet; no resume.
            errors.append({"type": type(error).__name__, "detail": str(error)})
        kind_differences = [{"case": row["case"], **row["comparison"]} for row in reports
                            if row.get("comparison", {}).get("kind_difference")]
        failed = bool(errors) or len(reports) != 24 or any(row["errors"] for row in reports)
        outcomes = {}
        for solver in ("legacy", "stable"):
            values = [row["measurements"][solver] for row in reports if solver in row["measurements"]]
            outcomes[solver] = {
                "retained_complete_response_files": len(list(output.rglob(f"{solver}.response.json"))),
                "measured_responses": len(values), "status_counts": dict(Counter(value["status"] for value in values)),
                "rotor_state_counts": dict(Counter(value["rotor_state"] or "NO_ROTOR_RESULT" for value in values)),
                "converged_annuli": sum(value["converged_annuli"] for value in values),
                "budget_exhausted_annuli": sum(state["solve_state"] == "EVALUATION_BUDGET_EXHAUSTED"
                                               for value in values for state in value["section_states"]),
            }
        summary = {"execution_status": "FAILED" if failed else "COMPLETE", "case_reports": len(reports),
                   "planned_cases": 24, "label": LABEL, "kind_differences": kind_differences,
                   "budget_comparability_argument": BUDGET_COMPARABILITY, "revision_note": REVISION_NOTE,
                   "one_contract_only_admission_refusals": [
                       {"case": row["case"], "refused_by": row["comparison"]["admission_refusal_solvers"],
                        "outcomes_by_solver": row["comparison"]["outcomes_by_solver"]}
                       for row in reports if row["comparison"]["one_contract_only_admission_refusal"]],
                   "solver_outcomes": outcomes,
                   "kind_assessment_unavailable": [row["case"] for row in reports
                                                   if row["comparison"]["kind_difference"] is None],
                   "errors": errors, "not_established": NOT_ESTABLISHED}
        emit(summary)
    memo = ("V147 v1 R0: authoring only, acceptance pending.\n\n" + LABEL + "\n\n" + BUDGET_COMPARABILITY + "\n\n" +
            ENCODER.encode(summary) + "\n\nSee run.log and case.json files for measured usage, counts, "
            "verbatim producer reasons and both solver outcomes. No superiority is presumed.\n\n" +
            "NOT ESTABLISHED:\n" + "\n".join("- " + text for text in NOT_ESTABLISHED) + "\n")
    (output / "memo.txt").write_text(memo, encoding="utf-8")
    manifest = {"version": VERSION, "attempt": "R0", "harness_sha256": pinned, "summary": summary,
                "caps": CAPS, "sources": before, "artifacts": inventory(output),
                "environment": {"python": sys.version, "platform": platform.platform()},
                "r0_limitations": "Exclusive directory admission only; the owner enforces one directory per pinned hash. "
                                  "A killed evaluator cannot supply an unreturned response; missing files are failures."}
    save(output / "manifest.json", manifest)
    manifest_sha = file_digest(output / "manifest.json")
    (output / "manifest.sha256").write_text(manifest_sha + "  manifest.json\n", encoding="ascii")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true", help="Read-only construction/static checks; zero evaluator calls")
    mode.add_argument("--run-r0", action="store_true", help="Owner-only admitted batch after review; consumes the attempt")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-harness-sha256")
    args = parser.parse_args()
    if args.self_test:
        require(args.output_dir is None and args.expected_harness_sha256 is None, "Self-test writes no artifacts")
        contracts, cases = catalogs(), case_family()
        check_family(cases, contracts)
        budget = budget_comparability(cases)
        # Control-only reporting checks: no solver results, loads, hashes or benchmark data are fabricated.
        control = {"status": "COMPUTED_EXPERIMENTAL", "rotor_state": None, "section_solve_result_count": 0,
                   "converged_annuli": 0, "section_states": [], "reasons": [], "totals": None}
        refusal = {**control, "status": "MODEL_INAPPLICABLE", "reasons": ["SELF_TEST_CONTROL_ONLY"]}
        for refused_by in ("legacy", "stable"):
            values = {solver: refusal if solver == refused_by else control for solver in ("legacy", "stable")}
            result = compare(values)
            require(result["kind_difference"] and result["one_contract_only_admission_refusal"], "Refusal KIND lost")
            require(result["admission_refusal_solvers"] == [refused_by], "Refusal solver lost")
        print(BUDGET_COMPARABILITY, flush=True)
        print(ENCODER.encode({"self_test": "PASSED", "version": VERSION, "cases": len(cases),
                              "base_cases": 12, "stress_cases": 12, "schema_checks": 48,
                              "budget_comparability": budget, "admission_refusal_reporting_checks": 2,
                              "revision_note": REVISION_NOTE,
                              "public_evaluator_calls": 0, "writes": 0, "caps": CAPS,
                              "preflight_scope": "Independent static contract checks using public catalogs; "
                                                 "no private preflight or numerical admission claimed.",
                              "harness_sha256": file_digest(Path(__file__).resolve())}))
        return 0
    require(args.output_dir is not None and args.expected_harness_sha256 is not None,
            "R0 requires --output-dir and --expected-harness-sha256 from owner review")
    return run_r0(args.output_dir.absolute(), args.expected_harness_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
