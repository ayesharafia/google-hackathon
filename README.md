# PhysiCore Drone

Greenfield implementation of the drone module specified in [plan.md](plan.md)
and the retained manifest. Python 3.11; FastAPI orchestration; OpenFOAM solves
flow equations. The 750 kg requirement is carried payload, not takeoff mass.
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
