"""PHYSIMESH: Eight-rotor static four-axis allocation.

Verifies equilibrium of vertical force, roll, pitch and yaw.
Illustrative reaction torque and spin configuration only.
Not a flight dynamics or physical validation model.
"""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import linprog

folder = Path(".backend/integrated-eight-rotor")
source = json.loads(
    (folder / "equilibrium_verification.json").read_text()
)

ROTOR_COUNT = 8
TORQUE_THRUST_RATIO_M = 0.02
SPIN_DIRECTIONS = [1, -1, 1, -1, 1, -1, 1, -1]

def allocate(case, capacity, failed=None):
    rotors = case["rotors"]
    assert len(rotors) == ROTOR_COUNT

    weight = case["weight_n"]
    cg_x, cg_y = case["cg_m"]

    x = np.array([r["x_m"] for r in rotors])
    y = np.array([r["y_m"] for r in rotors])
    spin = np.array(SPIN_DIRECTIONS)

    capacities = np.full(ROTOR_COUNT, capacity)
    if failed is not None:
        capacities[failed - 1] = 0.0

    # Force, roll moment, pitch moment, yaw reaction moment.
    A = np.vstack([
        np.ones(ROTOR_COUNT),
        y - cg_y,
        -(x - cg_x),
        spin * TORQUE_THRUST_RATIO_M
    ])

    target = np.array([weight, 0.0, 0.0, 0.0])

    # Minimize maximum utilization u:
    # T_i <= capacity_i * u.
    c = np.zeros(ROTOR_COUNT + 1)
    c[-1] = 1.0

    A_ub = np.zeros((ROTOR_COUNT, ROTOR_COUNT + 1))
    for i in range(ROTOR_COUNT):
        A_ub[i, i] = 1.0
        A_ub[i, -1] = -capacities[i]

    result = linprog(
        c,
        A_ub=A_ub,
        b_ub=np.zeros(ROTOR_COUNT),
        A_eq=np.column_stack([A, np.zeros(4)]),
        b_eq=target,
        bounds=[(0, None)] * (ROTOR_COUNT + 1),
        method="highs"
    )

    if not result.success:
        return {
            "solved": False,
            "within_capacity": False,
            "reason": result.message
        }

    thrust = result.x[:ROTOR_COUNT]
    utilization = float(result.x[-1])
    residual = A @ thrust - target

    assert np.max(np.abs(residual)) < 1e-6

    if failed is not None:
        assert abs(thrust[failed - 1]) < 1e-7

    return {
        "solved": True,
        "within_capacity": utilization <= 1.0 + 1e-8,
        "maximum_utilization_percent": utilization * 100,
        "thrust_n": thrust.tolist(),
        "force_residual_n": float(residual[0]),
        "roll_residual_nm": float(residual[1]),
        "pitch_residual_nm": float(residual[2]),
        "yaw_residual_nm": float(residual[3]),
        "failed_rotor": failed
    }

cases = [
    ("centered_150", "centered_cg", 150.0, None),
    ("offset_150", "offset_cg", 150.0, None),
]
cases.extend(
    (f"failure_rotor_{i}", "centered_cg", 150.0, i)
    for i in range(1, 9)
)

results = {}

for label, name, capacity, failed in cases:
    result = allocate(source[name], capacity, failed)
    results[label] = result

    print("\nCASE:", label)
    print("Optimizer solved:", result["solved"])
    print("Within capacity:", result["within_capacity"])

    if result["solved"]:
        print(
            "Minimum max utilization:",
            round(result["maximum_utilization_percent"], 3),
            "%"
        )
        print(
            "Thrust (N):",
            [round(v, 3) for v in result["thrust_n"]]
        )
        print(
            "Yaw residual (N.m):",
            result["yaw_residual_nm"]
        )

# Centred, unfailed and symmetrically spinning reference.
assert results["centered_150"]["within_capacity"]
assert abs(
    results["centered_150"]["maximum_utilization_percent"]
    - 100 * source["centered_cg"]["weight_n"] / (8 * 150)
) < 1e-6

destination = folder / "four_axis_verification.json"
destination.write_text(json.dumps({
    "model": "static_four_axis_minimax",
    "spin_directions": SPIN_DIRECTIONS,
    "torque_thrust_ratio_m": TORQUE_THRUST_RATIO_M,
    "results": results,
    "qualification": "ANALYTICAL_SOFTWARE_VERIFICATION_ONLY",
    "physical_validation": "NOT_ESTABLISHED"
}, indent=2))

print("\nPASS: Four-axis numerical checks completed")
print("Saved:", destination)
print("Flight qualification: NOT ESTABLISHED")
