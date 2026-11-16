"""Eight-rotor bounded static allocation feasibility test."""
import itertools
import json
import math
from pathlib import Path

folder = Path(".backend/integrated-eight-rotor")
source = json.loads(
    (folder / "equilibrium_verification.json").read_text()
)

def determinant(a):
    return (
        a[0][0]*(a[1][1]*a[2][2]-a[1][2]*a[2][1])
        -a[0][1]*(a[1][0]*a[2][2]-a[1][2]*a[2][0])
        +a[0][2]*(a[1][0]*a[2][1]-a[1][1]*a[2][0])
    )

def solve3(a, b):
    d = determinant(a)
    if abs(d) < 1e-10:
        return None

    answer = []
    for col in range(3):
        matrix = [row[:] for row in a]
        for j in range(3):
            matrix[j][col] = b[j]
        answer.append(determinant(matrix)/d)
    return answer

def allocate(case, capacity):
    rotors = case["rotors"]
    weight = case["weight_n"]
    cg_x, cg_y = case["cg_m"]

    positions = [(r["x_m"], r["y_m"]) for r in rotors]
    target = (weight, weight*cg_x, weight*cg_y)

    # A feasible bounded linear system has a vertex with
    # at most three non-bound variables when A has rank 3.
    for free in itertools.combinations(range(8), 3):
        fixed = [i for i in range(8) if i not in free]

        a = [
            [1.0 for i in free],
            [positions[i][0] for i in free],
            [positions[i][1] for i in free]
        ]

        for bits in itertools.product((0.0, capacity), repeat=5):
            thrusts = [0.0]*8

            for i, value in zip(fixed, bits):
                thrusts[i] = value

            b = [
                target[0] - sum(thrusts),
                target[1] - sum(
                    positions[i][0]*thrusts[i]
                    for i in range(8)
                ),
                target[2] - sum(
                    positions[i][1]*thrusts[i]
                    for i in range(8)
                )
            ]

            solution = solve3(a, b)
            if solution is None:
                continue

            if any(
                t < -1e-7 or t > capacity + 1e-7
                for t in solution
            ):
                continue

            for i, t in zip(free, solution):
                thrusts[i] = t

            residuals = [
                sum(thrusts)-target[0],
                sum(positions[i][0]*thrusts[i]
                    for i in range(8))-target[1],
                sum(positions[i][1]*thrusts[i]
                    for i in range(8))-target[2]
            ]

            if max(abs(v) for v in residuals) < 1e-6:
                return {
                    "feasible": True,
                    "thrusts_n": thrusts,
                    "residuals": residuals
                }

    return {"feasible": False, "thrusts_n": None}

results = []

for case_name in ("centered_cg", "offset_cg"):
    case = source[case_name]
    print("\nCASE:", case_name.upper())

    for capacity in (120.0, 130.0, 150.0):
        result = allocate(case, capacity)

        status = "FEASIBLE" if result["feasible"] else "INFEASIBLE"
        print(f"Capacity {capacity:.0f} N: {status}")

        if result["feasible"]:
            print(
                "  Allocated thrusts (N):",
                [round(t, 2) for t in result["thrusts_n"]]
            )
            print(
                "  Maximum residual:",
                max(abs(v) for v in result["residuals"])
            )

        results.append({
            "case": case_name,
            "capacity_n": capacity,
            **result
        })

expected = [False, True, True, False, False, True]
assert [r["feasible"] for r in results] == expected

destination = folder / "constrained_allocation_verification.json"
destination.write_text(json.dumps({
    "results": results,
    "status": "STATIC_FEASIBILITY_VERIFICATION",
    "physical_validation": "NOT_ESTABLISHED",
    "notes": [
        "Uses hypothetical rotor capacities",
        "Checks vertical force and roll/pitch equilibrium",
        "Does not check yaw, dynamics or motor physics",
        "Feasible allocations are not necessarily optimal"
    ]
}, indent=2))

print("\nPASS: Constrained allocation feasibility tests")
print("Saved:", destination)
