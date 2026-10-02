# Compute sizing: blocked

Task 1.4's hardened meshing fixture failed before any solving. See
[backend_pin.md](backend_pin.md) for the literal error and retained image pin.

Cell count, peak solver RAM, wall time, disk footprint, RAM per million cells,
and time per million cells per iteration are **not measured**. No scaling fit
or estimate can be reported from a failed fixture. [plan Task 1.4, M§28]

After the mount failure is diagnosed and the hardened fixture passes, run a
vendor incompressible simpleFoam tutorial and a controlled refinement of about
2x in each direction. Retain exact case changes, logs, sample timings and
resource records. The runtime image lacks /usr/bin/time; choose and document a
working measurement method rather than fabricating a peak. [VERIFY-IN-BACKEND]

Customer actuator and blade-resolved cell counts also require the actual STL
geometry (Q03). The 4 vCPU / 16 GB / 50 GB legacy profile is a 2D reference,
not an accepted 3D capacity. Release C host selection remains a client decision
(Q12). Never reduce fidelity silently to fit a budget. [M§14, M§28]
