# AI capability map

Source inspection: 26 October 2026, application baseline main `5de743c`.
Status: first foundation implemented locally; later domain adapters remain planned. This map
supports the [revised foundation design](../superpowers/specs/2026-10-26-ai-native-foundation-design.md).

The goal is complete product coverage through one action registry. The MCP tools,
workbench controls and optional model adapters use the same domain handlers.
Transport endpoints are evidence of existing features, not agent permission or
proof that a feature is pure, asynchronous, hosted or scientifically qualified.

## Domain coverage

| Domain | Existing evidence | Proposed actions/resources | Delivery |
| --- | --- | --- | --- |
| Contracts and discovery | `src/physimesh/api/contracts.py`, `api/settings.py` | Capability catalog, schemas, units, model regimes, mode/availability metadata | Foundation |
| Workspace and projects | `api/projects.py`: `projects`, `create`, `project`, `register_project`; `projects/service.py` | Project list/read and scoped context; project creation is not exposed to one-project grants | List/read foundation; creation later |
| Design authoring | `projects/service.py`, `projects/sqlite.py`, `platform/postgres.py`; `web/js/input-editors.js` | Draft schema/read, typed proposal/apply/undo with expected version/hash | Foundation for payload/duration/existing mass/CG; remaining fields follow |
| Input inspection | `api/projects.py`: `inspection`; `drone/authoring.py` | Separate mass/pack/case readiness evidence with missing inputs and exact draft binding | Foundation |
| Revisions | `api/projects.py`: `freeze`, `revision`, `history` | Explicit freeze, immutable revision read and paginated history | Foundation (revision read; broader history later) |
| Studies | `projects/studies.py`; `api/projects.py`: `run_study`, `study`, `study_summary` | Run existing eligible model on frozen inputs; exact result/summary/trim/energy resources | Foundation |
| Jobs | `platform/jobs.py`; `api/projects.py`: `jobs`, `job`, `cancel_job`, `retry_job` | Recorded status/attempts, explicit cancel/retry and mode limits | Foundation, hosted only |
| Comparisons | `api/projects.py`: `compare_studies`; `projects/studies.py` | Compare retained studies, input changes, outcomes and comparison limitations | Foundation |
| Exact evidence export | `api/projects.py`: `export_study` | Authorized artifact handle for exact retained JSON, identities and limitations | Foundation |
| Geometry | `drone/api.py`: `import_stl`; `api/projects.py`: `geometry`, `project_geometry_source`; `projects/geometry.py` | Staged upload handle, declared units, import inspection, reviewed attachment/transforms/removal | Domain expansion |
| Rotor sources | `projects/performance.py`; `api/projects.py`: `import_map`, `source`, `condition_source` | Import/read declared source, conditioning proposal, explicit compatible rotor/case binding | Domain expansion |
| Tabular library | `api/source_library.py`, `projects/source_library.py`, `projects/tabular.py` | Upload inspection/mapping preview/save, list/detail/original/reuse, exact conversion/row evidence | Domain expansion |
| Battery and mission | `web/js/input-editors.js`, `advanced-editors.js`; `drone/authoring.py`, `contracts.py` | Typed existing authoring groups, case/segment edits and deterministic consistency checks | Domain expansion |
| PDF and review pack | `api/projects.py`: `pdf_study`, `review_pack`, `prepared_study_pdf`; `projects/review_pack.py` | Explicit artifact preparation, existing report job/result, authorized download | Domain expansion |
| Collaboration | `platform/api.py`, `platform/identity.py` | Scoped member/invitation workflow and review preparation/history | Domain expansion; final human decisions remain trusted interactions |
| In-app AI conversation | No current model integration | Replaceable provider adapter using the action registry; selected context and actual usage | After foundation |
| Application development | No current code runner | Owner task scope, source read, isolated patch/checks, new review branch and exact evidence | Separate owner adapter stage |
| Operations and release | `api/app.py`: `health`, protected metrics; deployment files | Sanitized health/build metadata; separately authorized release workflows | Planned; release separately scoped |

## Important effects and exclusions

- `GET /projects/{id}/jobs/{job_id}` calls existing `accept_publication`.
  Describing the action as a pure read would omit accepted-result materialization.
- PDF/review-pack reads can generate/retain a PDF or enqueue a report job. Model
  tool effects must describe that operation rather than inheriting a GET hint.
- Hosted/local study execution and job availability differ. Return actual mode
  and accepted job/result identity. Never fabricate a durable local job.
- Source-library inspect/preview/save share a handler but have different effects.
  Every proposed action needs its own schema, policy and effect classification.
- Current HTTP POST project authorization would deny an MCP-encoded read to a
  viewer if copied mechanically. The shared gateway must authenticate first and
  apply each registered action's actual resource capability.
- Authoring, source binding and geometry attachment partly live in browser
  helpers today. These need typed server operations and behavioral parity checks;
  they are not already available as domain commands merely because draft saving
  exists. Human-only raw snapshot saving remains separately authorized.
- Global legacy results/plots/surfaces/screening have no sufficient hosted tenant
  ownership contract. Do not expose their raw hashes as an alternative route
  around project-bound evidence. Any future adapter needs an explicit owner/scope
  model; current project evidence remains the supported route.
- Login/password/session management, credential issuance/rotation, final human
  scientific acceptance and owner confirmation are trusted interaction flows.
  They are not model-callable approval or credential-reading tools.
- Upload actions accept staged, permission-bound upload handles or explicit file
  bytes within configured limits. Arbitrary host paths and arbitrary URL fetch
  are excluded. Retain original bytes, declared units and source identities.
- Runtime code development, GitHub publishing, main merges, infrastructure,
  deployment and physical-model changes have separate capabilities and limits.
  A project access token never implies operator authority.

## Foundation example

An authorized AI client can discover schemas, list accessible projects, read a
saved draft, inspect missing inputs and prepare a user-requested edit. A trusted
human approves its exact action binding. The client applies it once, reads the
receipt, freezes the saved design and requests an existing eligible analysis
under separately approved action authority. It reads actual results, compares
retained studies and exports evidence. A request for an unimplemented adapter
receives a clear unavailable reason; it is never reported as completed.

The foundation can be verified using a real MCP SDK client without activating a
paid model. Natural-language planning quality needs separate live-model evidence.
