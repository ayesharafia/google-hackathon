# PHYSIMESH — Integrated Eight-Rotor Engineering Validation Report

**Status:** Draft for engineering review  
**Evidence baseline commit:** `e749fef` (branch at time of validation: `validation/naca0012-trl4`)  
**Subsequent dynamic evidence:** local, uncommitted; commit only following review  
**Assessment scope:** numerical engineering verification of an *illustrative* eight-rotor aircraft, not experimental performance qualification  
**Prepared:** 17 November 2026

## 1. Executive summary

The tested PHYSIMESH eight-rotor allocation and simplified dynamic controller demonstrated numerical static equilibrium, control-authority classification, constrained/optimized allocation, and final-state recovery following each of eight single-rotor failures. The final priority-based bounded allocation tests returned **8/8 PASS** under the documented *provisional* final-state criteria; these results are supported by `integrated_acceptance.log`. These results do **not** establish validated rotor thrust, physical aircraft stability, propulsion hardware compliance, laboratory validation, or an aircraft TRL rating.

A diagnostic exact bounded allocation experiment produced **626 infeasible optimization requests** in the Rotor 8 failure case, despite subsequent recovery. A separately tested weighted least-squares bounded priority allocator yielded no solver failures in the eight reported cases, with the worst reported maximum altitude loss of **0.1391 m** (Rotor 7). There are still unresolved model and controller acceptance questions, including the scientific justification of the weights, all-case temporal convergence, transient requirements, and physical actuator characterization.

## 2. Original validation framework — authoritative status register

| Main validation activity | Evidence-based status |
|---|---|
| BEMT numerical verification | Passed (prior work; underlying rotor evidence not re-audited in this report) |
| Rotor software tests | 219 passed (previously reported; not rerun for this report) |
| Experimental data integrity | Passed (prior work) |
| Empirical thrust interpolation | Completed (prior work) |
| Measured rotor thrust validation | **Unvalidated** |
| Integrated eight-rotor engineering validation | Selected numerical engineering tests completed; overall evidence review open |
| Eight-rotor physical validation | **Not established** |

| Engineering validation | Evidence-based status |
|---|---|
| Eight-rotor static equilibrium | Passed for recorded cases |
| Centre-of-gravity offset handling | Passed for recorded cases |
| Constrained thrust allocation | Passed for recorded static cases; 150 N rotor-out infeasibility retained |
| Optimized thrust allocation | Passed for recorded static cases |
| Four-axis static equilibrium | Tested |
| Rotor-out at 150 N | **Infeasible** |
| Rotor-out yaw authority at 200 N | Feasible in idealized model |
| Roll/pitch/yaw authority envelopes | **Passed — tested numerical verification cases** |
| Motor torque and electrical power | Preliminary demand calculations reconciled; actual hardware-limit validation pending |
| Dynamic stability | **Passed — defined final-state numerical recovery scenarios; full physical/dynamic qualification open** |
| Integrated physical qualification | **Not established** |

## 3. Configuration and assumptions

- Illustrative aircraft mass: **100 kg**; weight per baseline static model approximately **981 N**.
- Eight rotors, radial arm radius **1.5 m**; example centre-of-gravity offsets used in earlier tests included **(0.10, −0.05) m**.
- Per-rotor thrust limits investigated: **150 N** and **200 N**. These are assumed model limits, not motor test ratings.
- Idealized reaction-torque coefficient: **0.02 m**, alternating rotor spin directions.
- Initial angular disturbance in tested dynamic scenarios: **10°** on each of roll, pitch and yaw.
- Diagonal rigid-body inertias in dynamic model: **[20, 20, 35] kg·m²**.
- Attitude proportional gains **[80, 80, 70]**; derivative gains **[32, 32, 35]** (units follow implemented moment/angle and moment/angular-rate conventions).
- First-order actuator response time constant **0.20 s**; instantaneous failed-rotor shutdown at **t = 3.0 s**.
- Vertical controller test law: `Fz_cmd = mg − 100 z − 150 vz` using simulated vertical position and speed.
- Single-failure dynamic tests simulated **20 s**. Priority allocator convergence runs employed timesteps **0.010**, **0.005**, and **0.0025 s**.
- Dynamic models approximate attitude kinematics by direct integration of angular rates and assume all produced thrust acts vertically in the altitude equation; rotor aerodynamics, thrust tilt, propeller gyroscopic effects, aerodynamic damping and hardware dynamics are not comprehensively represented.

## 4. Governing mathematical model

For the tested static thrust allocation, with signed planar rotor locations `(x_i, y_i)` measured from the centre of gravity and spin sign `s_i`:

\[
\begin{aligned}
F_z &= \sum_{i=1}^{8} T_i,\\
M_x &= \sum_{i=1}^{8} y_i T_i,\\
M_y &= -\sum_{i=1}^{8} x_i T_i,\\
M_z &= \sum_{i=1}^{8} k_q s_i T_i.
\end{aligned}
\]

In matrix form, `A T = [Fz, Mx, My, Mz]^T`. Physical candidate bounds are `0 ≤ T_i ≤ T_i,max`; the failed rotor must satisfy `T_failed = 0`.

The simplified coupled rotational model implements:

\[
J \dot\omega = M - \omega \times (J\omega).
\]

The simplified vertical dynamics implement:

\[
\ddot z = (F_z - mg)/m.
\]

The actuator update in the recorded code is first-order explicit Euler:

\[
T_{k+1} = \operatorname{clip}\left[T_k + (\Delta t/\tau)(T_{\mathrm{cmd}}-T_k),\ 0,\ 200\ \mathrm N\right].
\]

The priority allocation diagnostic uses bounded weighted least squares, minimizing `||W (A T - b_cmd)||²`, with raw provisional weights `W = diag(1,1,1,0.2)`. Since the objective mixes N and N·m, these weights are **not yet independently normalized or validated**. An optimization success flag does not itself prove that all requested force/moment channels were achieved.

## 5. Control-authority verification

### Independent-axis envelopes

- **10 configurations**, **30 roll/pitch/yaw axis evaluations** reported feasible and bidirectional.
- Normal case at **150 N**: roll and pitch **±280.821 Nm** each; yaw **±4.3867 Nm**.
- Normal case at **200 N**: roll and pitch **±628.452 Nm** each; yaw **±12.3867 Nm**.
- Example Rotor 1 failure at **200 N**: roll **±288.765 Nm**; pitch **−192.953 to +628.452 Nm**; yaw **−12.3867 to +4.3867 Nm**.
- Independent-axis maxima are **not simultaneous combined-axis limits**.

### Coupled-control feasibility

- **30** reported solved mathematical allocation cases.
- **20** within prescribed rotor limits.
- **10** outside limits; all ten were precisely the expected `150_failed_1_*` and `150_failed_2_*` scenarios in the saved test matrix.
- Maximum reported equilibrium residual: **4.192202140984591e−13** in model force/moment coordinates.
- The existing script asserts a residual below `1e−6` and checks specific representative feasible/infeasible scenarios. An independent classification check verified the ten infeasible scenario labels against the saved data.

**Acceptance conclusion:** Tested numerical authority and coupled-feasibility classification **passed**. Not all theoretical requests are achievable within rotor limits; expected infeasibility is retained rather than reclassified as success.

## 6. Power, torque and electrical requirements — preliminary

Original ideal isolated-actuator-disk screening used density **1.225 kg/m³**, radius **0.75 m** and

\[
P_{\mathrm{ideal}}=\frac{T^{3/2}}{\sqrt{2\rho\pi R^2}}.
\]

Coplanar disk overlap was detected for the original radius. A geometrically nonoverlapping **0.50 m candidate radius** was evaluated using the scaling `P_ideal(0.50 m) / P_ideal(0.75 m) = 1.5` at fixed thrust. This is a geometric ideal-disk screening approximation, **not measured aerodynamics**.

The file `power_screening_geometry_corrected.json` records corrected-radius metadata but contains **unscaled ideal power values**, as demonstrated by independently back-calculating **R = 0.75 m** from a stored Rotor 8 thrust and individual power. Therefore that file must **not** be interpreted as containing recalculated corrected-radius power columns. Derived 0.50 m estimates apply the 1.5 factor once to the 0.75 m results.

With **figure of merit 0.70**, **motor efficiency 0.90**, and illustrative **3000 RPM**:

| Scenario | Estimated corrected total electrical power |
|---|---:|
| Normal | 12.573 kW |
| Failed rotor 1 | 14.294 kW |
| Failed rotor 2 | 14.494 kW |
| Failed rotor 3 | 14.093 kW |
| Failed rotor 4 | 13.834 kW |
| Failed rotor 5 | 13.801 kW |
| Failed rotor 6 | 14.403 kW |
| Failed rotor 7 | 14.313 kW |
| Failed rotor 8 | **14.640 kW** |

Governing reported Rotor 8-failure single-motor demand (most loaded surviving Rotor 7) is about **195.095 N**, **2.806 kW shaft**, **8.933 N·m at 3000 RPM**, and **3.118 kW electric**.

**Status:** Preliminary computed requirements are reconciled. Motor continuous/peak ratings, torque–speed maps, ESC current limits, battery discharge ratings, and physical efficiency data are absent; therefore **hardware-limit compliance cannot pass**.

## 7. Dynamic stability and single-rotor failure

### 7.1 Allocator diagnosis and correction

The original minimax allocator enforced `T_i ≤ 200u` but did not limit `u ≤ 1`; the actual actuator output was clipped afterward. A diagnostic variant explicitly enforced `u ≤ 1`, causing **626 failed exact allocation requests** in the reported Rotor 8 case. This resulted in final roll **0.2398°** and pitch **0.2234°**, above the original **0.2°** final attitude threshold. Its fallback held previous commands rather than consistently minimizing achievable force/moment error.

A separate bounded weighted least-squares priority allocator solved the tested scenarios without optimizer failures. This correction is a **tested engineering candidate**, not validated flight-control software. Its force/moment weighting must be justified and measured tracking errors reviewed.

### 7.2 Priority allocator — eight-failure outcomes

All eight cases report `Integrated numerical acceptance: PASS` under **provisional** final-state thresholds. Reported maxima from the separate priority-allocator runs:

| Failed rotor | Maximum transient altitude loss (m) | Peak surviving thrust (N) | Largest final attitude error (°) |
|---|---:|---:|---:|
| 1 | 0.1390 | 189.537 | 0.0772 |
| 2 | 0.1094 | 199.792 | 0.0430 |
| 3 | 0.1373 | 189.413 | 0.0743 |
| 4 | 0.1084 | 199.784 | 0.0415 |
| 5 | 0.1375 | 189.426 | 0.0745 |
| 6 | 0.1096 | 199.794 | 0.0440 |
| 7 | **0.1391** | 189.545 | 0.0774 |
| 8 | 0.1107 | **199.796** | 0.0443 |

Illustrative final-state acceptance gates implemented in `test_vertical_acceptance.py`: final absolute roll/pitch/yaw below **0.2°** each; zero solver failures; peak thrust at most **200 N**; failed-rotor thrust zero; final |z| below **0.20 m**; final |vz| below **0.05 m/s**; and final actual-force/moment error within **[5 N, 5 Nm, 5 Nm, 1 Nm]**. These are test thresholds, **not aircraft safety requirements**.

### 7.3 Rotor 8 transient tracking

- Maximum **allocation** errors (force, roll, pitch, yaw): approximately **[0.00044 N, 0 Nm, 0 Nm, 0.54384 Nm]**; zeros shown at printed precision.
- Maximum **actual** actuator tracking errors: **[108.15812 N, 114.6587 Nm, 114.788 Nm, 12.06459 Nm]**.
- Times of maxima: **[3.0, 3.0, 3.0, 0.0] s** respectively; roll/pitch/vertical errors peak at failure, yaw at initial disturbance.
- Maximum actual tracking errors after **t ≥ 4 s**: **[4.38105 N, 13.92018 Nm, 14.78163 Nm, 0.99121 Nm]**.
- Last-exceedance-based diagnostic settling durations after failure: **[0.6475, 3.2375, 3.2475, 0.7900] s** using provisional bands **[5 N, 5 Nm, 5 Nm, 1 Nm]**. Final error check verified all bands at the last step for Rotor 8.
- Final Rotor 8 errors: **[0, 0.01242, 0.01184, 0.00947]** in the above units; `Tracking settled: True` at the final step. All eight cases reported this final-step flag as true, but their entire post-failure settling histories have not independently been reviewed.

### 7.4 Priority allocator timestep refinement, Rotor 8

| Timestep (s) | Maximum altitude loss (m) | Peak descent speed (m/s) | Peak thrust (N) | Allocator failures |
|---|---:|---:|---:|---:|
| 0.0100 | 0.1066 | 0.1478 | 199.708 | 0 |
| 0.0050 | 0.1093 | 0.1509 | 199.771 | 0 |
| 0.0025 | 0.1107 | 0.1524 | 199.796 | 0 |

The altitude-loss differences are **0.0027 m** and **0.0014 m**, suggesting approximately first-order convergence for this metric. Estimates of apparent order and extrapolated values depend on rounded printed data, can be sensitive to the nonsmooth failure/saturation event, and are **not** a total uncertainty estimate. Final attitude metrics show remaining timestep sensitivity. Convergence has not been independently established for all eight rotor failures.

### 7.5 Acceptance boundary

**Passed:** The defined numerical final-state recovery test for eight single-rotor failures using the candidate priority-based bounded allocator.  
**Not established:** Transient flight-safety limits, physically validated actuator dynamics, full six-degree-of-freedom performance, robustness over all masses/CG/environmental conditions, hardware safety margins, and physical flight qualification.

## 8. Evidence and integrity

- Existing committed engineering evidence baseline: **`e749fef`**; contains prior JSON verification records, original Python scripts and their SHA-256 manifests.
- Local dynamic logs: `docs/validation/eight_rotor/dynamic_recovery.log` and `docs/validation/eight_rotor/integrated_acceptance.log`.
- Local dynamic validation script evidence: `docs/validation/eight_rotor/scripts/`, containing **16** byte-identical copies of the source dynamic test scripts at the time of comparison.
- SHA-256 manifest for local evidence: `docs/validation/eight_rotor_evidence.sha256`. **18/18** saved log and script entries passed `sha256sum -c` on the user's local machine.
- Local branch had an unrelated modified file: `docs/validation/sphere_re100_runs.md`. Do **not** accidentally include or discard that modification during the final eight-rotor evidence commit.
- Note: `.backend/` is excluded by `.gitignore`; the review copies under `docs/validation/eight_rotor/scripts/` are the normally trackable dynamic-script evidence. Git inclusion and final commit have **not yet** been verified for this draft report.

Checksum validity demonstrates byte integrity of captured artifacts, **not** proof of experimental accuracy or independent algorithmic correctness.

## 9. Outstanding requirements within the original validation framework

1. **Motor torque and electrical power:** Specify actual motor continuous and peak ratings, torque–speed map, ESC current/power bounds, battery voltage and discharge limits; compare all operational demands with these limits before marking this activity fully passed.
2. **Dynamic stability:** Retain the candidate bounded priority controller's provisional weights as open engineering design parameters; formalize transient performance requirements and extend convergence/robustness tests as needed for the claimed operating envelope. Preserve distinctions between initial-attitude, actuator-delay and rotor-failure tracking errors.
3. **Measured rotor thrust validation:** Remains **Unvalidated**. The independent UIUC APC 12×6 coefficient dataset and 51-station geometry are relevant to this separate activity, but no independent PHYSIMESH prediction-to-experimental comparison is demonstrated by the eight-rotor evidence package.
4. **Integrated physical qualification:** Remains **Not established** until laboratory/physical tests support it. The present numerical evidence is not a declaration of aircraft TRL 4, flight readiness, certification or operational safety.
5. **Evidence:** Review this report and final acceptance logs, ensure the geometry-corrected metadata discrepancy is documented or addressed in a separately traceable derived file, review the tracked file list, then make the agreed single final commit.

## 10. Engineering conclusion

PHYSIMESH's integrated eight-rotor numerical verification has advanced from static equilibrium and control-authority screening to reproducible candidate bounded allocation and final-state dynamic rotor-out recovery. The **8/8** reported acceptance results and recorded transient tracking diagnostics support software engineering progress for the **defined illustrative scenarios**. They do not validate real rotor thrust, propulsion hardware capability, physical rotor-out safety, or full system qualification. The original validation framework remains open until its outstanding hardware and physical evidence requirements are met.
