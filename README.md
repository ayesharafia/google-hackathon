# PhysiCore Drone

Greenfield implementation of the drone module specified in [plan.md](plan.md)
and the retained manifest. Python 3.11; FastAPI orchestration; OpenFOAM solves
flow equations. Payload lift capacity is calculated from the entered design and operating case; no aircraft capacity is assumed.
[M§0, M§4]

## Setup

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock
uv pip install --python .venv/bin/python --no-deps -e .
.venv/bin/python -m pytest -q -m "not backend"
.venv/bin/ruff check .
```

Run the retained reference suite independently:

```sh
(cd reference_impl && ../.venv/bin/python -m pytest -q)
```

Backend tests need Docker and a confirmed, immutable OpenFOAM image pin.
No CFD capability or aircraft feasibility is established by unit tests. Missing
design inputs remain unknown and block dependent work. [M§2, M§26, M§27]

Work follows plan §10 in order, on a branch per work package. The separate 2D
PhysiMesh product remains untouched; integration is through the planned export
contract. [plan §2.5, §9.4]

## Run the labelled MVP demo

The retained sphere is a software verification case. The drone panel uses
synthetic example inputs and reports `screening_only`. Real aircraft geometry,
rotor performance and an approved mass ledger are still required.

Clone into a directory shared with your Docker VM (for Colima, use your home
directory rather than `/tmp`). After setup, start Docker and fetch the exact vendor tutorials for backend tests:

```sh
mkdir -p .backend/vendor/v2606
curl --fail --location https://dl.openfoam.com/source/v2606/OpenFOAM-v2606.tgz -o .backend/vendor/v2606/OpenFOAM-v2606.tgz
printf '%s\n' '2a1310e3ed192cc4c521e1d22dcc176f57bec61160c878dc4348f21d6672294d  .backend/vendor/v2606/OpenFOAM-v2606.tgz' | shasum -a 256 -c -
tar -xzf .backend/vendor/v2606/OpenFOAM-v2606.tgz -C .backend/vendor/v2606 --strip-components=1
export PHYSIMESH_OPENFOAM_TUTORIALS="$PWD/.backend/vendor/v2606/tutorials"
docker pull opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb
.venv/bin/python -m pytest -q -m backend
```

Generate the study, native-data plots and immutable evidence package:

```sh
.venv/bin/python scripts/demo_run.py --output-root .backend/demo
.venv/bin/python scripts/demo_loads.py --run-group .backend/demo/run_group.json
.venv/bin/python scripts/demo_plots.py --run-group .backend/demo/run_group.json
.venv/bin/python scripts/demo_surface.py --run-group .backend/demo/run_group.json
.venv/bin/python scripts/demo_assemble.py --run-group .backend/demo/run_group.json --data-root .backend/demo-app
.venv/bin/python scripts/demo_seed.py --data-root .backend/demo-app
export PHYSIMESH_OPENFOAM_IMAGE_DIGEST=opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb
export PHYSIMESH_DATA_ROOT="$PWD/.backend/demo-app"
export PHYSIMESH_DB_PATH="$PWD/.backend/demo/jobs.sqlite"
read -s 'PHYSIMESH_API_TOKEN?Choose a local session token: '
export PHYSIMESH_API_TOKEN
.venv/bin/python -m uvicorn physimesh.api.app:app_from_environment --factory --host 127.0.0.1 --port 8766
```

The token prompt uses zsh. In bash use `read -s -p 'Choose a local session token: ' PHYSIMESH_API_TOKEN`.
Open [the local evidence desk](http://127.0.0.1:8766/web/results.html) and enter
that token. No browser storage is used for credentials. The sphere solve took
about 16 minutes across three meshes on the audited local machine; timings vary.
Rerunning the commands reuses completed runs only after checking generated input
and retained output hashes, regenerates plots, and checks immutable package bytes.
Changed inputs or corrupted evidence are refused; select a new output root for a
new study. Keep `.backend` when transferring retained evidence, or regenerate it.

The approved design and mission snapshots use `si_numeric_snapshot_v1`: numeric
1 and 1.0 share a digest, while booleans and strings retain their types. Native
file SHA-256 hashes retain their exact byte semantics.

[QA and remaining release gates](docs/qa/results_page_checklist.md) distinguish
implemented behavior from pending independent physics review and release approval.

[Code, backend and physics guide](docs/technical/mvp-code-and-physics-guide.md) explains
the formulas, data flow, API, solver configuration, evidence checks and limitations.
