"""Eight-rotor static yaw-authority verification.

No dynamics, rotor interference or physical qualification.
"""
import json
import numpy as np
from pathlib import Path
from scipy.optimize import linprog

folder = Path(".backend/integrated-eight-rotor")

data = json.loads(
    (folder / "equilibrium_verification.json").read_text()
)

spin = np.array([1, -1, 1, -1, 1, -1, 1, -1])
kq = 0.02  # Assumed N.m yaw torque per N thrust.

def yaw_range(case, capacity, failed=None):
    rotors = case["rotors"]
    x = np.array([r["x_m"] for r in rotors])
    y = np.array([r["y_m"] for r in rotors])
    cg_x, cg_y = case["cg_m"]
    weight = case["weight_n"]

    A = np.vstack([
        np.ones(8),
        y - cg_y,
        -(x - cg_x)
    ])

    b = np.array([weight, 0.0, 0.0])
    yaw = spin * kq

    bounds = [(0.0, capacity)] * 8

    if failed is not None:
        bounds[failed - 1] = (0.0, 0.0)

    low = linprog(
        yaw, A_eq=A, b_eq=b,
        bounds=bounds, method="highs"
    )
    high = linprog(
        -yaw, A_eq=A, b_eq=b,
        bounds=bounds, method="highs"
    )

    if not low.success or not high.success:
        return {
            "feasible": False,
            "reason": "Force/roll/pitch constraints infeasible"
        }

    minimum = float(yaw @ low.x)
    maximum = float(yaw @ high.x)

    return {
        "feasible": True,
        "min_yaw_nm": minimum,
        "max_yaw_nm": maximum,
        "zero_yaw_available": minimum <= 1e-7
                              and maximum >= -1e-7,
        "bidirectional_yaw_authority": (
            minimum < -1e-5 and maximum > 1e-5
        )
    }

results = {}

for capacity in (150.0, 200.0):
    for failed in (None, *range(1, 9)):
        label = (
            f"capacity_{int(capacity)}_normal"
            if failed is None
            else f"capacity_{int(capacity)}_failed_{failed}"
        )

        result = yaw_range(
            data["centered_cg"], capacity, failed
        )
        results[label] = result

        print("\n", label)
        print("Static force/roll/pitch feasible:",
              result["feasible"])

        if result["feasible"]:
            print(
                "Achievable yaw range (N.m):",
                round(result["min_yaw_nm"], 4),
                "to",
                round(result["max_yaw_nm"], 4)
            )
            print(
                "Zero yaw achievable:",
                result["zero_yaw_available"]
            )
            print(
                "Bidirectional yaw authority:",
                result["bidirectional_yaw_authority"]
            )

destination = folder / "yaw_authority_verification.json"
destination.write_text(json.dumps({
    "results": results,
    "assumed_torque_thrust_ratio_m": kq,
    "qualification": "STATIC_SOFTWARE_VERIFICATION_ONLY",
    "physical_validation": "NOT_ESTABLISHED"
}, indent=2))

print("\nSaved:", destination)
print("Yaw authority analysis completed")
