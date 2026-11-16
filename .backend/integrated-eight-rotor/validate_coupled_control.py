"""PHYSIMESH combined four-axis static control allocation.

Software verification only; no flight qualification.
"""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import linprog

folder = Path(".backend/integrated-eight-rotor")
data = json.loads(
    (folder / "equilibrium_verification.json").read_text()
)

case = data["centered_cg"]
rotors = case["rotors"]

x = np.array([r["x_m"] for r in rotors])
y = np.array([r["y_m"] for r in rotors])

spin = np.array([1, -1, 1, -1, 1, -1, 1, -1])
kq = 0.02

A = np.vstack([
    np.ones(8),
    y,
    -x,
    spin * kq
])

commands = {
    "hover": (0, 0, 0),
    "roll": (30, 0, 0),
    "roll_pitch": (30, 30, 0),
    "combined_positive": (30, 30, 1),
    "combined_negative": (-30, -30, -1)
}

def solve(command, capacity, failed=None):
    roll, pitch, yaw = command
    target = np.array([
        case["weight_n"], roll, pitch, yaw
    ])

    caps = np.full(8, float(capacity))
    if failed is not None:
        caps[failed - 1] = 0

    # Variables: T1...T8, maximum utilization u.
    c = np.zeros(9)
    c[-1] = 1.0

    Aub = np.zeros((8, 9))
    for i in range(8):
        Aub[i, i] = 1.0
        Aub[i, -1] = -caps[i]

    solution = linprog(
        c,
        A_ub=Aub,
        b_ub=np.zeros(8),
        A_eq=np.column_stack([A, np.zeros(4)]),
        b_eq=target,
        bounds=[(0, None)] * 9,
        method="highs"
    )

    if not solution.success:
        return {
            "solved": False,
            "within_limits": False,
            "reason": solution.message
        }

    thrust = solution.x[:8]
    residual = A @ thrust - target
    assert max(abs(v) for v in residual) < 1e-6

    u = float(solution.x[-1])

    return {
        "solved": True,
        "within_limits": u <= 1.0 + 1e-8,
        "maximum_utilization_percent": 100*u,
        "thrusts_n": thrust.tolist(),
        "maximum_residual": float(max(abs(v) for v in residual))
    }

results = {}

for capacity in (150, 200):
    for failed in (None, 1, 2):
        condition = (
            "normal" if failed is None
            else f"failed_{failed}"
        )
        print(f"\nCAPACITY {capacity} N | {condition}")

        for name, command in commands.items():
            result = solve(command, capacity, failed)
            key = f"{capacity}_{condition}_{name}"
            results[key] = result

            if not result["solved"]:
                status = "NO MATHEMATICAL SOLUTION"
            elif result["within_limits"]:
                status = "WITHIN LIMITS"
            else:
                status = "EXCEEDS LIMITS"

            utilization = (
                f"{result['maximum_utilization_percent']:.2f}%"
                if result["solved"] else "N/A"
            )

            print(
                f"{name:20s} "
                f"{status:25s} "
                f"utilization={utilization}"
            )

destination = folder / "coupled_control_verification.json"
destination.write_text(json.dumps({
    "results": results,
    "qualification": "STATIC_COMBINED_CONTROL_ONLY",
    "rotor_physics": "UNVALIDATED",
    "dynamic_stability": "NOT_EVALUATED",
    "physical_validation": "NOT_ESTABLISHED"
}, indent=2))

assert results["150_normal_hover"]["within_limits"]
assert results["200_normal_hover"]["within_limits"]
assert not results["150_failed_1_hover"]["within_limits"]

print("\nPASS: Coupled control calculations completed")
print("Saved:", destination)
