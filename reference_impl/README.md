# reference_impl: verified reference code for plan.md

**What this is:** standalone, tested Python implementations of the physics-critical, backend-independent parts of the PhysiCore Drone plan: units, frames, atmosphere, mass ledger, STL parsing, topology, symmetry, surface-load integration, rotor momentum/BEM, statistics/GCI, contour-rule engine, allocation and mission energy.

**What this is not:** it is **not** integrated with the PhysiMesh code base, which was not available when this was written. It has never run against OpenFOAM output. The project is greenfield (plan §2.1): port each module into the new repository's `src/physimesh/` in task order (plan §10).

**Verification record (2026-10-02):** `python -m pytest -q` → **118 passed** on Python 3.9.6, NumPy 1.26.4, SciPy 1.13.1, pytest 8.3.4, FastAPI 0.128.8 (the 3 API tests need FastAPI + httpx; the other 115 need only NumPy/SciPy/PyYAML).

```bash
cd reference_impl && python3 -m pytest -q
```

**Rules for porting (from plan.md §0):**
- Port the tests first, unchanged in their expected values. If a test seems wrong, stop and report. Never edit an expected value to make code pass.
- Keep every `[M-Exx]` docstring tag.
- Test fixture models (thin-airfoil polar, kT·Ω² rotors, mass–energy toy cases) are **test fixtures only**. They must never appear in client deliverables as predictions.

| Module | Plan task | Tests |
|---|---|---|
| `src/physimesh/core/artifacts.py`, `jobs.py`, `container.py` | 1.2 | `tests/core/test_artifacts.py`, `test_jobs.py`, `test_container.py` |
| `src/physimesh/api/settings.py`, `app.py` | 1.5 | `tests/api/test_app.py` |
| `src/physimesh/drone/provenance.py` | 2.1 | `tests/drone/test_wp02_foundations.py` |
| `src/physimesh/drone/units.py` | 2.2 | same |
| `src/physimesh/drone/frames.py` | 2.3 | same |
| `src/physimesh/drone/atmosphere.py`, `mass.py` | 2.4 | same |
| `src/physimesh/drone/stl_import.py`, `geometry.py` | 3.1, 3.2 | `tests/drone/test_wp03_stl_geometry.py` |
| `src/physimesh/postpro/loads3d.py` | 5.1–5.4 | `tests/postpro/test_wp05_loads.py` |
| `src/physimesh/drone/propulsion.py`, `bem.py` | 6.1–6.4 | `tests/drone/test_wp06_rotor.py` |
| `src/physimesh/drone/symmetry.py` | 8.1–8.3 | `tests/drone/test_wp08_symmetry.py` |
| `src/physimesh/postpro/contour_rules.py` | 9.2, 9.3 | `tests/postpro/test_wp09_wp11_postpro.py` |
| `src/physimesh/postpro/statistics.py` | 11.1 | same |
| `src/physimesh/drone/allocation.py`, `mission.py` | 12.1–12.3 | `tests/drone/test_wp12_trim_mission.py` |
