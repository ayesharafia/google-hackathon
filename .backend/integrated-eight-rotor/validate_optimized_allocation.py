"""PHYSIMESH: Minimax eight-rotor static allocation.

Software verification only. No aerodynamic or flight qualification.
"""
import json
from pathlib import Path
from scipy.optimize import linprog

folder = Path(".backend/integrated-eight-rotor")
source = json.loads(
    (folder / "equilibrium_verification.json").read_text()
)

def optimize(case, capacity_n, failed_rotor=None):
    rotors = case["rotors"]
    n = len(rotors)
    assert n == 8

    x = [r["x_m"] for r in rotors]
    y = [r["y_m"] for r in rotors]
    cg_x, cg_y = case["cg_m"]
    weight = case["weight_n"]

    capacities = [float(capacity_n)] * n
    if failed_rotor is not None:
        capacities[failed_rotor - 1] = 0.0

    # Variables are eight thrust values and a maximum
    # rotor utilization u. Minimize u.
    objective = [0.0] * n + [1.0]

    A_eq = [
        [1.0] * n + [0.0],
        x + [0.0],
        y + [0.0]
    ]
    b_eq = [
        weight,
        weight * cg_x,
        weight * cg_y
    ]

    # T_i <= capacity_i * u.
    A_ub = []
    for i in range(n):
        row = [0.0] * (n + 1)
        row[i] = 1.0
        row[-1] = -capacities[i]
        A_ub.append(row)

    result = linprog(
        objective,
        A_ub=A_ub,
        b_ub=[0.0] * n,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=[(0.0, None)] * (n + 1),
        method="highs",
    )

    if not result.success:
        return {
            "solved": False,
            "within_capacity": False,
            "reason": result.message
        }

    thrusts = result.x[:n].tolist()
    utilization = float(result.x[-1])

    residuals = [
        sum(thrusts) - weight,
        sum(x[i] * thrusts[i] for i in range(n))
        - weight * cg_x,
        sum(y[i] * thrusts[i] for i in range(n))
        - weight * cg_y
    ]

    assert max(abs(v) for v in residuals) < 1e-6

    return {
        "solved": True,
        "within_capacity": utilization <= 1.0 + 1e-8,
        "maximum_utilization_percent": utilization * 100,
        "thrusts_n": thrusts,
        "residuals": residuals
    }

cases = [
    ("centered_130", "centered_cg", 130.0, None),
    ("centered_150", "centered_cg", 150.0, None),
    ("offset_130", "offset_cg", 130.0, None),
    ("offset_150", "offset_cg", 150.0, None),
    ("rotor_1_failed", "centered_cg", 150.0, 1),
]

outputs = {}

for label, case_name, capacity, failure in cases:
    result = optimize(
        source[case_name], capacity, failure
    )
    outputs[label] = result

    print("\nCASE:", label)
    print("Optimizer solved:", result["solved"])
    print("Within rotor capacities:",
          result["within_capacity"])

    if result["solved"]:
        print(
            "Minimum achievable maximum utilization:",
            round(result["maximum_utilization_percent"], 3),
            "%"
        )
        print(
            "Thrust allocation (N):",
            [round(t, 3)
             for t in result["thrusts_n"]]
        )
        print(
            "Maximum equilibrium residual:",
            max(abs(v) for v in result["residuals"])
        )

assert outputs["centered_130"]["within_capacity"]
assert outputs["centered_150"]["within_capacity"]
assert not outputs["offset_130"]["within_capacity"]
assert outputs["offset_150"]["within_capacity"]

# For a centered CG, equal thrust is minimax-optimal.
expected_u = source["centered_cg"]["weight_n"] / (8 * 150)
assert abs(
    outputs["centered_150"]["maximum_utilization_percent"]
    - 100 * expected_u
) < 1e-6

destination = folder / "optimized_allocation_verification.json"
destination.write_text(json.dumps({
    "results": outputs,
    "qualification": "STATIC_MECHANICS_ONLY",
    "yaw_validation": "NOT_ESTABLISHED",
    "physical_validation": "NOT_ESTABLISHED"
}, indent=2))

print("\nPASS: Optimized allocation checks completed")
print("Saved:", destination)
