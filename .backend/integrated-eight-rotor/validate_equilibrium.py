"""PHYSIMESH eight-rotor static equilibrium verification.

Independent of rotor aerodynamic predictions.
Illustrative geometry and mass; not flight qualification.
"""
import json
import math
from pathlib import Path

N = 8
G = 9.80665

# Software verification fixture, not a real drone specification.
TOTAL_MASS_KG = 100.0
ARM_RADIUS_M = 1.5

def rotor_positions(radius):
    return [
        (
            radius * math.cos(2 * math.pi * i / N),
            radius * math.sin(2 * math.pi * i / N)
        )
        for i in range(N)
    ]

def allocate_hover(mass, arm_radius, cg_x=0.0, cg_y=0.0):
    if mass <= 0 or arm_radius <= 0:
        raise ValueError("Mass and arm radius must be positive")

    weight = mass * G
    positions = rotor_positions(arm_radius)

    # Minimum-deviation solution for a regular symmetric octocopter.
    # Assumes vertical, independently commanded rotor thrust.
    thrusts = [
        weight / N +
        weight * (cg_x * x + cg_y * y) /
        (4 * arm_radius ** 2)
        for x, y in positions
    ]

    if any(t < 0 for t in thrusts):
        raise ValueError("Required negative rotor thrust")

    total_thrust = sum(thrusts)
    roll_moment = sum(
        (y - cg_y) * t
        for (x, y), t in zip(positions, thrusts)
    )
    pitch_moment = sum(
        -(x - cg_x) * t
        for (x, y), t in zip(positions, thrusts)
    )

    result = {
        "mass_kg": mass,
        "weight_n": weight,
        "arm_radius_m": arm_radius,
        "cg_m": [cg_x, cg_y],
        "rotors": [
            {
                "id": i + 1,
                "x_m": x,
                "y_m": y,
                "required_thrust_n": t
            }
            for i, ((x, y), t)
            in enumerate(zip(positions, thrusts))
        ],
        "force_residual_n": total_thrust - weight,
        "roll_moment_residual_nm": roll_moment,
        "pitch_moment_residual_nm": pitch_moment,
        "yaw_equilibrium": "NOT_EVALUATED",
        "thrust_capacity": "NOT_EVALUATED",
        "qualification": "ANALYTICAL_SOFTWARE_VERIFICATION_ONLY"
    }

    tolerance_force = 1e-9 * max(1.0, weight)
    tolerance_moment = tolerance_force * arm_radius

    assert abs(result["force_residual_n"]) < tolerance_force
    assert abs(roll_moment) < tolerance_moment
    assert abs(pitch_moment) < tolerance_moment

    return result

def show(title, result):
    print("\n" + title)
    print("Required total thrust:", round(result["weight_n"], 3), "N")
    print("Rotor thrust allocations:")
    for rotor in result["rotors"]:
        print(
            f"  Rotor {rotor['id']}: "
            f"{rotor['required_thrust_n']:.4f} N"
        )
    print("Force residual:", result["force_residual_n"], "N")
    print("Roll residual:", result["roll_moment_residual_nm"], "N.m")
    print("Pitch residual:", result["pitch_moment_residual_nm"], "N.m")

centered = allocate_hover(
    TOTAL_MASS_KG, ARM_RADIUS_M
)
offset = allocate_hover(
    TOTAL_MASS_KG, ARM_RADIUS_M,
    cg_x=0.10, cg_y=-0.05
)

# Analytic reference: identical loading for centered CG.
expected = TOTAL_MASS_KG * G / N
assert all(
    math.isclose(
        r["required_thrust_n"], expected,
        rel_tol=1e-12
    )
    for r in centered["rotors"]
)

# Offset CG must produce a different thrust distribution.
assert max(
    r["required_thrust_n"] for r in offset["rotors"]
) > expected
assert min(
    r["required_thrust_n"] for r in offset["rotors"]
) < expected

show("TEST 1: CENTERED CG", centered)
show("TEST 2: OFFSET CG", offset)

output = {
    "centered_cg": centered,
    "offset_cg": offset,
    "status": "ANALYTICAL_TESTS_PASSED"
}

destination = Path(
    ".backend/integrated-eight-rotor/"
    "equilibrium_verification.json"
)
destination.write_text(json.dumps(output, indent=2))

print("\nPASS: Eight-rotor static equilibrium tests")
print("Saved:", destination)
print("Physical validation: NOT ESTABLISHED")
