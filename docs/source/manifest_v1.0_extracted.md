# PhysiCore Drone Project Manifest v1.0 (1 October 2026) — extracted text

> Machine extraction of PhysiCore_Drone_Detailed_Project_Manifest.docx for LLM reference. Equations E01–E56 are omitted here (Word math objects) and are transcribed in plan.md §7. Style tags like [Heading1] come from the docx. If this copy and the .docx disagree, the .docx wins.

# PhysiCore Engine Drone Project Manifest
Physics specification and development contract for a 750 kg payload aircraft
Version 1.0 | 1 October 2026
Develop a three dimensional drone module that imports STL assemblies, predicts and verifies aerodynamic loads, evaluates rotor thrust and power, and produces reproducible engineering evidence. Extend the existing PhysiMesh orchestration and reporting services with new geometry, mesh, propulsion and visualization capabilities. Use an established CFD backend for the flow equations.
The governing payload requirement is 750 kg of carried payload. Aircraft structure, propulsion, energy storage and other equipment must be added to obtain total takeoff mass. No particular vehicle is declared capable of carrying this payload until its geometry, operating envelope, propulsion limits and validation evidence are supplied.
This manifest defines the engineering equations, data contracts, settings, software changes, release gates and automatic plot selection rules. It covers geometric symmetry checking, geometry mirroring and physically eligible reduced domain simulation. It distinguishes current documented capabilities from proposed additions. It is a development contract, not a completed drone simulation or a flight qualification.
The proposed first configuration is a multirotor aircraft. Coaxial rotors, tiltrotors and lift and cruise aircraft require additional cases and capability checks. Structural integrity, electrical endurance and controllability remain necessary parts of the aircraft program.
### How to use this manifest
Implement the requirements in release order. Every numerical result must resolve to an immutable project snapshot and retained solver evidence. Every proposed setting must pass a capability check for the pinned solver release. Values labeled starting values are development choices to test, not universal engineering limits or achieved accuracy.
A companion YAML template records the required setup and plot policies. Unknown design values remain null and block execution. The YAML is a proposed application contract; it is not an OpenFOAM or SU2 input deck.
## 1 Baseline and scope of change
The supplied PhysiMesh Complete Project Documentation records a steady 2D scalar research solver and a guided 2D aerodynamic workflow using an external SU2 adapter. The existing aerodynamic geometry is a closed profile or polyline. Its mesh generation, reference area and force integrals use two dimensional conventions. Three dimensional STL healing, 3D volume meshing, rotating assemblies and GPU execution are not established capabilities.
| Existing area | Reuse | Required development |
| aero models and service | Request validation and workflow structure | New 3D assembly and operating condition models |
| 2D geometry and Gmsh workflow | Quality reporting concepts | STL preparation and 3D mesh adapter |
| solver contracts and run service | Job lifecycle, artifacts and diagnostics | Rotor capabilities and version pinned backend |
| 2D force reconstruction | Provenance and sign testing patterns | 3D surface integrals and moments |
| analysis sessions and campaigns | Saved recipes and comparisons | Volume, surface, rotor phase and time statistics |
| browser raster worker | Some UI conventions | 3D viewer, clipping and vector display |
| scalar adaptation engine | Research verification examples | No direct reuse as a rotor Navier Stokes solver |

Architecture decision. Add a dedicated drone domain package. Keep shared solver services independent of aircraft type. Prefer one supported OpenFOAM distribution and release for the first 3D rotor workflow. Retain SU2 for its existing cases; add a drone capability only after testing the exact supported release. Backend choice is a development recommendation, not an existing integration.
STL input and volume mesh generation are separate stages. A triangulated surface does not supply the fluid cells, boundary layers, rotor interfaces or physical boundary conditions needed by CFD. OpenFOAM documents STL driven meshing and rotating interface examples [R1–R2]; these still require a new application adapter.
Initial exclusions. No automatic CAD shape optimization from an STL, no full aircraft aeroelastic coupling, no battery chemistry solver, no acoustic certification, no flight controller deployment, and no guarantee of flight compliance. Define extension interfaces for these later. Export aerodynamic load cases and propulsion maps so the rest of the engineering program can use them.
## 2 Requirement register and decision outputs
| ID | Requirement | Acceptance evidence |
| REQ01 | Treat 750 kg as payload | Mass ledger and total mass with units |
| REQ02 | Import ASCII and binary STL | Unit and geometry fixtures plus 3D preview |
| REQ03 | Separate stationary and rotating parts | Tagged assembly and rotor zone validation |
| REQ04 | Predict thrust and shaft torque | Measured map or validated rotor model |
| REQ05 | Assess full vehicle aerodynamic loads | Body, rotor and total forces without duplication |
| REQ06 | Detect and execute valid symmetry | Transformation tests and full domain comparison |
| REQ07 | Evaluate power and mission energy | Component limits and energy balance |
| REQ08 | Quantify mesh and time sensitivity | Controlled refinement campaigns |
| REQ09 | Select physically relevant plots | Field, unit, time and capability checks |
| REQ10 | Preserve reproducibility | Input, geometry, mesh, backend and recipe hashes |
| REQ11 | Preserve existing 2D behavior | Appropriate existing regression checks |
| REQ12 | Report failed or unsupported work honestly | Explicit statuses and blocked claims |

The decision report must answer: What is total mass? What thrust is required at each condition? What thrust is predicted and within what applicability? What shaft and electrical power are needed? What body download and moments exist? Is a trim solution available within actuator limits? What uncertainty could change the decision?
The aircraft status must be one of inputs_incomplete, screening_only, numerically_unverified, validation_pending, within_validated_envelope, or requirement_not_met. A completed CFD process is not a feasibility status. A design can meet thrust yet fail power, control, energy or structural requirements.
Use separate release statuses for the software and for each aircraft study. Software release acceptance does not validate an arbitrary customer model.
Required environmental cases. Hover, climb, descent, forward flight if applicable, limiting temperature and density, crosswind, ground clearance, maximum and minimum mass states, and intended payload positions. Add rotor loss and electrical derating as explicitly defined cases. Descent through a rotor wake requires special assessment; a simple axial momentum estimate is inadequate in vortex ring conditions.
## 3 Units frames and symbol contract
Use SI internally. Store the original unit declaration and every conversion. A coordinate transform applies to points, vectors, tensors, rotor axes and moment origins, not only to the rendered geometry.
| Symbol or field | Meaning | Unit |
| x, r, R, D, c | Position, radial coordinate, radius, diameter, chord | m |
| m, I | Mass and inertia tensor | kg and kg m² |
| u, w, v_i | Velocity, moving mesh velocity, induced speed | m/s |
| rho, mu, nu | Density, dynamic and kinematic viscosity | kg/m³, Pa s, m²/s |
| p, p_k | Static pressure and kinematic pressure | Pa and m²/s² |
| T, F, Q, M | Thrust, force, shaft torque, moment | N and N m |
| Omega, n | Angular speed and revolutions per second | rad/s and 1/s |
| k, omega_t, nu_t | Turbulent kinetic energy, specific dissipation, eddy viscosity | m²/s², 1/s, m²/s |
| q_ref, t_A | Reference dynamic pressure and surface traction | Pa |

World frame. Right handed east north up convention for the study: x and y horizontal; z upward. Gravity is (0,0,-g). The default body frame is right handed with x forward, y left and z upward. A rotation matrix maps body vectors into the world frame. If an imported CAD uses another convention, transform it explicitly and show the axes in the preview.
Rotor frame. Record a unit thrust axis a_i, center x_i, and signed angular velocity vector. Positive RPM follows the right hand rule about a_i. Blade handedness and rotation sign must agree. Rotor azimuth zero and phase offsets are mandatory for blade resolved transient comparisons.
Force convention. All reported aerodynamic forces act on the aircraft. Force exerted on the air is their opposite. The body surface normal points outward from the solid into the fluid. A backend that reports a fluid domain patch normal requires an adapter sign conversion. Record whether torque means aerodynamic resisting torque or positive motor shaft torque.
A moment is always associated with an origin. Changing center of gravity changes the reported moment even when the surface loads are unchanged. Gravity and payload weight appear in the aircraft balance, not in the aerodynamic traction field.
## 4 Mass atmosphere and operating envelope
Equations E01–E04 establish the mass state and screening conditions.
Here each component inertia has first been rotated into the common body frame, and d_j is its displacement from the combined center of gravity. Store mass uncertainty and operating state, including fuel use or removable payload. STL volume times a density is not a reliable mass estimate for a hollow assembly without material and thickness information.
Use absolute pressure and Kelvin. Set dry air R_air = 287.05 J/(kg K) and gamma near 1.4 only when this ideal gas approximation is appropriate. Supply measured or standard atmosphere data with provenance; humid air and strong temperature changes may require a better property model. Do not combine independent altitude and pressure values inconsistently.
The last expression is an axial flight screening estimate. Forward flight changes advancing and retreating blade velocities and must use the local velocity. Evaluate rotor compressibility from blade relative speed, not aircraft freestream alone.
Required settings. Payload kg, every mass item, center of gravity, inertia for dynamic studies, atmosphere source, altitude, air temperature, pressure, viscosity, humidity assumption, velocity vector, attitude, acceleration target and ground clearance. Null total mass or missing atmosphere blocks quantitative feasibility.
The payload alone weighs 7,354.99 N at standard gravity. For an illustrative total mass of 1,500 kg, weight is 14,709.98 N. These values are analytical examples; actual thrust must include aerodynamic body loading and the operating requirement.
## 5 Aircraft force moment and trim equations
E06 assumes a rigid aircraft with constant body inertia; rotor gyroscopic terms and varying mass need an extended dynamics model. CFD held at a fixed pose returns loads, not a flight trajectory. A fixed pose with nonzero net moment is not trimmed flight.
For level hover with vertical rotor axes, define body download as a positive downward force.
Use the signed body force directly when it has an upward contribution. Do not force body download to be positive in all circumstances. For tilted rotors, use each vector force projected onto the vertical and include any wing lift. Side forces must also balance when claiming hover trim.
Choose nonzero engineering scales, such as F_scale = m g and M_scale = m g L_ref. Report components as well as norms. A small overall norm must not conceal an unacceptable yaw moment or power exceedance.
Trim development. Couple rotor performance to a constrained outer loop over RPM, pitch if available, and vehicle attitude. Solve the six force and moment residuals only for physically available controls. Account for body loads and rotor interference iteratively. Report unreachable conditions; do not introduce artificial forces merely to make a solver converge.
Margins. Compare predicted loading with sustained and peak rotor limits at the same density and electrical state. Define margin as (available − required)/required with a documented denominator. Peak thrust cannot be used to justify continuous hover. A motor loss case requires feasible moment allocation and power supply, not just sufficient summed maximum thrust.
## 6 Rotor analytical and blade element equations
For an isolated ideal rotor in hover, the momentum relations provide a useful lower bound.
Figure of merit uses isolated hover assumptions; it is not universal aircraft efficiency. Overlapping or coaxial rotors cannot use independent disk area sums to claim a power benefit. Body download increases rotor thrust required above vehicle weight.
For a propeller blade element, define axial and tangential relative flow with the selected induction model.
Integrate from aerodynamic root cutout to the tip. B is blade count. E11–E13 use a propeller convention; do not copy wind turbine induction signs. Account for radial chord, twist, airfoil sections, polar interpolation, hub losses and tip losses. The numerical model must state whether a loss correction modifies induction, loading or both to avoid double application.
For a simple non swirling annulus in axial propeller operation:
Match blade element and momentum loading iteratively. Add a consistent angular momentum model for swirl. Do not apply this simplified annular relationship to strong crossflow, vortex ring descent or highly nonuniform interacting wakes without an appropriate extension. Preserve iteration residuals and polar applicability. Reject unconverged radial stations.
These relationships are engineering model definitions for this implementation. Rotorcraft systems analysis and rotor blade literature provide model context [R4–R5]. Their use does not validate a new large aircraft.
## 7 Rotor coefficients maps and fidelity selection
Use the propeller coefficient convention throughout the first release.
eta_p is useful in propulsive axial flight and goes to zero in hover; do not label that as zero hover capability. Helicopter coefficients normalized with disk area and tip speed are different. Store the convention and convert explicitly before comparing datasets. At zero RPM the coefficients are undefined; return unavailable rather than divide by a small invented RPM.
| Fidelity | Inputs | Suitable result | Required limitation |
| Measured map | RPM, T, Q, inflow, density and test metadata | Fast sizing and operating limits | Interpolation within tested envelope |
| BEM | Blade geometry and airfoil polars | Radial loading and preliminary T and Q | Induction and stall model validity |
| Actuator disk | Distributed loading law or prescribed load | Wake and body interference | Prescribed T is an input, not proof |
| Actuator line | Blade geometry, polars and regularized source | Time varying distributed wakes | Smoothing and mesh sensitivity |
| Steady rotating frame | Explicit blades, rotation zone and RPM | Mean blade loading | Frozen interaction approximation |
| Transient mesh | Explicit blades, interface and phase | Blade passage and unsteady loads | Time and interface sensitivity |

Automatic selection. Use the requested engineering question and available inputs. An unknown propeller design needs BEM screening or blade resolved analysis; a measured map can support known hardware. Vehicle interference can begin with calibrated disks. Strong interaction, rotor phase effects or unsteady peaks require transient analysis. Resource limits may recommend a cheaper screening run, but cannot silently downgrade the fidelity of an accepted design decision.
Map storage. Keep signed torque conventions, shaft versus electrical power, air properties, instrumentation uncertainty, fixture geometry, inflow, blade pitch, motor thermal state and interpolation limits. Non dimensional rescaling across density assumes similar Reynolds and Mach behavior; mark that approximation and do not extrapolate through stall or compressibility changes.
## 8 Fluid equations and turbulence model contract
For constant density incompressible flow with an effective viscous stress and optional rotor force density:
For laminar flow, set modeled turbulent terms to zero. In RANS, some solvers absorb the isotropic turbulent stress into a modified pressure. The force adapter must match that pressure definition and the backend traction formulation rather than mixing conventions. Never add turbulent pressure twice.
For compressible capability, use conservative equations with total energy and thermodynamic closure.
E = e + |u|²/2, heat flux follows the selected molecular and turbulent conductivity models, and a body source energy term must be consistent with its work. The exact RANS energy treatment follows the pinned backend. Do not implement E22 with guessed source work.
Turbulence recommendation. Start blade and vehicle RANS validation with a documented SST formulation supported by the chosen release. Compare model sensitivity where separation or transition affects a decision. Laminar settings are not a substitute for missing turbulence data. LES and hybrid methods need separate wall, mesh, time and averaging requirements.
The next section records the transport structure. Production must use the backend implementation and its documented constants, limiters and wall behavior. A model name alone is not a complete reproducibility record.
## 9 Turbulence equations walls and initialization
A representative SST transport form is shown to identify required fields and coupling, not to replace the solver source implementation.
F1 and F2 are blending functions; coefficients, production limiters, small value protection and the precise strain measure depend on the SST variant. Store a backend coefficient snapshot and model version. Implementing a home made closure from E23–E25 alone is outside the first release. Keep omega_t distinct from aircraft rotation and vorticity.
For inflow estimates where intensity I_t, speed U_t and length L_t have defensible meaning:
Do not set U_t = 0 in hover and conclude turbulence is zero. Specify ambient turbulence through nonzero measured or justified absolute values, and record sensitivity. Ambient length scale cannot simply equal the far field box size.
For a low y plus development strategy, begin with a target near 1 and inspect the achieved blade and body distribution. A wall function strategy must use the valid range and implementation of that specific wall function. Neither approach is accepted from an estimated first layer alone.
Use no slip on stationary solids. For a moving blade, the inertial wall velocity is Omega × (x − center) plus aircraft translation. A relative frame may express this differently; the adapter must test both descriptions. Specify wall conditions for k and omega as required by the selected turbulence treatment. Record layer coverage, missing layers and leading edge quality together with the y plus contour.
## 10 Rotating frames moving meshes and actuator sources
In a constant rotating frame, relative velocity u_r has additional inertial accelerations.
For angular acceleration include dot(Omega) × r; a general translating rotating frame adds its origin acceleration. The backend provides its own rotating formulation. Relative velocity at a rotating wall can be zero while absolute velocity is not. All exported plots must say which velocity they use.
A moving mesh finite volume formulation uses relative face flux and must satisfy geometric conservation.
Record sliding or overset interpolation settings, donor quality, interface flux imbalance, overlap and mesh motion. An AMI interface is not a mirror boundary. Avoid blade contacts with static surfaces or rotation zone boundaries.
For a volume distributed rotor model, f_i is force per volume acting on the fluid.
A regularized actuator line can use a normalized kernel K_epsilon, with integrated source equal to the intended blade element force. Document kernel shape, width and cell resolution. Source spread must not change total force or torque. Test mesh and smoothing width together.
If a disk supplies axial force only, rotor swirl and reaction torque are unavailable unless another consistent model supplies them. Mark missing outputs; never invent a wall pressure contour for an actuator disk that has no blade surface. Avoid counting both actuator reaction and resolved blade traction for the same rotor.
## 11 STL assembly ingestion and geometry requirements
| Setting | Required value or rule |
| file format | ASCII or binary STL with bounded parser |
| source units | Explicit m, mm or other supported unit; never inferred silently |
| assembly roles | body, blade, hub, landing gear, payload, ground or excluded |
| transform | Scale, rotation and translation retained with hash |
| topology tolerance | Set in metres and relative to geometry scale |
| component identity | Stable IDs independent of triangle ordering |
| rotor assignment | Blade and hub IDs linked to a rotor and rotation zone |
| geometry provenance | Original file hash and repair history |

Parse without executing content. Bound uploaded bytes and triangles, reject nonfinite coordinates, and verify binary header and record lengths. Do not assume a binary file beginning with the word solid is ASCII. Resource bounds belong in configuration, not arbitrary hard coded limits.
Check degenerate and duplicate facets, inconsistent winding, holes, nonmanifold edges, disconnected shells, intersections and thin features below mesh resolution. Present each problem spatially in the 3D viewer. Distinguish an intentionally open duct or porous representation from defective topology through explicit modeling decisions.
A repair operation must produce a new geometry revision with changed area, bounds and surface distance metrics. Preserve leading edges, blade tips, trailing edges and gaps. Do not close openings or merge surfaces purely to obtain a green mesh status. Confirmation of a major repair is a product choice recorded by the project, not an unlogged solver convenience.
Assembly separation. Prefer separate component STL files for blades and body. A combined STL may be split by disconnected shells, but connected or overlapping components cannot be assigned reliably without user tagging. Imported blade geometry must include its pitch state. Rotation metadata cannot be recovered reliably from geometry alone.
Geometry accuracy. Compare tessellation chordal error with the desired blade shape fidelity and mesh spacing. Refining a volume mesh cannot recover missing geometry from a coarse STL. Keep a source CAD reference where available even though the initial interface accepts STL.
Readiness output. Return status, unit scale, bounding box, triangle and shell counts, surface area, topology issues, proposed repairs, component roles and unresolved inputs. Import success means the file was read; it does not mean a valid CFD case was created.
## 12 Symmetry geometry and physical eligibility
For a plane through x0 with unit normal n, define reflection matrix H.
Compare each reflected surface with the intended counterpart using bidirectional distances and unmatched area. Sample facet interiors as well as vertices; different triangulations can describe the same surface. Record scale dependent tolerance, maximum distance, percentile distance and unmatched component IDs. A heuristic symmetry score is not a physical eligibility result.
For vector and axial vector transforms:
Reflect triangle coordinates then correct winding and normals. Transform rotor handedness, centers, axes and rotation sign, and relevant inertia tensors. Preserve the source geometry rather than overwriting it.
Eligibility rules. Geometry, ambient flow, rotor distribution, RPM, loading law, boundary conditions and transient rotor phase must be invariant under the proposed reduction. Center of gravity and applied controls must support the same trim assumption. A geometrically symmetric body with a single swirling rotor does not generally satisfy mirror symmetry. Counter rotating paired rotors may, but only if the complete modeled problem matches.
A mirror flow boundary imposes zero normal velocity and the corresponding symmetry constraints. A repeating isolated rotor can sometimes use a rotational periodic blade sector. These are different boundary types. Drone arms, body interactions or crosswind usually destroy isolated rotor sector repetition.
Reject symmetry by default for crosswind across the plane, yaw, asymmetric RPM, displaced payload trim, motor loss and asymmetric transient disturbances. A symmetric solution can suppress real unstable modes; validate important cases using a full domain transient study.
Reconstruct forces and moments using E33 and a common origin. For each paired component, sum the simulated load and its transformed partner. Some moment components cancel rather than double. Record represented versus simulated blade count and area. A full domain versus reduced domain comparison is required before labeling a reduction validated for a case family.
## 13 Domain boundaries and mesh settings
Choose domain dimensions relative to rotor diameter and vehicle span, then test them. A starting hover box may use several rotor diameters of clearance upstream and laterally and a longer downstream wake region; this is a starting experiment, not a fixed acceptance rule. A close boundary can constrain entrainment or distort thrust even with a good residual history.
| Region | Boundary intent | Verification |
| Hover far field | Allow ambient inflow and wake outflow without forced freestream | Reverse flow handling and domain sensitivity |
| Forward flight inflow | Prescribed velocity and turbulence state | Correct body and world frame transform |
| Outlet | Compatible pressure and velocity behavior | No unintended reflection or constrained wake |
| Stationary solids | No slip with selected wall treatment | Wall units and layer coverage |
| Rotating blades | Correct moving wall in chosen frame | Tangential speed and sign fixtures |
| Ground | Specified stationary or moving ground model | Clearance and ground sensitivity |
| Symmetry or periodic | Only eligible physical reduction | Full domain or full rotor comparison |

Mesh controls. Define global cell scale, component surface resolution, blade root and tip refinement, leading and trailing edge treatment, wake refinement, rotation zone dimensions, interface resolution, boundary layer first height, growth, layer count and maximum cells. Express absolute lengths in metres and optional normalized lengths against a declared rotor diameter.
E34 is a geometric layer thickness estimate for growth ratio r_g ≠ 1; at unity use N_l y1. Layer thickness must cover the intended near wall region without collision in narrow gaps. A starting growth ratio of 1.15–1.25 is a mesh experiment, not proof of accuracy.
Record minimum volume, nonorthogonality, skewness, aspect ratio, layer coverage by component and rotor interface diagnostics. High aspect ratio boundary layer cells may be intentional, whereas a collapsed cell is not. Backend quality thresholds depend on mesh and discretization; retain its check report and add stricter case specific gates where evidence requires.
Generate systematic coarse, medium and fine variants without changing geometry, physical models or boundary conditions. The existing 2D triangular fallback cannot be labeled solver ready for this new 3D workflow. Failure to meet the resource budget produces a blocked or screening recommendation, not an automatically acceptable coarse mesh.
## 14 Discretization controls and execution settings
Use finite volume conservation in the selected backend. For a transported quantity phi, face fluxes and source integrals must form a consistent cell balance.
| Control | Proposed starting policy | Required evidence |
| Steady coupling | Backend SIMPLE or supported equivalent | Load stabilization and continuity |
| Transient coupling | Backend PIMPLE or supported equivalent | Per step nonlinear convergence |
| Convection | Bounded startup, then documented higher order scheme | Scheme and load sensitivity |
| Diffusion and gradients | Supported corrected formulation | Mesh quality and correction behavior |
| Time integration | Supported second order for final transient studies | Time refinement |
| Turbulence transport | Bounded settings and valid initialization | Positivity, wall treatment and sensitivity |
| Pressure solve | Backend validated linear solver settings | Residual and mass balance |
| Relaxation | Conservative initial values, versioned changes | No hidden automatic setting mutations |

Exact solver names, tolerances and backend dictionary syntax must be pinned in the adapter profile. Proposed project settings are translated only if capabilities are known. Do not assume syntax from another OpenFOAM distribution or release works.
The backend uses its exact flux based Courant definition. Choose time step from both Courant and rotation requirements. A starting blade rotation increment of 1 degree and target Courant below approximately 1 can guide an initial transient case, then refine. At 1,000 RPM, 1 degree gives 0.0001667 s. This does not establish time accuracy.
Output force history more frequently than full volume fields. Resolve blade passage frequencies and the peak phenomena being studied; a movie sampled too slowly can alias rotor motion. Mesh statistics, linear solve logs, restart settings, parallel decomposition, CPU count, memory and output cadence must be retained.
No claim of GPU acceleration is included. Local workstation or CPU parallel execution is the initial compute path. Codex assisted development can avoid new model API costs, but CFD runtime and hardware requirements remain independent of the ChatGPT subscription.
## 15 Convergence conservation and uncertainty settings
Execution states are queued, preparing, meshing, running, postprocessing, completed, cancelled and failed. Engineering evidence is recorded separately as unverified, iteration_converged, periodic_or_statistical_converged, mesh_assessed, time_assessed and validated_for_case_family.
For a statistically meaningful averaging interval:
Compare consecutive complete revolution windows, report force drift and RMS, and retain component moments. Do not use a fixed small number of revolutions as universal convergence. Periodic transients and irregular wakes require different stopping evidence.
Use absolute gross flux or a rotor throughput estimate for the nonzero scale; net hover boundary flux is near zero and cannot be its own normalization. Include moving mesh and density effects when relevant.
For three systematically refined meshes with equal effective refinement ratio, fine to coarse outputs f1, f2, f3 can support an observed order and GCI estimate [R6].
Apply only when convergence behavior and asymptotic assumptions support it; use another nonzero scale for near zero quantities. Unequal ratios and oscillatory convergence require an appropriate generalized analysis. For 3D meshes an effective length can be based on (V/N)^(1/3), while documenting local refinement changes.
Provisional development gates. Start with less than 2% change in key mesh and time outputs, less than 1% eligible symmetry comparison difference, and agreed experimental comparison targets such as 5% thrust and 10% torque. These are proposed targets, not demonstrated product accuracy. Also inspect local blade loading and wake behavior. Iterative, discretization, model, measurement and input uncertainties must remain distinct; a small GCI does not establish physical accuracy.
## 16 Surface forces and moments as the source of truth
With the solid outward normal n_s, pressure relative to a declared reference and viscous traction consistent with the backend:
For finite volume wall faces, integrate native face values and face geometry. Do not integrate a smoothed visualization surface to generate the official loads. Separate pressure and viscous contributions, rotors, hubs, body, landing gear and payload surfaces. Retain individual patch totals and native solver force output for comparison.
E43 defines resisting aerodynamic torque and positive shaft input for normal propulsive operation. Windmilling can change the sign. Do not obtain power by multiplying unsigned torque by an unrelated global RPM. Moment about a rotor center is different from moment about vehicle center of gravity.
Pressure dimensions. In some incompressible backends pressure is kinematic: physical pressure difference is rho × p_k. A p_rgh field additionally requires hydrostatic reconstruction with the backend reference conventions. Compressible pressure may already be Pa. Inspect dimensions and metadata; never multiply every field named p by density.
A constant reference pressure cancels for a fully closed surface but may affect an open patch or partial component integration. Store reference and closure status. For RANS, reconcile modified pressure and modeled stress with the native force function. OpenFOAM force processing provides pressure, viscous and optional porous contributions with specified density handling [R7]. The new adapter must verify its conventions against independent fixtures.
Mandatory fixtures. Uniform pressure on a closed cube gives zero net force; pressure on one known planar patch gives the predicted normal force; a linear pressure field gives the expected result; a known tangential traction gives shear force; an offset load gives the correct moment. Add a rotating blade torque sign check and actuator reaction check.
## 17 Control volume loads and propulsion accounting
A control volume offers an independent load consistency check. Let outward fluid normal be n, mesh or control surface velocity be w, and fluid momentum be integrated in an inertial frame.
Use E45 to isolate aircraft force only after accounting for all body sources, momentum storage, boundaries and pressure references. A downstream momentum flux slice alone is generally insufficient in a finite near wake. Include pressure and lateral fluxes. Avoid counting both an enclosed actuator source and a separately inferred surface reaction without consistent bookkeeping.
Force ledger. Store rotor fluid source reactions or resolved rotor wall forces, stationary body aerodynamic loads, gravity and any external modeled load in distinct categories. The total aerodynamic aircraft force sums the first two. The required trim balance then adds gravity. Blade and hub patch membership must prevent duplication; excluded components must be visible in the report.
Electrical power and energy. For positive propulsion input:
Use consistent Wh or joules and pack level specific energy. E47 is a screening equation; power rate limits, thermal derating, voltage sag, aging, reserve policy and structural integration can determine a larger mass. Battery mass changes total thrust and power, so sizing requires a coupled mass energy iteration rather than one pass.
Store motor maps, sustained torque, peak torque duration, current, bus voltage and thermal limits. The propeller aerodynamics module does not automatically model motor cooling. Regeneration and windmilling require an extended signed energy model.
The decision report must show required thrust, predicted thrust, source of performance data, body download, shaft and electrical power, energy and applicability for the same mass and atmosphere case. Do not combine best thrust from one case with best efficiency from another.
## 18 Required contours and load visualizations
A contour is a visualization of a scalar field. A pressure contour is not itself a force measurement, because force also depends on surface normal, area, viscous stress and integration. The mandatory evidence pack couples explanatory contours with integrated loads.
| Engineering question | Required visualization | Quantitative companion |
| Does the aircraft lift the mass | Signed vertical traction on all modeled aircraft surfaces | Rotor and body forces, total mass balance |
| Where does rotor thrust originate | Blade pressure difference and axial traction | T and Q histories, radial loading |
| Why is torque or power high | Tangential traction and wall shear | Shaft torque and power by rotor |
| Why does body download occur | Body pressure and vertical traction | Body vertical force by component |
| How do rotors interact | Axial velocity and swirl slices, wake structures | Per rotor T and Q changes |
| Is separation important | Wall shear vectors and signed streamwise shear | Surface loading and model sensitivity |
| Are blade tip speeds compressible | Blade relative Mach and local pressure | Max local Mach and capability decision |
| Is the near wall mesh suitable | y plus and layer coverage | Coverage and quality statistics |
| Does symmetry remain valid | Paired component and field difference plots | Full versus reduced load errors |

Release minimum. Produce dimensional pressure and axial traction maps, per rotor and total load histories, body download map, rotor center wake slices, y plus for turbulent wall cases, mesh quality evidence and a convergence panel. Pressure and traction require actual surfaces; source based rotors use volume source displays and loading profiles instead of fictitious blade contours.
Provide lift or vertical force, side force, drag in the declared flight direction, roll, pitch and yaw moments. In hover, report world vertical force rather than an undefined freestream lift coefficient.
Use surface color maps for wall fields; slices for volume fields; vector glyphs for direction; and isosurfaces for wake structure. A plot of velocity magnitude does not show upflow versus downflow. A wall pressure map does not show net torque. The next sections define each derived field and selection rule.
Every figure caption must include run ID, field, units, component or plane, frame, time treatment, color range, fidelity and validation status. Symmetry reconstruction and smoothing must be identified. Unavailable fields produce an explicit missing evidence item, not a substituted unrelated plot.
## 19 Pressure traction and moment contour definitions
For any requested unit force direction e, compute pressure, viscous and total surface contribution per area.
These fields have units N/m². Their area integral gives the force component. The discrete face force is f_A,e × A_face, in N; it is a separate field. Coloring by per face N can overemphasize coarse faces and must not replace traction density in design comparisons.
Moment contribution per area has units N m/m². Integrate to get N m. Color signed yaw, roll or pitch contribution around a declared center of gravity. For rotor shaft torque, use rotor center and axis instead. Reusing a vehicle yaw contour to infer rotor shaft power is incorrect.
In hover, freestream speed is zero, so freestream Cp is undefined. Default to dimensional pressure. An optional rotor Cp may use a declared tip speed reference, labeled explicitly and kept consistent between cases. Do not quietly insert an artificial freestream to make Cp render.
Blade pressure difference. Pair pressure and suction surfaces at corresponding chordwise and radial locations. Define Delta p = p_pressure − p_suction with mapping metadata. A positive difference can explain loading but is not generally equal to axial thrust per planform area without geometric projection. Integrate E41 for official loads.
Contour selection for thrust. Use traction.world_z for aircraft lifting contribution and traction.rotor_axial for each rotor. Show pressure and viscous decomposition where available. Accompany the contour with integrated positive and negative contributions; cancellation matters. Never infer thrust from the maximum red value or colored area alone.
Data integrity. Derive these fields from unsmoothed native face pressure, traction and normals. Display interpolation is allowed but must be labeled and cannot change official integrated numbers. Compare the sum of derived face forces with the backend load output using a declared reconciliation tolerance; investigate mismatches before issuing an accepted force report.
## 20 Velocity wake turbulence and wall contours
E51 assumes a rotor frame with no translation; include aircraft velocity when converting a moving aircraft result. Define azimuthal basis around the axis and mask its singular center. Use absolute velocity for vehicle wakes and relative velocity for blade aerodynamic conditions. In the world z up convention, downward wake velocity is negative. A rotor axial coordinate can differ; legends must state it.
Vorticity has units 1/s and Q criterion 1/s². Positive Q indicates rotation dominating strain locally; an isosurface threshold is a visualization choice, not a force or separation threshold. Use Q_v to distinguish it from torque Q. Compute gradients with the backend or a verified mesh operator. Label the velocity frame because rotating frame vorticity and Q can differ.
Normalize optional wake criteria with a fixed reference speed and length, then record them. A suggested threshold sweep may show several levels; a single automatic threshold must not be chosen because it creates the most persuasive shape. Compare matched thresholds across designs and retain the sensitivity views.
Projected wall shear can reveal reverse flow when the tangential direction is meaningful. Define that direction from local external relative flow or an approved surface coordinate; it is undefined at stagnation and some leading edge points. Mask such regions and show vector shear rather than force a sign. Negative shear is an indicator requiring context, not an automatic separation certification.
Turbulence k and eddy viscosity ratio can explain wake diffusion and model behavior. They are modeled RANS quantities, not resolved vortex energy measurements. Use y plus only at walls with applicable turbulence treatment. Pressure gradient, vorticity and Q are particularly sensitive to mesh and differentiation; keep quality plots alongside them.
## 21 Slice planes time windows and comparative displays
Define rotor slices in local coordinates using center x_i, axis a_i, radius R and a declared downstream wake direction d_i. Under normal hover d_i opposes thrust. Reverse flow or tilted cases need a case specific downstream definition.
E54 is a proposed set when thrust axis points upward and the wake runs downward. Record its sign convention. Select an upstream diagnostic plane as well, and keep the planes outside source layers or mesh interfaces when assessing undisturbed loading. The exact offsets are configurable starting locations, not guaranteed wake diagnostics.
Generate a vertical plane through each rotor center and axis; a plane connecting interacting rotor centers; world planes through the payload or center of gravity; and ground clearance slices for ground effect. Derive plane locations from geometry metadata, not axis aligned bounding box midpoint alone.
Plane validity. Verify that the plane intersects the intended fluid region and has valid samples. Mask solids, uncovered cells, invalid gradients and extrapolated points. A plane intersecting a rotating interface is permitted if its interpolation and coverage are known; it cannot silently show holes as zero velocity.
Temporal views. Use instantaneous fields for peak load and blade passage; phase averages for repeatable rotor phase studies; time averages and RMS for mean interference. Average vector components before taking magnitude when requesting magnitude of the mean. The mean of speed and the speed of mean velocity are different outputs.
Record startup discard interval, retained revolutions, rotor phase reference, bin width and sample counts. Multiple rotor speeds may lack a short common period; do not phase average all rotors using an arbitrary one rotor phase. Use separate phase references or statistically justified time averages.
Comparisons. Match mass, atmosphere, flight condition, fidelity, reference values, time treatment and selected component role. Use a common coordinate transform and compatible spatial sampling for difference plots. Moving blades must align by phase or be compared in their rotor frame. Mesh interpolation error must be visible. Do not subtract unrelated cell IDs from different meshes.
A comparison panel retains shared color limits, plane offsets, camera, component masks and averaging policy. Include raw extrema and integrated load deltas so a quiet looking contour cannot conceal a significant load change.
## 22 Deterministic automatic contour selection
Implement a field registry and rule engine before adding natural language assistance. The system selects the right evidence from the engineering question, model capability and data provenance; it does not choose a plot based on visual attractiveness.
Step 1 Define intent. Supported intents are payload lift, rotor thrust, rotor power, body download, interference, separation, compressibility, ground effect, numerical quality and symmetry comparison. A free text request maps to one or more intents through a reviewable classifier; deterministic rules then select evidence.
Step 2 Build capability manifest. Record whether the case contains blade walls or actuator sources, pressure dimensions and meaning, stress fields, velocity frame, density, gradients, phase, y plus, volume connectivity and accepted time statistics. Missing requirements block derived plots.
Step 3 Select mandatory evidence. Payload lift requires signed world vertical traction or consistent actuator reaction plus body loads, load histories and E05 balance. Rotor power requires rotor moment about its axis, signed angular speed and shaft power; tangential traction is explanatory. Interference requires per rotor load comparison and axial or swirl slices. Never substitute velocity magnitude for thrust evidence.
Step 4 Apply prerequisites. Reject Cp at zero reference speed; reject blade pressure at a source only rotor; reject averaged fields with no accepted window; reject relative Mach from absolute aircraft speed; reject y plus on a laminar or nonwall region; reject comparisons with mismatched conditions unless explicitly exploratory.
Step 5 Plan location and time. Choose assembly surfaces, local rotor planes and configured wake offsets. Select mean, phase or instantaneous treatment by intent. Validate sample coverage. A maximum load event must come from retained history with its time reference, not an arbitrary last frame.
Step 6 Set shared display policy. Choose a sequential map for nonnegative magnitude, diverging for signed contributions, and explicit invalid and out of range colors. Lock ranges across matched comparisons and animations. Preserve true extrema and clipping fraction.
Step 7 Reconcile and label. Integrate the source native fields, check against backend forces and attach run status, units and derivation. A failed force reconciliation marks the force panel diagnostic only.
Step 8 Persist recipe. Store the selection rule, field dependency graph, frame transform, surfaces, plane equations, averaging interval, colormap, limits, version and input hashes. Replaying the recipe on the same data must reproduce the figures and load table. User overrides are allowed but recorded as overrides; they cannot override missing physical data.
## 23 Field registry and plot contracts
| Canonical field | Association and unit | Dependencies | Primary use |
| pressure.static_gauge | Wall face or volume, Pa | Backend pressure definition and reference | Loading explanation |
| traction.world_z | Wall face, N/m² | Pressure, stress, normals, frame | Lift contribution |
| traction.rotor_axial | Rotor wall face, N/m² | Rotor axis and traction | Thrust distribution |
| moment_density.rotor_axial | Rotor face, N m/m² | Rotor center and traction | Shaft torque explanation |
| source.rotor_reaction | Rotor zone integral, N | Source sign and cell volume | Source modeled thrust |
| velocity.absolute_axial | Fluid cells, m/s | Absolute velocity and local axis | Wake direction |
| velocity.relative_mach | Rotor region, dimensionless | Relative velocity and sound speed | Compressibility |
| wall_shear.signed | Wall face, Pa | Stress units and tangent direction | Reverse flow indicator |
| mesh.y_plus | Wall face, dimensionless | Turbulence wall treatment | Near wall suitability |
| wake.Q | Fluid cells, 1/s² | Absolute velocity gradient | Wake structure |
| load.thrust_history | Rotor record, N | Surface or source integral | Performance evidence |

Each registry entry must specify semantic name, backend source name, association, dimensions, native frame, derivation, supported fidelities, temporal treatment, required references, valid domain and quality status. Names alone are insufficient. The same name p can mean different physical dimensions in different backends.
Derived field dependency graph. Pressure plus normals yields pressure traction; stress plus normals yields viscous traction; their sum yields total traction; direction projection yields signed force density; lever arm cross traction yields moment density. Volume gradient fields depend on mesh quality and gradient method. The graph records the operators and their version, not just an image filename.
Plot request contract. Require intent, run_ids, field_id, component_ids, association, frame, time_mode, interval or phase, location recipe, range policy, reference values and desired evidence status. Output the image or interactive data plus plot_recipe.json, integral table and warnings or unmet prerequisites.
Unsupported output. If a requested plot cannot be derived, return its exact missing dependency and an appropriate next action. Examples: export stress to obtain viscous contribution; provide Cp reference; rerun with volume fields to obtain wake slices; run a blade resolved model to obtain blade pressure. Do not invent missing fields with AI or replace them with a generically colored STL.
## 24 Color scales smoothing and plot acceptance
Use perceptually ordered sequential colors for pressure magnitude where unsigned, speed, turbulence magnitude and y plus. Use a diverging scale centered at zero for signed axial velocity, traction, moment density, shear and differences. Gauge pressure may be signed and generally benefits from a diverging map. Avoid a rainbow default that suggests artificial boundaries.
Range policies. Use shared_global for matched design comparisons, shared_temporal for animations, and single_full_range for an individual diagnostic. An optional robust percentile range can reveal detail, but must report full extrema, clipped sample fraction and out of range colors. It is not allowed to hide overload locations. In a face field, decide and record whether percentile statistics are area weighted.
ParaView supports component versus magnitude selection, custom transfer function ranges, temporal ranges and special colors for out of range or invalid values [R8]. The application should use these mechanisms through saved recipes rather than automatic per frame rescaling.
Use logarithmic maps only for strictly positive values and label them. Signed values must not be transformed by absolute value merely to allow log rendering. For a constant field, use a neutral display and the actual value; do not create an artificial color pattern. Show NaNs and missing samples distinctly from physical zeros.
Smoothing. Retain native cell or face data for integration and evidence. A point interpolated surface can be displayed for readability, but must say interpolated. Do not smooth across component IDs, pressure jumps, actuator source boundaries or rotating interfaces without a physically justified operator. Mesh decimation for browser rendering must preserve source IDs and cannot be used for force integration.
Plot acceptance tests. Check field units, selected vector component, surface membership, solid mask, reference frame, time interval, color limits, finite values, area and valid sample coverage. Recompute an integral from the plot source data and compare with the official load within the agreed conversion tolerance. Verify that identical inputs and recipe hashes reproduce the range and figure.
Keep numerical quality and validation badges visible on exports. Diagnostic plots from an unconverged run can be useful, but they cannot appear as accepted performance evidence. Rendering quality does not upgrade scientific confidence.
## 25 Software modules and interface changes
All new paths are proposals under src/physimesh. Verify exact existing interfaces against the implementation checkout before editing.
| Proposed path | Responsibility |
| drone/models.py | Versioned project schema and readiness rules |
| drone/units.py and frames.py | Dimensions, transforms and axis conventions |
| drone/stl_import.py and geometry.py | Safe STL parser, assembly tagging and repair evidence |
| drone/symmetry.py | Geometry matching and physical reduction rules |
| drone/atmosphere.py and mass.py | Consistent atmosphere and mass ledger |
| drone/propulsion.py and bem.py | Rotor maps, blade elements and applicability |
| drone/meshing.py | 3D mesh contracts and rotor zone readiness |
| drone/trim.py and allocation.py | Force moment balance and actuator constraints |
| drone/mission.py | Coupled mass and energy screening |
| postpro/loads3d.py | Native traction integrals and moments |
| postpro/field_registry.py | Semantic field and derivation contracts |
| postpro/contour_rules.py and recipes.py | Deterministic evidence selection and replay |
| solver/openfoam.py | Backend capability, generation, execution and parsing |

Extend solver/contracts.py and service.py with dimensionality, rotation, source model and temporal capabilities. Extend jobs.py and artifacts.py for durable heavy jobs, restart records and field statistics. Extend fields.py and analysis services for 3D slices, surface selection, valid masks and phase or time averaging. Preserve per unit span behavior for existing 2D force APIs.
Add browser assets for a 3D viewer and a drone setup wizard. Include units confirmation, component picking, rotor axes, symmetry planes, rotation zones, field legends, clipping and load vectors. Do not embed backend dictionary vocabulary in ordinary customer flows; advanced settings can expose the translated profile.
The 2D quadtree mesh representation and scalar conservative transfer do not directly become 3D flow adaptation. Leave them in their research workflow. Reuse campaign orchestration and quality evidence before attempting a new adaptation implementation.
Every implementation task must name the request schema, backend capability, returned artifact and acceptance fixture. A new UI button with no validated solver path is not a delivered physics feature.
## 26 Project schema API and runtime contracts
The YAML template has these required groups: identity, units and frames, mission, masses, atmosphere, assembly, rotors, flow, fidelity, symmetry, domain, mesh, numerics, boundaries, convergence, postprocessing, validation and execution. Schema versions are mandatory. Preserve unknown inputs as null; readiness fails instead of substituting guesses.
| Proposed endpoint | Input | Output |
| POST /api/drone/import | STL files, units and transforms | Assembly and topology report |
| POST /api/drone/validate | Project snapshot | Input and capability readiness |
| POST /api/drone/symmetry | Plane, assembly and operating state | Geometry match and physical eligibility |
| POST /api/drone/mesh | Immutable mesh request | Mesh ID, preview and quality |
| POST /api/drone/runs | Ready snapshot and backend profile | Run ID and evidence state |
| POST /api/drone/plots | Intent and plot recipe | Verified figures and unmet prerequisites |
| POST /api/drone/campaigns | Controlled case variations | Comparable run group |
| GET /api/drone/runs/{id} | Run ID | Lifecycle, loads, fields and provenance |

Backend protocol. probe() returns version and capabilities. validate(project) reports unsupported settings. prepare_case() returns generated files and a translated setting record. run() streams lifecycle and resources. parse() returns dimensions, native frame and raw data lineage. diagnose() evaluates evidence. export() packages results and reproducible recipes.
Require capabilities for 3D volume mesh, incompressible or compressible flow, turbulence, disk or line sources, steady rotating frame, transient interface, force integration and field export separately. A capability must include a tested fixture and supported release. Do not infer support from the presence of a binary alone.
Use a durable queue with cancellation, timeout, restart, CPU, memory and disk budgets. Keep preparation, meshing and solving separately diagnosable. Stream progress without promising a completion percentage from residual count. Long transient jobs need checkpoint artifacts and meaningful failure recovery.
Retain original CAD, project snapshots, meshes, backend configs, histories, native fields, derived field metadata, plot recipes, reports and hashes. Versioned migration must not rewrite old run evidence. Avoid storing only rendered images; future analyses need the raw fields or a declared retention limitation.
## 27 Validation campaigns and release gates
| Campaign | Purpose | Minimum retained evidence |
| Geometry fixtures | Units, topology and transforms | Known bounds, area and normals |
| Force fixtures | Pressure, stress and moment signs | Analytical versus computed loads |
| Isolated rotor stand | Rotor T, Q and power validity | Multiple RPM and relevant inflows |
| Mesh and time series | Discretization assessment | Matched physical cases and refinement logs |
| Full vehicle hover | Body download and rotor interference | Component loads and wake measurements where available |
| Symmetry comparison | Reduction eligibility | Paired field and load differences |
| Off design operation | Applicability limits | Density, crosswind, clearance and descent cases |
| Fault and derating | Feasibility under defined faults | Allocation residuals and actuator limits |

Release A. STL import, component assignment, 3D viewer, mass and atmosphere contracts, stationary 3D mesh and verified force integration. Evidence must include native units and analytical fixtures.
Release B. Measured rotor maps or BEM, calibrated actuator sources, vehicle hover interference and intent based postprocessing. A source only model must clearly state prescribed versus predicted loads.
Release C. Blade resolved steady rotating frames, then transient interfaces, phase processing and peak loads. Validate against a suitable rotor dataset and assess mesh and time sensitivity. Preserve the load and contour reconciliation checks.
Release D. Trim, control allocation, mission energy, uncertainty and constrained design comparisons. Aircraft decisions must use the appropriate fidelity and validated applicability. Structure and power systems remain separate requirements.
For measured comparisons, match geometry, pitch, atmosphere, RPM, inflow and fixture blockage. Report absolute and relative errors, measurement uncertainty and repeatability. Near zero loads use absolute scales. Validation on a small rotor does not by itself establish a large rotor with different Reynolds, Mach, blade flexibility or installation effects.
Numerical regression tests should protect transformations, conservative source totals, force integrals, temporal averaging and deterministic plot selection. End to end acceptance includes an actual backend run, not just configuration generation. Preserve current 2D tests appropriate to shared code changes. Pin reproducible environments and retain reference outputs with their provenance.
## 28 Development task ledger and engineering ownership
| Work package | Dependency | Concrete completion criterion |
| WP01 Baseline audit | Source checkout | Current interfaces and capability map |
| WP02 Schema and equations | WP01 | Validated units, mass and atmosphere fixtures |
| WP03 STL and 3D assembly | WP02 | Import diagnostics and component preview |
| WP04 Mesh and backend | WP03 | Reproducible stationary 3D case |
| WP05 Loads and registry | WP04 | Analytical force fixtures and native reconciliation |
| WP06 Rotor screening | WP02 and rotor data | Validated maps or BEM and applicability |
| WP07 Vehicle sources | WP04–WP06 | Hover interference and source bookkeeping |
| WP08 Symmetry | WP03 and WP07 | Geometric tests and full domain comparison |
| WP09 Contour automation | WP05 and WP07 | Intent rules, prerequisites and saved recipes |
| WP10 Explicit blades | WP04–WP07 | Rotating case and measured comparison |
| WP11 Transient evidence | WP10 | Time and phase validation |
| WP12 Trim and mission | WP06–WP11 | Coupled feasibility report with constraints |

Use Codex assisted roles for planning, physics implementation, numerical criticism and code review within the existing workflow. Responsibilities describe tasks, not independent certification: the physics role defines equations and assumptions; the numerical role checks discretization and convergence; the geometry role preserves CAD; the software role implements contracts; the critic role challenges evidence and unsupported claims.
AI can draft code, setup proposals and explanations. Deterministic validation checks units, schemas, capabilities and provenance. Numerical solvers and validated engineering models produce the physical outputs. No role may create a thrust number that lacks an analytical calculation, measured source or retained run.
Set development effort after WP01 and the first real STL and rotor data review. A large transient study can dominate computing costs, even with open source software. Keep a low cost screening path, but do not let budget automatically authorize low fidelity flight design claims.
Required external inputs. Actual source repository, component STL files, rotor count and geometry or maps, mass ledger, payload position, energy system, motor limits, mission duration and environment. Without them, schema and fixtures can be developed but the customer design cannot be evaluated.
## 29 Risks boundaries and evidence communication
| Risk | Consequence | Required response |
| Coarse or defective STL | Incorrect blade loading | Geometry fidelity and repair evidence |
| Incorrect unit or torque sign | Orders of magnitude or wrong power | Dimensions and analytical fixtures |
| Prescribed thrust mistaken for prediction | False payload feasibility | Source labels and fidelity rules |
| Rotor interaction omitted | Wrong thrust or download | Full installation studies |
| Symmetry incorrectly imposed | Suppressed moments or wake modes | Physical eligibility and full domain tests |
| Incorrect pressure semantics | Wrong traction and forces | Backend field definition and reconciliation |
| Auto scaled colors | Misleading design comparison | Shared ranges and saved recipes |
| Inadequate time window | Biased means or hidden peaks | Complete intervals and sensitivity |
| Unmodeled structural deformation | Different real aerodynamic shape | Load export and structural coupling plan |
| Energy mass feedback ignored | Infeasible aircraft sizing | Coupled mass power iteration |

Claims allowed. State the field, model, condition, numerical evidence and applicability. For example: predicted mean rotor thrust at the declared RPM under the tested atmosphere, with documented mesh sensitivity and validation comparison. An accepted plot must point to the exact load table it helps explain.
Claims blocked. Guaranteed 750 kg flight capability from a contour; perfect first execution; zero hallucination; validated accuracy for every STL; flight certification from CFD; lower power inferred from smoother wake imagery; or motor loss safety from summed remaining thrust alone.
AI assistance should explain missing dependencies and recommend the next controlled experiment. A numerical solver can still return an incorrect answer because of geometry, inputs, modeling or settings. The system must distinguish a trustworthy calculation chain from demonstrated physical accuracy.
Customer reports should start with mass, condition, thrust, power, margin and evidence status, then use the contour pack to explain where forces originate and what limits the result. Keep engineering assumptions accessible without exposing implementation details unnecessarily.
This module can provide dependable, repeatable aerodynamic evidence when its contracts and validation gates are met. It cannot replace the remaining aircraft engineering and qualification program.
## 30 References and equation index
The current capability baseline is the user supplied PhysiMesh Complete Project Documentation, repository reference dated 29 September 2026. The preceding Drone Physics and Project Specification establishes the initial scope. New paths, APIs, defaults and release gates in this manifest are proposed development requirements.
R1 OpenCFD snappyHexMesh documentation. STL surface based volume meshing. https://doc.openfoam.com/2606/tools/pre-processing/mesh/generation/snappyhexmesh/
R2 OpenCFD rotating fan tutorial. Rotating mesh and arbitrary mesh interface example. https://doc.openfoam.com/2212/examples/tutorials/incompressible/pimpleFoam/ami-rotating-fan/
R3 SU2 actuator disk variable load tutorial. https://su2code.github.io/tutorials/ActuatorDisk_VariableLoad/
R4 Wayne Johnson. NDARC NASA Design and Analysis of Rotorcraft Theory Appendix 1. NASA/TP-2015-218751. https://ntrs.nasa.gov/citations/20160012474
R5 Bangura, Melega, Naldi and Mahony. Aerodynamics of Rotor Blades for Quadrotors. 2016. https://arxiv.org/abs/1601.00733
R6 NASA NPARC Alliance. Examining Spatial Grid Convergence. https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html
R7 OpenCFD forces function documentation. Density and pressure handling must be verified against the selected release and source. https://www.openfoam.com/documentation/guides/latest/doc/guide-fos-forces-forces.html
R8 ParaView reference manual. Color maps and transfer functions. https://docs.paraview.org/en/latest/ReferenceManual/colorMapping.html
| Equations | Subject | Sections |
| E01–E04 | Mass, atmosphere and local flow | 4 |
| E05–E08 | Aircraft force and trim | 5 |
| E09–E16 | Rotor momentum, blade elements and coefficients | 6–7 |
| E17–E27 | Flow, turbulence and wall resolution | 8–9 |
| E28–E36 | Rotation, source models and numerics | 10, 12–14 |
| E37–E40 | Statistics and numerical uncertainty | 15 |
| E41–E47 | Traction, control volume and energy | 16–17 |
| E48–E54 | Contour fields and sampling | 19–21 |

The equations cover the declared module models and diagnostic operators. Production turbulence closures, solver algorithms and backend boundary implementations require the pinned solver source and documentation; they are not replaced by abbreviated equations in this document.
## 31 Settings register for geometry and physics
These defaults are proposed development settings. Null means required project data has not been supplied and must block the relevant run or decision. Tolerances are configurable and versioned; none of these values represents achieved accuracy.
| Setting | Initial policy | Change trigger |
| schema_version | drone_manifest_v1 | Explicit migration only |
| payload_mass_kg | 750 | Customer requirement revision |
| source_units | null | Required CAD declaration |
| world_frame | ENU with z upward | Explicit coordinate transformation |
| solid_normal | Outward into fluid | Backend patch conversion test |
| total_mass_kg and CG | null | Required ledger completion |
| rotor count and radius | null | Actual design selection |
| signed RPM and pitch | null | Per condition design inputs |
| atmosphere pressure and temperature | null | Defined mission environment |
| viscosity | null or approved property law | Atmosphere consistency |
| initial fidelity | measured map or BEM screening | Input availability and engineering intent |
| flow compressibility | capability decision from local flow | Blade Mach and physical effects |
| turbulence model | Pinned backend SST variant for RANS tests | Validation and model sensitivity |
| geometric match tolerance | User declared absolute and relative | CAD tessellation and required accuracy |
| symmetry execution | Off until eligible and compared | Full domain verification |
| ground model | Explicit per case | Actual flight clearance |

BEM extension requirements. Add radial station count, nonlinear tolerance, maximum iterations, induction relaxation, loss model and polar extrapolation policy. Starting values could be 80 radial stations, relative load residual 0.0001 and 200 iterations, followed by station and tolerance sensitivity. No station may remain unconverged in an accepted model output.
An illustrative Prandtl tip factor under an appropriate axial blade element formulation is:
Handle root, tip and zero angle limits consistently with the model. Do not multiply already corrected polars or measured rotor maps by this factor. Store the actual loss implementation and compare with data.
Control allocation extension. A local approximation maps rotor commands to aircraft wrench, but interference and tilt can make the map nonlinear. Use constrained optimization with force and moment scales, failure masks, rotor bounds, torque limits and shared electrical power. Return residual and active constraints; low optimizer objective alone is not a feasible aircraft condition.
Commands c can be RPM or pitch, only when physically available. Store weighting and normalization so forces in N and moments in N m are not combined arbitrarily.
## 32 Settings register for mesh solver and evidence
| Setting | Proposed starting value | Acceptance rule |
| mesh scales and domain bounds | null | Filled from geometry and domain study |
| first layer target y plus | 1 for low y plus strategy | Achieved distribution and model suitability |
| layer growth | 1.2 | Collision, coverage and sensitivity |
| layer count | null | Thickness and geometry dependent |
| steady iteration budget | 3,000 as resource starting cap | Cap is not convergence |
| transient rotation per step | 1 degree | Refine and compare loads |
| target Courant | 0.8 as initial target | Actual maximum and sensitivity |
| final linear relative tolerance | 0 where supported | Avoid relative early termination in final solves |
| pressure absolute tolerance | 0.0000001 initial backend value | Residual definition and balance checks |
| velocity and turbulence tolerance | 0.000001 initial backend value | Backend scale and load checks |
| outer and pressure correctors | 2 and 2 as an initial profile | Per step nonlinear sensitivity |
| startup discard | At least 5 revolutions for first inspection | Extend until startup has decayed |
| averaging window | Begin with 10 complete revolutions | Extend for drift and sampling convergence |
| load history cadence | Every time step | Peak and blade passage resolution |
| full field cadence | 5 degrees as initial choice | Volume budget and sampling need |
| force drift gate | 0.5% between consecutive windows | Component and absolute scale checks |
| continuity diagnostic target | 0.1% of declared gross scale | Consistent moving mesh balance |
| native force reconciliation | 0.1% plus absolute tolerance | Matching formulation and inputs |
| mesh and time change target | 2% in decision quantities | Local loading also assessed |
| symmetry change target | 1% with absolute scales | Eligible physical family only |

These values are not one universal CFD preset. Linear residuals depend on backend normalization; a value copied into another solver can have different meaning. Store translated settings and their definitions. Near zero moments and coefficients require absolute tolerances. Start with conservative profiles, then freeze the settings used for the accepted campaign.
Field retention. Always retain T, Q, power and component forces at high cadence. Retain wall pressure and stress, accepted wall diagnostics, and the volume fields needed for the requested contour intents. If storage limits remove raw volume fields, state which future plots cannot be reproduced. A lossy display cache cannot become the retained integration source.
Capability blocking. Null backend version or image digest, unsupported compressibility, unresolved rotation zone, invalid pressure dimensions, missing rotor loading input, unsupported wall treatment or incomplete physical boundaries blocks execution. Resource ceilings can be selected by the user, but reaching a ceiling cannot upgrade an incomplete solution.
## 33 Contour rule examples and acceptance fixtures
| Intent and available data | Automatic selection | Rejected alternative |
| Payload lift with blade walls | Mean world z traction plus force ledger | Pressure magnitude alone |
| Payload lift with disks | Integrated source reaction plus body traction | Invented blade pressure |
| Rotor power with walls and stress | Axial moment density, Q history and signed shaft power | Speed contour as power evidence |
| Hover pressure explanation | Gauge pressure in Pa | Cp using zero freestream |
| Crosswind interference | Signed rotor axial slices and per rotor load deltas | Mirror reduction without eligibility |
| Separated region | Signed shear and shear vectors with tangent validity | Negative unsigned shear magnitude |
| Two candidate designs | Matched planes and shared limits | Independent automatic ranges |
| Unconverged transient | Diagnostic instantaneous plots with status | Accepted mean thrust figure |

Fixture CT01. Two equal pressure fields must produce the same color legend under a shared recipe even if their meshes differ. Changing the camera cannot change the global comparison range.
Fixture CT02. A uniform face pressure on a closed surface has no net force; the plot may show nonzero local pressure and opposing traction. The system must display zero integrated load within numerical tolerance.
Fixture CT03. At zero hover freestream, reject freestream Cp and offer dimensional pressure. A user supplied nonzero tip reference permits a separately labeled rotor Cp.
Fixture CT04. Kinematic pressure and kinematic wall stress must convert through density once. Equivalent physical and kinematic inputs must produce matching force and shear plots. Already dimensional pressure must not be multiplied again.
Fixture CT05. A source only rotor must select source density and reaction records, and mark blade wall plots unavailable. A disk with prescribed T must label that T as an input.
Fixture CT06. Reflect an offset force and axial moment, reconstruct the partner and verify the vehicle totals. Confirm cancellation of the appropriate moment components.
Fixture CT07. A sampled peak outside the accepted averaging interval remains available as an instantaneous event, but cannot be used as the mean operating load. Phase alignment is required before a moving blade difference map.
Fixture CT08. A plot with invalid coverage must show a missing sample mask. Percentile clipping must expose the unclipped extrema and clipped area fraction. A stored recipe must reproduce the same result from the same native data.
The accompanying template contains the proposed configuration groups and starting numerical policies. The application must implement its schema and readiness rules before accepting it as executable input. Extend the equation index with E55 for tip loss and E56 for constrained allocation.