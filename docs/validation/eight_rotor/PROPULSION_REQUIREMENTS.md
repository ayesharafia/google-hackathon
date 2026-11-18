# PHYSIMESH Eight-Rotor Propulsion Requirements

Status: NUMERICAL REQUIREMENTS VERIFIED
Hardware operating limits: NOT VERIFIED
Physical validation: NOT ESTABLISHED

## Assumptions
- Rotor radius: 0.50 m
- Air density: 1.225 kg/m3
- Figure of merit: 0.70 (assumed)
- Motor efficiency: 0.90 (assumed)
- Rotor speed: 3000 RPM (assumed)
- Model: ideal isolated actuator disk

## Corrected Scenario Results

| Scenario | Electrical power (kW) | Peak shaft torque (Nm) |
|---|---:|---:|
| Normal | 12.573 | 5.312 |
| Failed 1 | 14.294 | 8.553 |
| Failed 2 | 14.494 | 8.336 |
| Failed 3 | 14.093 | 7.411 |
| Failed 4 | 13.834 | 7.380 |
| Failed 5 | 13.801 | 7.380 |
| Failed 6 | 14.403 | 7.444 |
| Failed 7 | 14.313 | 8.099 |
| Failed 8 | 14.640 | 8.933 |

## Governing Scenario
Rotor 8 failure:
- Maximum system electrical power: 14.640 kW
- Maximum individual shaft torque: 8.933 Nm
- Maximum individual shaft power: approximately 2.806 kW
- Maximum individual electrical power: approximately 3.118 kW

## Limitations
The original JSON contains ideal-power values calculated
using a 0.75 m rotor radius. A factor of 1.5 was applied
once to calculate the requirements for a 0.50 m radius.

No physical motor, ESC, battery or propeller ratings have
been supplied. Hardware feasibility is not established.

The assumptions and results are illustrative and must not
be used as evidence of flight readiness.
