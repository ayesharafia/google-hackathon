import json
import numpy as np
from scipy.optimize import linprog
from pathlib import Path

p = Path(".backend/integrated-eight-rotor")
case = json.loads((p/"equilibrium_verification.json").read_text())["centered_cg"]
rotors = case["rotors"]

x = np.array([r["x_m"] for r in rotors])
y = np.array([r["y_m"] for r in rotors])
spin = np.array([1,-1,1,-1,1,-1,1,-1])

A = np.vstack([np.ones(8),y,-x,0.02*spin])
J = np.array([20.,20.,35.])
kp = np.array([80.,80.,70.])
kd = np.array([32.,32.,35.])

angles = np.radians([10.,10.,10.])
rates = np.zeros(3)
thrust = np.full(8,case["weight_n"]/8)

dt = 0.02
tau = 0.20
peak = 0.
failed_steps = 0

for step in range(1000):
    requested = -kp*angles-kd*rates
    target = np.r_[case["weight_n"],requested]

    solution = linprog(
        np.zeros(8),
        A_eq=A,
        b_eq=target,
        bounds=[(0,200)]*8,
        method="highs"
    )

    if not solution.success:
        failed_steps += 1
        command = thrust.copy()
    else:
        command = solution.x

    # First-order actuator dynamics
    thrust += dt*(command-thrust)/tau
    thrust = np.clip(thrust,0,200)

    actual = A@thrust
    moment = actual[1:]

    acceleration = (
        moment-np.cross(rates,J*rates)
    )/J

    rates += dt*acceleration
    angles += dt*rates

    peak = max(peak,float(np.max(thrust)))

final = np.abs(np.degrees(angles))
passed = bool(
    np.all(final < 0.2)
    and failed_steps == 0
    and peak <= 200
)

print("Final angles (deg):",np.round(final,4))
print("Peak rotor thrust (N):",round(peak,3))
print("Allocator failures:",failed_steps)
print("Integrated dynamic test:", "PASS" if passed else "REVIEW")
print("Physical validation: NOT ESTABLISHED")
