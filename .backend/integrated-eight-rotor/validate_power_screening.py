import json
import math
from pathlib import Path

folder = Path(".backend/integrated-eight-rotor")

source = json.loads(
    (folder / "offset_failure_verification.json").read_text()
)

# Illustrative values, not validated aircraft specifications
rho = 1.225
rotor_radius = 0.75
disk_area = math.pi * rotor_radius**2

def ideal_power(thrust):
    if thrust < -1e-8:
        raise ValueError("Negative thrust unsupported")
    return max(0.0, thrust)**1.5 / math.sqrt(
        2 * rho * disk_area
    )

results = {}

print("\nPHYSIMESH — IDEAL PROPULSION POWER SCREENING")
print("Assumed rotor radius:", rotor_radius, "m")
print("Assumed air density:", rho, "kg/m3")
print()
print(
    f"{'Scenario':12s} "
    f"{'Peak thrust':>12s} "
    f"{'Ideal power':>14s}"
)
print("-" * 43)

for scenario, record in source["results"].items():
    highest_power = -1.0
    governing_command = None
    governing_thrusts = None

    for command, result in record["tests"].items():
        if not result.get("within_limits", False):
            continue

        thrusts = result["thrusts_n"]
        total_power = sum(ideal_power(t) for t in thrusts)

        if total_power > highest_power:
            highest_power = total_power
            governing_command = command
            governing_thrusts = thrusts

    if governing_thrusts is None:
        raise RuntimeError(
            f"No feasible command for {scenario}"
        )

    peak_thrust = max(governing_thrusts)

    results[scenario] = {
        "governing_command": governing_command,
        "peak_thrust_n": peak_thrust,
        "total_ideal_power_w": highest_power,
        "individual_rotor_power_w": [
            ideal_power(t) for t in governing_thrusts
        ]
    }

    print(
        f"{scenario:12s} "
        f"{peak_thrust:12.2f} "
        f"{highest_power:14.2f} W"
    )

destination = folder / "power_screening.json"

destination.write_text(json.dumps({
    "results": results,
    "assumed_radius_m": rotor_radius,
    "assumed_density_kg_m3": rho,
    "model": "ideal_isolated_actuator_disk",
    "motor_power": "NOT_EVALUATED",
    "electrical_power": "NOT_EVALUATED",
    "torque": "NOT_EVALUATED",
    "physical_validation": "NOT_ESTABLISHED"
}, indent=2))

print("\nSaved:", destination)
print("Status: IDEALIZED POWER SCREENING ONLY")
