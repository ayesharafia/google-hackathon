import json
import math
from pathlib import Path

source = Path(
    ".backend/integrated-eight-rotor/"
    "power_screening_geometry_corrected.json"
)

data = json.loads(source.read_text())

radius = data["geometry_corrected_candidate_radius_m"]
original_radius = data["assumed_radius_m"]
scale = original_radius / radius

assert math.isclose(
    scale, data["geometry_corrected_power_scale"]
)

fm = 0.70
motor_efficiency = 0.90
rpm = 3000
omega = 2 * math.pi * rpm / 60
margin = 1.20

print("PHYSIMESH PROPULSION ENVELOPE")
print("Status: NUMERICAL SCREENING ONLY\n")

max_total = 0
max_individual = 0
max_shaft = 0
max_torque = 0
governing = None

for scenario, result in data["results"].items():
    original = result["individual_rotor_power_w"]

    assert len(original) == 8
    assert math.isclose(
        sum(original),
        result["total_ideal_power_w"],
        rel_tol=1e-9
    )

    shaft = [p * scale / fm for p in original]
    electrical = [p / motor_efficiency for p in shaft]
    torque = [p / omega for p in shaft]

    total = sum(electrical)

    if total > max_total:
        max_total = total
        governing = scenario

    max_individual = max(max_individual, *electrical)
    max_shaft = max(max_shaft, *shaft)
    max_torque = max(max_torque, *torque)

assert len(data["results"]) == 9

requirements = {
    "governing_scenario": governing,
    "scenario_count": len(data["results"]),
    "assumed_rotor_radius_m": radius,
    "assumed_rpm": rpm,
    "assumed_figure_of_merit": fm,
    "assumed_motor_efficiency": motor_efficiency,
    "provisional_margin": margin,
    "system_electrical_power_w": max_total,
    "motor_electrical_power_w": max_individual,
    "motor_shaft_power_w": max_shaft,
    "motor_shaft_torque_nm": max_torque,
    "screening_targets": {
        "system_power_w": max_total * margin,
        "motor_electrical_power_w": max_individual * margin,
        "motor_shaft_power_w": max_shaft * margin,
        "motor_torque_nm": max_torque * margin
    },
    "hardware_limits_verified": False,
    "physical_validation": "NOT_ESTABLISHED"
}

output = Path(
    "docs/validation/eight_rotor/"
    "propulsion_envelope.json"
)

output.write_text(json.dumps(requirements, indent=2) + "\n")

print("Governing case:", governing)
print("System electrical:", round(max_total / 1000, 3), "kW")
print("Individual electrical:", round(max_individual / 1000, 3), "kW")
print("Individual shaft:", round(max_shaft / 1000, 3), "kW")
print("Individual torque:", round(max_torque, 3), "Nm")
print("Provisional margin:", margin)
print("Saved:", output)
print("Hardware validation: NOT ESTABLISHED")
