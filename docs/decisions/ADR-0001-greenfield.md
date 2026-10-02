# ADR-0001: Build the drone application in a new repository

Date: 2026-10-02. Status: accepted by the workspace user; client sign-off
remains open as plan Q01.

The PhysiMesh source is unavailable. The user chose a greenfield application
(plan §2.1), and authorized implementing the plan task by task. Retained
reference implementations supply tested development fixtures, not solver or
client validation evidence.

This deviates from the manifest instruction to extend existing PhysiMesh
orchestration and reporting [M§0]. Keep Python, the physimesh package layout,
SQLite jobs, filesystem evidence, and hardened container execution so later
integration remains possible. Do not alter the separate 2D SU2 product.

Integration follows plan §2.5: export load_cases.json, propulsion_map.json,
recipes and hashes through a future run-export ZIP endpoint. A later merge maps
core services onto the legacy platform once its source is available. The CFD
engine remains established OpenFOAM; greenfield does not mean writing a flow
solver [M§0, M§1].

Unknown vehicle values remain null. Software tests do not establish that a
vehicle can carry the payload [M§2, M§26].
