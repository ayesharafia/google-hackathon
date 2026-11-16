import json
import numpy as np
from pathlib import Path
from scipy.optimize import linprog

p = Path(".backend/integrated-eight-rotor")
case = json.loads(
    (p / "equilibrium_verification.json").read_text()
)["centered_cg"]

rotors = case["rotors"]
x = np.array([r["x_m"] for r in rotors])
y = np.array([r["y_m"] for r in rotors])
spin = np.array([1,-1,1,-1,1,-1,1,-1])

A = np.vstack([np.ones(8), y, -x, .02*spin])
J = np.array([20.,20.,35.])
kp = np.array([80.,80.,70.])
kd = np.array([32.,32.,35.])

angles = np.radians([10.,10.,10.])
rates = np.zeros(3)
thrust = np.full(8,case["weight_n"]/8)

dt, tau = .02, .20
failure_time = 3.0
allocator_failures = 0
saturated_steps = 0
peak = 0.0

for step in range(1000):
    t = step * dt
    failed = t >= failure_time

    if failed:
        thrust[0] = 0.0

    requested = -kp*angles-kd*rates
    target = np.r_[case["weight_n"],requested]

    bounds = [(0,200)]*8
    if failed:
        bounds[0] = (0,0)

    result = linprog(
        np.zeros(8), A_eq=A, b_eq=target,
        bounds=bounds, method="highs"
    )

    if result.success:
        command = result.x
    else:
        allocator_failures += 1
        command = thrust.copy()
        if failed:
            command[0] = 0.0

    thrust += (dt/tau)*(command-thrust)
    thrust = np.clip(thrust,0,200)

    if failed:
        thrust[0] = 0.0

    if np.any(thrust >= 199.999):
        saturated_steps += 1

    actual = A@thrust
    acceleration = (
        actual[1:]-np.cross(rates,J*rates)
    )/J

    rates += dt*acceleration
    angles += dt*rates
    peak = max(peak,float(np.max(thrust)))

final = np.abs(np.degrees(angles))
passed = bool(
    np.all(final < .2)
    and allocator_failures == 0
    and peak <= 200.000001
    and abs(thrust[0]) < 1e-9
)

print("Rotor failed: 1 at 3.0 s")
print("Final angles (deg):",np.round(final,4))
print("Final rotor 1 thrust:",round(thrust[0],4),"N")
print("Peak surviving thrust:",round(peak,3),"N")
print("Allocator failures:",allocator_failures)
print("Steps at thrust limit:",saturated_steps)
print("Dynamic failure test:","PASS" if passed else "REVIEW")
print("Physical validation: NOT ESTABLISHED")
