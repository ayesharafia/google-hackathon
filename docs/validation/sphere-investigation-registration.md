# I01/I02 investigation registration, 5 October 2026

Registered before new investigation executions. Existing retained sphere results,
sampling protocols, acceptance thresholds and four refused slices remain unchanged.
Neither experiment upgrades aircraft evidence or attributes the retained +2.65%
correlation gap to a cause. Independent interpretation review remains required.

I01 uses the pinned OpenCFD v2606 image
`opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb`.
Copy a newly run 20-iteration coarse sphere into an isolated directory, preserving
its mesh and fields. Probe the native `sets` function with a `cloud` of 25
explicitly supplied regular-plane points (x=0.6:0.5:2.6 m, y=0, z=-0.5:0.25:0.5 m),
`cellPoint` interpolation, raw format, p/U/vorticity. This tests sampling at
provided grid coordinates, not native plane-mesh conversion or scientific accuracy.
Retain dictionary, ordered coordinates, exact source-field hashes, all raw output,
log and recipe hashes. Accept capability only if outputs contain the requested
coordinates and finite signed scalar/vector columns; otherwise retain the refusal.
Budget: 2 cores, 4 GiB, 512 PIDs, no network, read-only root, 120 s wall,
1 GB new outputs. No full steady solve or three-grid eligibility campaign here.
Independent interpolation/direction/refinement validation remains a later gate.

I02 is a prospective controlled campaign, not an executed result. Use the existing
origin-centred D=1 m STL, Re=100, U=(1,0,0), nu=0.01, rho=1,
Aref=pi/4, laminar steady model, positive-x drag and the retained stopping policy.

| Arm | Domain | Background divisions | Surface level | Controlled change |
|---|---|---|---|---|
| A | (-10,-10,-10) to (30,10,10) | (144,72,72) | (4,4) | Reproduce fine reference recipe |
| B | (-20,-20,-20) to (60,20,20) | (288,144,144) | (4,4) | Twice extent with identical background cell spacing and surface refinement |
| C | Same as A | (144,72,72) | (5,5) | Surface refinement at fixed domain/background |
| D | Same as B | (288,144,144) | (5,5) | Interaction, only if B/C resource checks permit |

Do not change STL faceting, fluid properties, normalization, solver numerics,
loads definition or stopping thresholds between arms. Record mesh quality and
near-body cell distributions; identical prescribed refinement does not guarantee
identical realized mesh. Run each arm twice with fresh roots. Retain raw
pressure/shear/loads, six-component native reconciliation, last-two-window drift,
residuals, iteration counts, Cd, slice provenance, wall time, peak RAM and CPU.
Compare B-A and C-A and qualify interactions. A smaller correlation difference
alone is not proof of greater physical accuracy.

Provisional development ceiling: 2 cores, 8 GiB, 512 PIDs, 20 GB per arm,
3600 s per execution; campaign ceiling 8 executions / 8 wall hours / 160 GB.
Preflight predicted cells and available disk/RAM before launching; terminate
budget overruns and preserve unresolved outcomes. These are proposed experiment
budgets, not capacity estimates. The campaign remains unrun until the reference
input/output bundle is reproduced and an independent reviewer accepts its
controlled protocol; current main's empirical gap remains unassigned.
