"""PHYSIMESH: Eight-rotor coplanar spacing audit.

Illustrative engineering geometry; not structural validation.
"""
import json
import math
from pathlib import Path

folder = Path(".backend/integrated-eight-rotor")
equilibrium = json.loads(
    (folder / "equilibrium_verification.json").read_text()
)
power = json.loads(
    (folder / "power_screening.json").read_text()
)

rotors = equilibrium["centered_cg"]["rotors"]
positions = [(r["x_m"], r["y_m"]) for r in rotors]

# Evaluate existing and candidate propeller radii.
radii = (0.75, 0.50)
results = {}

for radius in radii:
    distances = []

    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            dx = positions[i][0] - positions[j][0]
            dy = positions[i][1] - positions[j][1]
            distances.append(math.hypot(dx, dy))

    minimum_distance = min(distances)
    clearance = minimum_distance - 2 * radius
    compatible = clearance >= 0

    # At unchanged thrust and air density, ideal
    # isolated-disk power scales inversely with radius.
    original_radius = power["assumed_radius_m"]
    scale = original_radius / radius

    normal_power = (
        power["results"]["normal"]["total_ideal_power_w"]
        * scale
    )
    worst_failure_power = max(
        record["total_ideal_power_w"] * scale
        for name, record in power["results"].items()
        if name.startswith("failed_")
    )

    label = f"radius_{radius:.2f}_m"
    results[label] = {
        "rotor_radius_m": radius,
        "minimum_center_spacing_m": minimum_distance,
        "minimum_disk_clearance_m": clearance,
        "coplanar_disks_do_not_overlap": compatible,
        "normal_ideal_power_w": normal_power,
        "worst_failure_ideal_power_w": worst_failure_power,
    }

    print(f"\nROTOR RADIUS: {radius:.2f} m")
    print("Minimum centre spacing:",
          round(minimum_distance, 4), "m")
    print("Disk clearance:", round(clearance, 4), "m")
    print("Coplanar geometry compatible:", compatible)
    print("Normal ideal power:",
          round(normal_power, 2), "W")
    print("Worst failure ideal power:",
          round(worst_failure_power, 2), "W")

output = folder / "rotor_spacing_verification.json"
output.write_text(json.dumps({
    "results": results,
    "qualification": "GEOMETRIC_AND_IDEAL_POWER_SCREENING",
    "aerodynamic_interference": "NOT_EVALUATED",
    "physical_validation": "NOT_ESTABLISHED"
}, indent=2))

assert not results["radius_0.75_m"][
    "coplanar_disks_do_not_overlap"
]
assert results["radius_0.50_m"][
    "coplanar_disks_do_not_overlap"
]

print("\nPASS: Rotor spacing audit completed")
print("Saved:", output)
