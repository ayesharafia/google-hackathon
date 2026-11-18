# PHYSIMESH Eight-Rotor Engineering Validation

## Classification
NUMERICAL ENGINEERING TESTS COMPLETED FOR DEFINED SCENARIOS

Overall Activity 6: IN PROGRESS
Physical validation: NOT ESTABLISHED

## Completed Numerical Evidence
- Eight-rotor static equilibrium: PASS
- Centre-of-gravity offset handling: PASS
- Constrained thrust allocation: PASS
- Optimized thrust allocation: PASS
- Roll/pitch/yaw authority: PASS for tested cases
- Dynamic recovery: 8/8 defined scenarios PASS
- Propulsion power screening: 9/9 scenarios evaluated
- Electrical current screening: 48 to 120 V evaluated

## Governing Propulsion Requirements
- Scenario: Rotor 8 failure
- Total electrical power: 14.640 kW
- Maximum individual electrical power: 3.118 kW
- Maximum shaft power: 2.806 kW
- Maximum shaft torque: 8.933 Nm
- Assumed rotor radius: 0.50 m
- Assumed RPM: 3000
- Assumed figure of merit: 0.70
- Assumed motor efficiency: 0.90

## Provisional Sizing
- Screening margin: 20%
- System electrical power target: 17.568 kW
- Individual electrical power target: 3.742 kW
- Shaft torque target: 10.720 Nm

## Outstanding Requirements
- Verify actual motor torque-speed ratings
- Verify ESC continuous and peak current limits
- Verify battery voltage and discharge capability
- Confirm thermal and transient operating limits
- Complete end-to-end model integration review
- Obtain physical laboratory evidence separately

## Limitations
Numerical tests use illustrative geometry, idealized
propulsion models and provisional acceptance criteria.

The results do not establish actual propulsion hardware
feasibility, integrated physical qualification or flight
readiness.

No NACA0012 benchmark is included in this validation
acceptance scope.

## Supporting Evidence
- INTEGRATED_VALIDATION_REPORT.md
- integrated_acceptance.log
- PROPULSION_REQUIREMENTS.md
- propulsion_envelope.json
- verify_propulsion_envelope.py

## Integrated Model Consistency Review

Static allocation and ideal-power consistency:
- Checks performed: 139
- Failed checks: 0
- Result: PASS

Dynamic configuration review:
- Aircraft mass: 100 kg
- Rotor-arm radius: 1.5 m
- Rotor count: 8
- Rotor geometry: loaded from centered-CG equilibrium case
- Spin directions: alternating +/-1
- Yaw torque/thrust ratio: 0.02 m
- Assumed inertia: [20, 20, 35] kg m2
- Actuator time constant: 0.20 s
- Numerical timestep: 0.0025 s
- Initial attitude disturbance: 10 degrees per axis
- Failure initiation: 3.0 s
- Individual thrust limit: 200 N

Assessment:
DEFINED NUMERICAL INTEGRATION VERIFICATION COMPLETED.

The dynamic model is simplified, and physical propulsion
performance, full nonlinear flight dynamics and integrated
physical qualification remain unverified.

Overall Activity 6 remains qualified by these limitations.
Activity 7: EIGHT-ROTOR PHYSICAL VALIDATION NOT ESTABLISHED.
