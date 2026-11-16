"""Offset-CG and single-rotor-failure verification.

Static mechanics only. Does not establish flight capability.
"""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import linprog

folder = Path(".backend/integrated-eight-rotor")
data = json.loads(
    (folder / "equilibrium_verification.json").read_text()
)

case = data["offset_cg"]
rotors = case["rotors"]
cx, cy = case["cg_m"]

x = np.array([r["x_m"] - cx for r in rotors])
y = np.array([r["y_m"] - cy for r in rotors])

spin = np.array([1, -1, 1, -1, 1, -1, 1, -1])
kq = 0.02
capacity = 200.0

A = np.vstack([np.ones(8), y, -x, spin*kq])

commands = {
    "hover": (0, 0, 0),
    "roll": (30, 0, 0),
    "roll_pitch": (30, 30, 0),
    "combined_positive": (30, 30, 1),
    "combined_negative": (-30, -30, -1),
}

def solve(command, failed):
    target = np.array([case["weight_n"], *command])
    caps = np.full(8, capacity)

    if failed is not None:
        caps[failed-1] = 0.0

    objective = np.zeros(9)
    objective[8] = 1.0

    inequalities = np.zeros((8, 9))
    for i in range(8):
        inequalities[i, i] = 1.0
        inequalities[i, 8] = -caps[i]

    result = linprog(
        objective,
        A_ub=inequalities,
        b_ub=np.zeros(8),
        A_eq=np.column_stack([A, np.zeros(4)]),
        b_eq=target,
        bounds=[(0, None)]*9,
        method="highs",
    )

    if not result.success:
        return {"solved": False, "within_limits": False}

    residual = A @ result.x[:8] - target
    assert np.max(np.abs(residual)) < 1e-6

    return {
        "solved": True,
        "within_limits": bool(result.x[8] <= 1 + 1e-8),
        "utilization_percent": float(result.x[8] * 100),
        "thrusts_n": result.x[:8].tolist(),
    }

results = {}
for failed in (None, *range(1, 9)):
    label = "normal" if failed is None else f"failed_{failed}"
    tests = {name: solve(cmd, failed)
             for name, cmd in commands.items()}
    passing = sum(v["within_limits"] for v in tests.values())
    peak = max(
        (v["utilization_percent"]
         for v in tests.values() if v["solved"]),
        default=None
    )
    results[label] = {
        "passing_commands": passing,
        "tests": tests,
        "peak_utilization_percent": peak
    }
    print(
        f"{label:10s} {passing}/5 within limits | "
        f"peak utilization: "
        f"{peak:.2f}%" if peak is not None
        else f"{label:10s} no solution"
    )

output = folder / "offset_failure_verification.json"
output.write_text(json.dumps({
    "results": results,
    "capacity_n": capacity,
    "cg_m": case["cg_m"],
    "qualification": "STATIC_SOFTWARE_VERIFICATION_ONLY",
    "physical_validation": "NOT_ESTABLISHED"
}, indent=2))

print("\nCompleted 45 offset-CG calculations")
print("Saved:", output)
