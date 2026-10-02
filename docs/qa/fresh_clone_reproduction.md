# Fresh-clone reproduction, 2026-10-02

Cloned `https://github.com/PhysiCoreEngine12/Drone-Project.git`, branch `mvp/3day`,
commit `58a95964b8b6b00d44bc3591981e6139e35cb2f0`. Installed Python 3.11 dependencies
from the committed lockfile and the package editable with no dependency changes.
Unit suite: 285 passed. Ruff passed. Verified vendor archive SHA-256:
`2a1310e3ed192cc4c521e1d22dcc176f57bec61160c878dc4348f21d6672294d`.

The first `/tmp` location was not shared by Colima. Backend cases reported missing
controlDict inside the bind mount, and the first demo coarse run failed. Failed
evidence was preserved. The checkout was moved under the shared workspace at
`.backend/repro-clone`; editable installation was refreshed. All three pinned
backend fixtures then passed in 19.51 s. README now documents this mount condition.

The driver used its default ordered coarse, medium, fine set and 3000 iteration
cap. Every case stopped at 812. All reported Mesh OK.

| Mesh | Cells | Wall seconds | Peak bytes | Cd |
|---|---:|---:|---:|---:|
| Coarse | 80,473 | 58.983535 | 210,419,712 | 1.1468925753419967 |
| Medium | 251,192 | 335.894182 | 636,342,272 | 1.1249130055212535 |
| Fine | 804,280 | 829.899842 | 2,151,305,216 | 1.1206201832165152 |

The Cd values match the original retained study exactly. All force/moment/Cd
reconciliations and complete-window drift checks passed. Effective ratios,
observed order and qualified GCI match the original. Evidence stays unverified.

Fresh group SHA-256:
`ffb5d252c9b9155fbc0040b13f4aa94f2694fe2973645a8f689651fcac0a8bfc`.
Fifteen plots and a 39,816-triangle native face-constant surface were generated.
`demo_assemble.py` published `results/ffb5d252c9b9155f` into the clone's data root.
`demo_seed.py` retained the labelled synthetic input records.

Repeating `demo_run.py` verified generated input hashes and every native output
byte hash, reused completed CFD runs and regenerated loads/plots/surface.
Repeating assembly succeeded against the existing immutable package, proving
identical published bytes in this environment. This is a command reproduction
check, not a timed narrated presentation rehearsal.

FastAPI TestClient checked the actual fresh package: unauthenticated access 401;
authenticated results 200 and numerical_checks_passed/unverified; export 200,
2,577,760 bytes, all 33 manifest-listed members matching SHA-256. Complete
screening returned 52.232730994123955 kg, screening_only, and missing climb inputs
returned no headline. The httpx TestClient deprecation warning remains.

The original browser-facing package remains separate and preserved. Its actual
Brave ZIP download was found in Downloads: 2,576,790 bytes, all 33 listed members
matching SHA-256, evidence unverified/review pending. Execution timing, job IDs
and group hashes differ between studies even when Cd is identical.

Independent physics/product reviews, two timed presentation rehearsals and a
backup screen recording remain release gates. No aircraft capability is inferred.

## Linux CI portability follow-up

Manual workflow 37047160696 on 8a35d02 fetched and verified the vendor archive,
but all backend fixtures failed while writing the Linux runner-owned bind mount.
The image's default root process had all capabilities dropped and did not own
those files. The inspected pinned `/openfoam/run` documents numeric `--user` and
nss-wrapper support. Docker arguments now set the host caller's POSIX UID/GID,
with all existing isolation/resource limits retained. A unit regression verified
UID 1001 / GID 123; local 285 unit and 3 backend tests passed after the change.
Software follow-up review found no actionable issues.

[Manual GitHub workflow 37047628955](https://github.com/PhysiCoreEngine12/Drone-Project/actions/runs/37047628955)
on 73ee812 passed unit, lint and all three actual pinned backend fixtures on Linux.
The push workflow also passed. This records Linux execution capability, not an
independent physics review or an aircraft validation result.
