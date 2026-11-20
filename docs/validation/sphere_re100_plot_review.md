# Native sphere plot review

VERIFICATION CASE: sphere Re=100. These are visual sanity observations, not
acceptance criteria. No numerical inputs were tuned from a picture.

Produced 15 plots using `scripts/demo_plots.py`: pressure, speed and y-vorticity
on all three meshes; fine vectors and in-plane streamlines; wake profiles;
Cd histories; fine residuals; mesh Cd with frozen reference and qualified GCI.
Every PNG has a JSON recipe, array hash, PNG hash and verified native source
hashes. Regeneration verifies the retained execution record and source bytes.

The gallery contact sheet and full-size fine pressure, streamlines and mesh
plots were visually inspected on 2026-10-02. Front stagnation pressure is
positive. The velocity view shows a downstream low-speed wake. Fine in-plane
streamlines show paired recirculation behind the sphere. Native wake-axis
minimum Ux is negative on each mesh: coarse -0.1078546, medium -0.1177961,
fine -0.1187954 m/s. Shared legends allow honest mesh comparison.

Masking keeps the sphere interior grey rather than assigning a false zero.
XY/bar backgrounds were lightened after inspection to improve contrast.
Captions, axis labels, legends and extrema were checked at full image size.
The plotted extrema are extrema of the rendered, interpolated view, not the
whole native volume. The captions identify visualization interpolation.

## Native plane coordinate caveat

OpenFOAM raw samples requested on y=0 contain small y deviations near the
surface: maximum absolute values coarse 2.532574e-6, medium 9.278716e-6,
fine 4.702166e-6 m. The cause is not established here. Retain those coordinates,
record their extrema, and accept a declared 1e-5 D tolerance solely for visual
projection to x,z. Reject larger deviations. Captions say nominal y=0 and
state the bound. Nothing is presented as an exact 3D particle trajectory.

Plot artifacts are local under `.backend/demo-load-history/plots/`; replay
commands regenerate them from the retained native runs. `index.json` lists
recipes and hashes. This record does not raise evidence above unverified.
