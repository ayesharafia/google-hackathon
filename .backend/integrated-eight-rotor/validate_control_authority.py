"""PHYSIMESH: static independent-axis control authority.

Illustrative geometry, thrust limits, and yaw torque law.
Not physical or dynamic flight validation.
"""
import json
import numpy as np
from pathlib import Path
from scipy.optimize import linprog

folder = Path(".backend/integrated-eight-rotor")
data = json.loads(
    (folder / "equilibrium_verification.json").read_text()
)

spin = np.array([1,-1,1,-1,1,-1,1,-1])
kq = 0.02

def authority(case, capacity, failed=None):
    rotors = case["rotors"]
    x = np.array([r["x_m"] for r in rotors])
    y = np.array([r["y_m"] for r in rotors])
    cx, cy = case["cg_m"]

    A = np.vstack([
        np.ones(8),
        y - cy,
        -(x - cx),
        spin * kq
    ])
    weight = case["weight_n"]

    bounds = [(0.0, capacity)] * 8

    if failed is not None:
        bounds[failed - 1] = (0.0, 0.0)

    output = {}

    for axis, index in [
        ("roll", 1),
        ("pitch", 2),
        ("yaw", 3)
    ]:
        # Maintain weight and zero moments on the
        # other two axes.
        constrained = [i for i in range(4) if i != index]
        Aeq = A[constrained]
        beq = np.array([
            weight if i == 0 else 0.0
            for i in constrained
        ])

        low = linprog(
            A[index],
            A_eq=Aeq, b_eq=beq,
            bounds=bounds, method="highs"
        )
        high = linprog(
            -A[index],
            A_eq=Aeq, b_eq=beq,
            bounds=bounds, method="highs"
        )

        if not low.success or not high.success:
            output[axis] = {"feasible": False}
            continue

        for solution in (low, high):
            residual = Aeq @ solution.x - beq
            assert np.max(np.abs(residual)) < 1e-6

        minimum = float(A[index] @ low.x)
        maximum = float(A[index] @ high.x)

        output[axis] = {
            "feasible": True,
            "minimum_nm": minimum,
            "maximum_nm": maximum,
            "bidirectional": (
                minimum < -1e-6 and maximum > 1e-6
            )
        }

    return output

cases = [
    ("normal_150", 150.0, None),
    ("normal_200", 200.0, None),
] + [
    (f"failed_{i}_200", 200.0, i)
    for i in range(1, 9)
]

results = {}

for label, capacity, failed in cases:
    result = authority(
        data["centered_cg"], capacity, failed
    )
    results[label] = result

    print("\nCASE:", label)

    for axis in ("roll", "pitch", "yaw"):
        value = result[axis]

        if not value["feasible"]:
            print(axis, ": INFEASIBLE")
        else:
            print(
                f"{axis:5s}: "
                f"{value['minimum_nm']:9.3f} to "
                f"{value['maximum_nm']:9.3f} N.m "
                f"| bidirectional={value['bidirectional']}"
            )

assert all(
    results["normal_150"][axis]["bidirectional"]
    for axis in ("roll", "pitch", "yaw")
)

destination = folder / "control_authority_verification.json"
destination.write_text(json.dumps({
    "results": results,
    "qualification": "STATIC_AXIS_AUTHORITY_ONLY",
    "aerodynamic_validation": "NOT_ESTABLISHED",
    "dynamic_stability": "NOT_EVALUATED",
    "physical_validation": "NOT_ESTABLISHED"
}, indent=2))

print("\nPASS: Static control-authority analysis completed")
print("Saved:", destination)
