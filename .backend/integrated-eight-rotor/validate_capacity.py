import json
from pathlib import Path

folder = Path(".backend/integrated-eight-rotor")
data = json.loads(
    (folder / "equilibrium_verification.json").read_text()
)

results = []

for name in ("centered_cg", "offset_cg"):
    case = data[name]
    thrusts = [
        r["required_thrust_n"]
        for r in case["rotors"]
    ]

    print(f"\nCASE: {name.upper()}")
    print("Required total thrust:",
          round(sum(thrusts), 3), "N")

    for cap in (120.0, 130.0, 150.0):
        margins = [cap - t for t in thrusts]
        utilization = [100*t/cap for t in thrusts]
        within_limits = all(m >= -1e-9 for m in margins)

        status = (
            "ALLOCATION WITHIN LIMITS"
            if within_limits
            else "ALLOCATION EXCEEDS LIMITS"
        )

        print(
            f"Capacity {cap:6.1f} N | "
            f"Max utilization {max(utilization):7.2f}% | "
            f"Minimum margin {min(margins):8.3f} N | "
            f"{status}"
        )

        results.append({
            "case": name,
            "rotor_capacity_n": cap,
            "max_utilization_percent": max(utilization),
            "minimum_margin_n": min(margins),
            "allocation_within_limits": within_limits,
            "status": status
        })

assert not results[0]["allocation_within_limits"]
assert results[1]["allocation_within_limits"]
assert results[2]["allocation_within_limits"]
assert not results[3]["allocation_within_limits"]
assert not results[4]["allocation_within_limits"]
assert results[5]["allocation_within_limits"]

output = folder / "capacity_check.json"
output.write_text(json.dumps({
    "results": results,
    "qualification": "ALLOCATION_LIMIT_CHECK_ONLY",
    "note": (
        "Failure of this allocation does not prove "
        "that no alternative feasible allocation exists."
    )
}, indent=2))

print("\nPASS: Capacity-limit checks completed")
print("Saved:", output)
print("Physical validation: NOT ESTABLISHED")
