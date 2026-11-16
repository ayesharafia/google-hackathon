"""Full single-rotor-failure coupled-control verification."""
import contextlib
import io
import json
import runpy
from pathlib import Path

folder = Path(".backend/integrated-eight-rotor")
script = folder / "validate_coupled_control.py"

# Reuse the already-tested allocator without its console output.
with contextlib.redirect_stdout(io.StringIO()):
    module = runpy.run_path(str(script))

solve = module["solve"]
commands = module["commands"]

results = {}
count = 0

for capacity in (150, 200):
    print(f"\nCAPACITY: {capacity} N")
    print(
        f"{'Failed':>7} {'Passed':>8} "
        f"{'Tests':>8} {'Peak use':>12}"
    )
    print("-" * 42)

    for failed in range(1, 9):
        cases = {}
        utilizations = []

        for name, command in commands.items():
            result = solve(command, capacity, failed)
            cases[name] = result
            count += 1

            if result["solved"]:
                utilizations.append(
                    result["maximum_utilization_percent"]
                )

        passed = sum(
            bool(r.get("within_limits", False))
            for r in cases.values()
        )

        peak = max(utilizations) if utilizations else None

        print(
            f"{failed:7d} "
            f"{passed:8d} "
            f"{len(cases):8d} "
            f"{peak:11.2f}%"
            if peak is not None
            else f"{failed:7d} {passed:8d} "
                 f"{len(cases):8d} N/A"
        )

        results[f"{capacity}_failed_{failed}"] = {
            "passed": passed,
            "total": len(cases),
            "peak_utilization_percent": peak,
            "commands": cases
        }

assert count == 80

destination = folder / "all_failures_verification.json"
destination.write_text(json.dumps({
    "test_count": count,
    "results": results,
    "qualification": "STATIC_SOFTWARE_VERIFICATION_ONLY",
    "rotor_thrust_validation": "UNVALIDATED",
    "dynamic_stability": "NOT_ESTABLISHED",
    "flight_qualification": "NOT_ESTABLISHED"
}, indent=2))

print("\nTotal calculations:", count)
print("Saved:", destination)
print("Physical validation: NOT ESTABLISHED")
