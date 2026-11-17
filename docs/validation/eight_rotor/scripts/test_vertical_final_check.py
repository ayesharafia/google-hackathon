import os
import json
import numpy as np
from pathlib import Path
from scipy.optimize import linprog
from scipy.optimize import lsq_linear

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

dt, tau = .0025, .20
failure_time = 3.0
failed_index = int(os.getenv("FAILED_ROTOR", "1")) - 1
allocator_failures = 0
saturated_steps = 0
peak = 0.0
z = 0.0; vz = 0.0; min_support = float("inf"); max_descent = 0.0
min_z = 0.0

peak_error = np.zeros(4)
peak_actual_error = np.zeros(4)
peak_error_time = np.zeros(4)
post_error = np.zeros(4)
last_exceed = np.full(4,3.0)
for step in range(8000):
    t = step * dt
    failed = t >= failure_time

    if failed:
        thrust[failed_index] = 0.0

    requested = -kp*angles-kd*rates
    target = np.r_[case["weight_n"]-100*z-150*vz,requested]

    bounds = [(0,200)]*8
    if failed:
        bounds[failed_index] = (0,0)

    caps = np.full(8, 200.0)
    if failed:
        caps[failed_index] = 0.0

    objective = np.zeros(9)
    objective[-1] = 1.0

    inequalities = np.column_stack([
        np.eye(8), -caps
    ])

    weights = np.array([1.0, 1.0, 1.0, 0.2])

    W = np.diag(weights)

    result = lsq_linear(
    W @ A,
    W @ target,
    bounds=(
        np.zeros(8),
        caps + 1e-12
    ),
    method="trf"
    )

    if result.success:
    	command = result.x.copy()
    else:
    	allocator_failures += 1
    	command = thrust.copy()
 
    if failed:
    	command[failed_index] = 0.0

    thrust += (dt/tau)*(command-thrust)
    thrust = np.clip(thrust,0,200)

    if failed:
        thrust[failed_index] = 0.0

    if np.any(thrust >= 199.999):
        saturated_steps += 1

    actual = A@thrust
    if t >= 3.0: last_exceed = np.where(np.abs(actual-target)>[5,5,5,1],t,last_exceed)
    if t >= 4.0: post_error = np.maximum(post_error,np.abs(actual-target))
    peak_error_time = np.where(np.abs(actual-target)>peak_actual_error,t,peak_error_time)
    peak_actual_error = np.maximum(peak_actual_error,np.abs(actual-target))
    peak_error = np.maximum(peak_error,np.abs(A@command-target))
    az = (actual[0] - case["weight_n"]) / case["mass_kg"]; vz += dt * az; z += dt * vz; min_support = min(min_support, actual[0]); max_descent = max(max_descent, -vz)
    min_z = min(min_z, z)
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
    and abs(thrust[failed_index]) < 1e-9
)

print(f"Rotor failed: {failed_index+1} at 3.0 s")
print("Final angles (deg):",np.round(final,4))
print("Final failed rotor thrust:",round(thrust[failed_index],4),"N")
print("Peak surviving thrust:",round(peak,3),"N")
print("Allocator failures:",allocator_failures)
print("Steps at thrust limit:",saturated_steps)
print("Minimum support (N):",round(min_support,3)); print("Final vertical speed (m/s):",round(vz,4)); print("Altitude change (m):",round(z,4)); print("Peak descent speed (m/s):",round(max_descent,4))
print("Dynamic failure test:","PASS" if passed else "REVIEW")
print("Maximum altitude loss (m):", round(-min_z,4))
print("Peak allocation errors [N,Nm,Nm,Nm]:",np.round(peak_error,5))
print("Peak actual errors [N,Nm,Nm,Nm]:",np.round(peak_actual_error,5))
print("Peak actual error times (s):",np.round(peak_error_time,4))
print("Peak errors after 4s [N,Nm,Nm,Nm]:",np.round(post_error,5))
print("Tracking settling times after failure (s):",np.round(last_exceed-3.0+dt,4))
print("Final tracking errors:",np.round(actual-target,5))
print("Tracking settled:",bool(np.all(np.abs(actual-target)<=[5,5,5,1])))
print("Physical validation: NOT ESTABLISHED")
