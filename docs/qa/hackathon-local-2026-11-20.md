# Local hackathon verification — 20 November 2026

## Checkout and runtime

- Repository: `https://github.com/PhysiCoreEngine12/Drone-Project.git`, branch `hackathon`.
- Base revision: `df3a407e1574e885a5bb9130885e68ddd4c47505`; changes remain local and uncommitted.
- Isolated checkout: `C:\Users\aishr\Downloads\Drone-Project-main\Drone-Project-hackathon`.
- The original source folder was an archive without Git metadata; its parent Git repository belongs to a different project. Neither was edited. No changes to `main` or `validation/drone-trl4`.
- Read `AGENTS.md`, `.physicore/AGENT_POLICY.md`, resume state and the API/workbench verification skill.
- No existing workspace virtual environment or Python 3.11 installation was found. Provisioned Python 3.11.18 under ignored `.backend/python` and `.venv`; installed `requirements.lock`, editable project/dev dependencies and Playwright. Used installed Chrome. Subsequent checks reuse this environment.
- Dependency check: 49 installed packages compatible. The lock omits cryptography declared in pyproject; editable installation resolved it. Added the previously undeclared `mpmath` test dependency to the dev extra.

## Running locally

Open **http://127.0.0.1:8768/web/hackathon.html**.

The server uses `physimesh.api.app:app_from_environment --factory`, local mode,
loopback binding, `PHYSIMESH_PUBLIC_ACCESS=0`, and `.backend/local-hackathon`
for private application data. A randomly generated development token is retained
in `.backend/local-hackathon/dev-token.txt` (ignored by Git). The intake page
does not require a token; use that file's value to connect the advanced workbench.
The token is not embedded in frontend assets or this report. Files remain subject
to the workstation's existing filesystem permissions; no OS access controls changed.

To restart after stopping the existing server, from this checkout in PowerShell:

```powershell
.\scripts\start_hackathon.ps1
```

The launcher reuses the environment, data and token without reinstalling packages.
The background server started during verification writes logs to
`.backend/local-hackathon/server.stdout.log` and `server.stderr.log`.

## Fixes

1. Reject STL preview data with zero/incomplete triangles or nonfinite coordinates. Keep previously accepted geometry after rejection.
2. Clear the file input after selection so the same STL can be retried after selecting units or correcting an import error.
3. Avoid POSIX-only directory fsync on Windows, which previously crashed authenticated saved STL import with missing `os.O_DIRECTORY`. File fsync, atomic hard-link publication, first metadata and existing-byte integrity checks remain intact; POSIX directory syncing is unchanged. Windows directory-entry power-loss durability is **not qualified**.
4. Declare `mpmath` in development dependencies and provide a repeatable browser check and PowerShell launcher.

No equations, physical acceptance criteria, flight-critical logic or solver implementation changed.

## Actual verification

- Chrome browser check: `python scripts/qa/verify_hackathon_browser.py` passed against the real local server, with no JavaScript page errors. Tested all five aircraft selections, objective defaults, example/invalid mission inputs, required STL units, four-triangle synthetic geometry/WebGL preview, explicit role assignment, preflight, unsupported CFD, results refusal, JSON download, original-byte SHA-256, empty/nonfinite STL rejection, preserved previous geometry, unit-change clearing and same-file retry. Advanced workbench loads.
- Desktop 1440×1000 and phone 390×844 screenshots inspected; no horizontal page overflow. Captures: `.backend/browser-qa/desktop.png`, `mobile.png`. Export: `.backend/browser-qa/intake.json`. No native assistive-technology or full accessibility audit claimed.
- Live HTTP: frontend 200; unauthenticated `/api/drone/import` 401; authenticated synthetic sphere import 200 (`read_ok`, 80 triangles).
- **109 passed**, one Starlette/httpx deprecation warning, 26.63 seconds:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/api/test_app.py tests/core/test_artifacts.py tests/drone/test_api_import.py tests/drone/test_autonomous_cfd_hackathon.py tests/drone/test_wp03_stl_geometry.py tests/drone/test_screening.py tests/drone/test_mission.py tests/projects/test_local_projects.py tests/projects/test_local_studies.py --tb=short
```

- **118 passed**, one deprecation warning, 10.75 seconds: from `reference_impl`, `..\.venv\Scripts\python.exe -m pytest -q --tb=short`.
- **362 passed, 1 skipped, 0 failed**: set `PYTHON` to the absolute `.venv/Scripts/python.exe`, then `node --test tests/web/*.mjs`. These are implementation regressions, not independent scientific review.
- Changed Python files pass Ruff; `git diff --check` passes. Repository-wide Ruff reports **32 issues in unrelated existing files**; these were not silently fixed.
- Logs are retained under ignored `.backend/`: `final-tests-host.log`, `reference-tests-isolated.log`, `node-tests.log`, `ruff.log`.

## Failed attempts and boundaries

- Initial broader Python collection failed for missing `mpmath`; corrected dependency setup. Initial Node run: 189 passed, 3 failed, 1 skipped because `python3` was unavailable; explicit `PYTHON` resolved this.
- The broad Drone/projects run was interrupted after early failures; a stop-on-first-failure run reproduced the Windows `O_DIRECTORY` defect (1 failed, 12 passed). The full broad suite was **not completed**. The final 109-test selection covers the changed storage and relevant existing workflows.
- After the Windows guard, sandboxed tests reported 18 failed/91 passed because the sandbox denied hard-link creation. The same 109 tests passed outside the sandbox; atomic publication was not weakened to bypass this restriction.
- An intermediate browser check used the wrong expected heading text; corrected to the actual “No solver results available” and reran successfully.
- A usage-limit approval-review failure temporarily blocked a check; work resumed after the user's reset. No remaining approval block.
- No OpenFOAM/CFD solver run, grid-independence automation demonstration or real-aircraft validation was performed. The hackathon frontend is an intake/preview/preflight/export prototype, with `NOT_SIMULATED` exports. Synthetic numerical grid tests do not establish solver execution.
- Geometry preview is local to the browser; JSON contains metadata/hashes, not STL source bytes. Refreshing the intake page loses unsaved entries. Use the existing workbench for saved projects.
- Hosted services, Docker execution, complete repository test suite, Windows crash recovery and flight qualification remain unverified.

## User-supplied aircraft icons
Replaced the five existing configuration symbols with CSS-clipped icons from the supplied icons.png, retaining the original image bytes in web/assets. Browser flow passed again with no page errors; inspected the selector capture at .backend/browser-qa/aircraft-icons.png. No configuration or physics behavior changed.

## Simplified mission form
Removed Advanced engineering inputs and moved the existing objective choices into Analysis focus below the four mission fields. Removed fields export as null and remain missing in preflight; illustrative examples populate mission values only. Real Chrome flow passed with no page errors, and exported null engineering values were checked. No solver or physics changes.

## Analysis disciplines
Added Full analysis (Aero, Propulsion & Structure), with individually selectable Aero, Propulsion and Structure focuses. Preflight lists the requested disciplines and missing evidence; no solver integration is implied. Chrome checks exercised every new selection and its downloaded JSON, retaining NOT_SIMULATED. Existing focus choices remain available.

## Simple workflow replacing the old-workbench handoff
Added /web/simple-workflow.html with Configure, Review and Export stages. The hackathon page's workbench entry links now open this new workflow. No project setup or legacy workbench/evidence navigation is required within it. A fresh workflow starts blank; edits persist between its steps, and JSON includes workflow=simple_analysis. Original STL bytes are not embedded; drafts remain browser-session state. Verified the entry link, three stages, exact input review, edit/back preservation, JSON download, reset and 390px phone layout using scripts/qa/verify_simple_workflow.py. No project API requests or browser errors occurred. Reviewed desktop and phone captures in .backend/browser-qa/simple-workflow. Existing hackathon browser regression also passed. Solver execution remains unavailable.

## Existing backend component calculations connected

The simple workflow now exposes optional stateless component panels in Review:
- Aero: existing `/api/drone/fixed-wing/screen`, supplied-coefficient screening for fixed-wing configuration only.
- Propulsion: existing `/api/drone/hover-bemt/evaluate`, experimental isolated-hover rotor, not cruise propulsion or motor/battery performance.
- Structure: existing `/api/drone/cantilever/screen`, ideal prismatic rectangular cantilever, not STL/FEM or aircraft structural qualification.

No backend equations, thresholds or routes changed. Inputs start blank, remain separate from mission/STL data, and require explicit source/applicability declarations. The existing local session API protects calculation access; the token is neither stored in localStorage nor exported. Editing main inputs, component data, or changing connection clears affected results and invalidates late responses. Output schemas, echoed inputs, status, units, evidence labels, and finite scalar/vector values are checked before displaying or retaining results. Result downloads preserve the exact API response text. Intake exports include these independent records while retaining NOT_SIMULATED for the aircraft and zero CFD runs.

Verification: `python scripts/qa/verify_simple_calculations.py` exercised three real local API computations using labelled synthetic fixtures, authentication, exact downloads, independently recomputed Python hashes, lift=7500 N, cantilever tip deflection=0.0000215 m, edit invalidation, delayed response and disconnect. Browser checks confirm no project API requests. First harness assertion used original Python float formatting rather than the JSON request representation; corrected the hash check to use echoed request values (which match the submitted values), then passed. Desktop/phone captures and exact synthetic results are in `.backend/browser-qa/calculations`.

`python -m pytest -q tests/drone/test_fixed_wing.py tests/drone/test_fixed_wing_application.py tests/drone/test_cantilever.py tests/drone/test_cantilever_application.py tests/drone/test_hover_bemt_request.py tests/drone/test_hover_bemt_application.py --tb=short`: **292 passed**, one existing Starlette/httpx warning, 52.43 seconds. Log: `.backend/component-tests.log`. Existing simple-workflow and hackathon browser regressions passed. Changed Python QA scripts pass Ruff; JavaScript syntax checks and diff whitespace checks pass.

These component checks supersede the earlier statement that no calculations are connected to the simple page. They do not constitute coupled Full analysis, actual CFD, automatic grid independence, STL-based structural analysis, physical validation, or flight approval. The live server remains bound to 127.0.0.1:8768 on hackathon.

## Simplified outcome
Replaced the simple workflow's final checklist with a plain-language Flight outcome and reasons. The current truthful outcome is NOT_DETERMINED: component calculations cannot establish actual flight success/failure. Backend refusals are retained as failed-check reasons, cleared on edits, and included in the exported flight_assessment. Browser tests verify an all-components-computed result still cannot claim flight success and a refused structural check appears with its reason. Both simple workflow and live component browser checks passed; phone outcome screenshot inspected. No scientific acceptance gates changed.

## Outcome-only screen
Removed Next action and Download analysis from the simple workflow's outcome screen at the user's request, leaving the outcome and reasons full-width. Shared handlers tolerate absent export/action elements; the original hackathon export remains available. Updated browser check passed for navigation and absence of both removed controls; desktop screenshot inspected.

## Fixed-wing run module and current-mission defaults

Read the user's existing in-app tab without reloading or changing its uploaded STL. The observed mission was payload 300 kg, altitude 1000 m, speed 70 m/s and duration 15 min, with Fixed-wing/Aero selected. These values are now the simple-workflow defaults. Added a fixed-wing-only setup entry that opens the existing aerodynamic panel; its submit button is labelled Run simulation with its supplied-coefficient screening scope explicitly shown. The panel itself is hidden for other aircraft, and the existing submit eligibility guard remains. Airspeed is read-only in that model and follows the editable mission speed. Other model inputs remain blank and explicit.

In a separate in-app test tab, verified defaults, switching to Multirotor hides setup, switching back restores it, and setup opens the correct panel. Ran the actual backend at mission speed 70 m/s with labelled synthetic wing/coefficient inputs: SCREENING_COMPUTED, dynamic pressure 2940 Pa, lift 14700 N, drag 880.4472079313576 N. This is component screening, not flight approval or a CFD run. Original user tab/geometry left intact. JavaScript syntax, changed QA-script Ruff and diff checks passed. Updated browser automation scripts for defaults/visibility/speed binding; those scripts were not rerun in this increment (verification used the in-app browser).

## Independent airspeed — 21 November 2026
Removed mission-speed copying and the read-only restriction from fixed-wing airspeed. Airspeed starts blank and is explicitly entered relative to surrounding air. Mission edits invalidate results but preserve the independently entered airspeed. Browser regression passed with mission speed 70 m/s and aerodynamic airspeed 50 m/s; after changing mission speed to 80 m/s, airspeed remained 50 m/s. Real coefficient screening and exact result hashes passed. First test expected text 50 rather than the entered 50.0; corrected the assertion and reran successfully. No backend equations changed.
