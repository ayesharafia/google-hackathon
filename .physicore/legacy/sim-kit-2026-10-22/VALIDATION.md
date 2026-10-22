# VALIDATION.md : How We Know the Physics Is Right

This is what "industry standard" means in simulation. Serious simulation companies follow the idea of **V&V (Verification and Validation)**, formalized in standards like **ASME V&V 20** (CFD and heat transfer) and **ASME V&V 10** (solid mechanics), plus the **NAFEMS** benchmark collections.

Two simple ideas:
- **Verification** = "Did we solve the equations correctly?" (a math/code question)
- **Validation** = "Are these the right equations for the real world?" (a physics question)

You do not need to understand the physics to run this. You need to see green or red.

## The Verification Ladder (every feature climbs this)

| Level | Check | Plain meaning | Pass looks like |
|---|---|---|---|
| L0 | Units and sanity | No negative temperatures in Kelvin, no mass appearing from nowhere | Automated asserts pass |
| L1 | Conservation | What goes in = what comes out + what is stored (mass, energy, charge) | Imbalance below 0.1% (set per spec) |
| L2 | Analytical solution | Compare against a case with an exact math answer | Error within tolerance |
| L3 | Mesh convergence | Make the grid finer; the answer should settle down, not jump around | Grid Convergence Index (GCI, Roache method) reported, error shrinks at expected rate |
| L4 | Published benchmark | Compare against well-known reference results | Within published tolerance |
| L5 | Cross-code | Same case in a trusted open-source tool gives same answer | Within agreed % |
| L6 | Experimental data | Compare against real measurements | Within measurement uncertainty |

**Ship gate:** a feature needs L0 to L4 minimum. L5/L6 before telling customers it is "validated".

## Benchmark Catalog (starting point; agents must verify each reference before using)

### Fluids / Turbulence (drone, data center)
- Lid-driven cavity flow (Ghia, Ghia and Shin, 1982) : basic incompressible solver check
- Laminar flow past a cylinder at Re = 100 : vortex shedding frequency (Strouhal number about 0.16 to 0.17)
- Backward-facing step (Armaly et al., 1983) : flow separation and reattachment length
- Taylor-Green vortex : energy decay, checks numerical dissipation
- Turbulent channel flow DNS (Moser, Kim and Mansour, 1999) : turbulence model check
- Rotor/propeller: momentum theory and blade element theory for hover thrust, plus measured propeller datasets (for example the UIUC propeller database)

### Thermal
- 1D steady conduction through a wall : exact linear temperature profile
- 1D transient conduction, semi-infinite solid : exact erfc solution
- Natural convection in a square cavity (de Vahl Davis, 1983) : Nusselt numbers
- Conjugate heat transfer (solid + fluid) : flat plate correlations

### Data center
- Uses the fluid + thermal cases above, then system checks: total heat load in = heat removed by cooling (L1 at room scale)
- Report against ASHRAE TC 9.9 thermal guidelines (rack inlet temperature ranges)

### Battery
- Single Particle Model (SPM), then Doyle-Fuller-Newman (DFN) model
- Cross-code against **PyBaMM** using a published parameter set (for example Chen 2020)
- Thermal: heat generation (Bernardi equation) energy balance; lumped model vs. measured temperature rise

## Rules
- Reference data files go in `validation/reference/` with source citation in the filename or header.
- Tolerances are set in the spec and approved by the scientist. Agents cannot change them.
- Every validation run produces a plot: our result vs reference, on the same axes. If the lead can see the lines overlap, it passes the eye test too.
