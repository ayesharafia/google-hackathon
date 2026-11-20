# PhysiCore Drone: v3 resume state

## Local hackathon verification: 20 November 2026

- User requested local frontend verification on `hackathon` only. Isolated checkout at `C:\Users\aishr\Downloads\Drone-Project-main\Drone-Project-hackathon`, base `df3a407e1574e885a5bb9130885e68ddd4c47505`; no publication or other-branch changes.
- Python 3.11.18 `.venv`, private-token local data and loopback server on port 8768 configured. Start/restart with `scripts/start_hackathon.ps1`; frontend `/web/hackathon.html`.
- Fixed empty/nonfinite STL preview acceptance, same-file retry, Windows-only directory-sync crash in artifact storage; added missing mpmath dev dependency. No physics or flight-critical changes. Windows directory power-loss durability remains unqualified.
- Verified real Chrome intake/export flow, live authenticated STL API, 109 targeted Python tests, 118 isolated reference tests and 362 Node tests (1 skipped). Full suite not completed; unrelated repository lint has 32 findings. Detailed commands, failed attempts and limitations: `docs/qa/hackathon-local-2026-11-20.md`. No CFD or grid-independence execution claim.

## Current continuation: 27 October 2026

- Owner approved project-scoped read-only rotor source actions. `sources.list` and `sources.inspect` expose bounded retained identity, units, conditions and verified provenance to chat and MCP without cross-project enumeration. Targeted source and agent suite passed 12 tests including a local MCP SDK client and hosted viewer. QA: `docs/qa/agent-source-inspection-2026-10-27.md`; no source authoring or physics change. AI-JOURNEY-001 is blocked pending a private live Groq retry after the usage limit, not marked complete.

- Owner approved persistent per-user AI settings and project chat. Local implementation uses AES-GCM encrypted provider settings with a separately configured server secret; hosted actor isolation and explicitly shared local identity, save/replace/remove, status, and saved-key chat are implemented. The mock-provider browser verified save, refresh/reuse, reviewed approval/rejection and deletion. Agent tests passed 46 with one PostgreSQL integration skipped; see `docs/qa/persistent-ai-settings-2026-10-27.md` and setup `docs/technical/ai-settings.md`. No production secret, deployment or GitHub publication was performed. Real-provider testing of saved credentials, PostgreSQL, native accessibility and full action coverage remain open.

- AI-JOURNEY-001 is in progress: the full explain/edit/human-review/freeze/run/summary path passed with a scripted provider and synthetic project. A separate disposable local workbench is open for the owner to enter a Groq key privately and test the real model; no real-model result is yet established. See `docs/qa/ai-journey-2026-10-27.md`. Remote hosted provider setup, live Claude/ChatGPT and wider action coverage remain open.
- First live chat produced a generic error with unknown cause. Added tested, static secret-free Groq failure categories; the disposable server is restarted on loopback and awaiting a fresh private key entry and retry. The exposed prior key needs revocation. No production server was restarted.
- Owner identified the retired default model. Groq documents its decommission for free/developer tiers; replaced the default with its recommended tool-capable `openai/gpt-oss-120b`. The new default was verified in the disposable browser. Live model behavior remains unverified.
- Owner's retry showed access denied. A no-key network probe isolated Cloudflare HTTP 1010 on the default Python user agent; an identifying PhysiCore user agent reached Groq authentication instead. Updated the adapter and tested the outgoing header and safe error categories; restarted the disposable server. Awaiting a live retry with a privately entered replacement key.
- Live Groq chat subsequently answered and invoked `design.inspect` on synthetic data. It also claimed unsupported CFD/edits. The following explanation/proposal request hit a Groq rate/usage limit before creating a proposal. Added and tested an explicit instruction to avoid unsupported capability claims; this is not a guarantee and is not yet live-validated. Live reviewed edit, freeze, run and summary remain pending. See QA record.

## Previous continuation: 27 October 2026

- Owner approved hosted organization sign-in. Local implementation now provides
  OIDC authorization-code/PKCE sign-in for provisioned users, opaque hosted browser
  sessions, remote project consent and scoped MCP HTTP. A disposable HTTPS browser
  completed sign-in, consent, remote proposal, human approval, retry and logout;
  real provider/Claude/ChatGPT, PostgreSQL, production security and hosting remain
  unverified. See `docs/qa/hosted-signin-remote-mcp-2026-10-27.md` and
  `docs/technical/ai-foundation.md`. User data, original shared runtime and main
  branch are untouched. Wider project action coverage and owner code tools remain
  future work.

## Previous continuation: 26 October 2026

- Owner approved the AI-native foundation and MCP-first stage. Implemented in the
  isolated `codex/ai-native-foundation` worktree: scoped project credentials,
  discoverable actions, trusted review, version-bound edits and undo, receipts,
  saved design-to-study actions, real stdio MCP and workbench controls. See
  `docs/technical/ai-foundation.md` and `docs/qa/ai-foundation-2026-10-27.md`.
  No model-provider activation, embedded chat, code worker, publication or
  deployment. Physical validation and qualified engineering review remain open.

- Owner approved “Proceed with Job Activity & Recovery”, including tests/browser/full interface review and main publication. JOBS-001 implemented: nonblocking hosted job/attempt inspection, manual refresh/pagination, explicit permitted recovery and associated-study navigation with draft preservation/context guards. Verified 148 Node tests (24 new), 27 existing Python regressions and 58 Chrome checks; four wheel assets/resource hashes and static protections pass. Full law review corrected state wrapping/selected-label contrast and distinguishes list IDs. QA: docs/qa/job-activity-2026-10-26.md. Reused-fixture failed rerun retained and explained; final fresh-fixture checks pass. No server/model/access/dependency changes or deployment. Implementation 65c54a8ed82cc1c8c2383c8e93fcd9bdadfaff4c published to main; exact remote SHA/all branch names verified. Receipt: .physicore/evidence/PUBLISH-2026-10-26-job-activity.json. Hosted mode only; provider/worker/endurance/restore/physical gates remain open.

- Owner approved “Proceed with Rotor Source Explorer”, including targeted tests/browser/interface review and main publication. SOURCE-EXPLORE-001 implemented: discrete retained samples, exact original-row/value inspection, declared coverage and electrical/shaft basis, stale/late-response guards and viewer-safe controls. Verified 124 Node tests (24 new), 45 existing Python regressions and 68 installed-Chrome checks; wheel bytes/resource hashes pass. Full 147-entry law ledger and real layout/name fixes: docs/qa/rotor-source-explorer-2026-10-23.md. No model/API/dependency/access/retained-byte change or deployment. Implementation e5d7e7d7c9c1c911b2ea26f1c9673646cd30734f published to main; exact remote SHA and all branch names verified. Receipt: .physicore/evidence/PUBLISH-2026-10-23-source-explorer.json. Native popup/zoom/screen-reader/provider/physical qualification remain unverified.

- Owner approved “Proceed with Case Trim Evidence”, including targeted tests/browser/interface review and main publication. TRIM-001 implemented: separate mission-payload and individual-case records; exact commands, candidate totals, residuals/policy/interval and guarded frozen-case navigation. Verified 100 Node, 41 Python regressions and 65 Chrome checks. Full 147-entry law ledger, corrected accessible naming/column width and failed harness attempts: docs/qa/case-trim-evidence-2026-10-23.md. No physics/API/dependency/access/retained-byte change or deployment; implementation 974e04679f46a1d6f3453e200ee20a61b7d9fb28 published to main and exact remote SHA verified; receipt: .physicore/evidence/PUBLISH-2026-10-23-trim-evidence.json. Native popup keyboard selection/native zoom/screen-reader/provider/physical qualification remain unverified.

- Owner approved “Proceed with Study Review Pack”, including tests/browser/interface review and main publication. PACK-001 implements exact retained result/frozen input, PDF/receipt and rotor/conditioned-source ZIP with hashes, bounds/exclusions and existing permissions/jobs. 74 Python, 81 Node and 46 Chrome checks pass; QA/interface ledger: docs/qa/study-review-pack-2026-10-23.md. No physics/dependency/source/result/access changes; implementation 757b5c8b21bd68ac301b94b9bfd4862207303425 published to main and exact remote SHA verified; receipt: .physicore/evidence/PUBLISH-2026-10-23-review-pack.json. Initial test/setup/Linux limits retained; hosted publication uses deterministic producer fixture, not a demonstrated Linux supervisor. Focused research: RESEARCH_LOG.md. Original shared API must restart to load the route; no restart/deployment performed.

- Owner approved “Proceed with Mission Energy Budget”, including targeted tests/browser/interface review and publication to main. ENERGY-001 adds exact retained budget/segment evidence and guarded referenced-case navigation; implemented and locally verified: 61 Node tests, 65 existing Python regressions and 31 Chrome checks (16 mission, 15 comparisons), no page JS errors. Final QA/interface ledger: docs/qa/mission-energy-2026-10-23.md. Implementation 367bd1ba86c9ab50950a81d181803b6990899133 is published to main and exact remote SHA verified; receipt: .physicore/evidence/PUBLISH-2026-10-23-energy.json. No formula, source/result byte, reserve, API/dependency, access or deployment change.

- Owner approved “Proceed with Design Comparisons”, including targeted checks and publication to main. COMPARE-001 implements grouped whole-declaration changes, before/after case outcomes and limits, exact JSON, strict numeric gating and stale/late-response guards.
- Verified: 48 Node tests (13 new), 35 existing retained-study/report/summary regressions and 15 disposable Chrome browser checks; no page JS errors. Final law review and screenshots: docs/qa/design-comparisons-2026-10-23.md. Failed harness attempts remain retained and explained. CSS zoom=2 is not native zoom; screen-reader/real-user/provider testing remains unexecuted.
- Implementation 988b93fc445712b9ee73e28f2dcacddbc8b84282 is published to main and its exact remote SHA verified. Receipt: .physicore/evidence/PUBLISH-2026-10-23-comparisons.json. Previous importer/library af637bf publication receipt is retained.
- Preserve original shared runtime/access, retained sources/results/formulas/tolerances and all branches. No deployment, runtime restart, qualified physics acceptance or real-aircraft validation is performed. Broader requirement checks remain a future concrete design.

## Completed importer delivery

- Current request: implement the approved CSV/Excel importer and reusable component library. Owner explicitly answered “Proceed with this design” to the concrete architecture, dependencies and targeted tests/browser checks. Design: docs/superpowers/specs/2026-10-22-tabular-component-library-design.md.
- IMPORT-001 delivered locally: CSV/modern XLSX worksheet/header/range selection, explicit column/units/test declarations, original/SI preview and row refusal, immutable raw/map/manifest provenance, persistent searchable project-owned source catalog, authorized same-org cross-project reuse and existing explicit rotor binding.
- Preserved: original source bytes, existing JSON path, saved/frozen geometry/revisions, model equations/schema/tolerances, public-demo access and all branches. Existing study/PDF exports do not yet embed the full tabular manifest chain; library provenance/download controls expose it.
- Access: source-project read plus target-project write for reuse, same organization; viewers can inspect/download with writes disabled. Hash knowledge grants no access. Local mode keeps existing shared semantics.
- Data limits: 2 MiB file/20 MiB expanded XLSX, 256 members/16 sheets/5000 rows/64 columns, literal values and explicit declarations; unchanged 2–64 sample rotor-map contract. Four concurrent readers per process. No inferred missing torque or source conditions.
- Runtime dependencies: openpyxl 3.1.5, defusedxml 0.7.1 and transitive et-xmlfile 2.0.0; verified PyPI hashes added to runtime/platform/test locks while preserving unrelated pins. Existing venv installed with uv (pip unavailable).
- Final evidence: 187 project/platform Python checks pass (optional S3 module excluded; three integration cases deselected), 35 Node tests and 44 actual browser checks (12 importer, 4 hosted viewer, 18 readiness, 10 JSON binding). Ruff, syntax/links/whitespace/protected paths and local wheel/hash-required fresh parser install pass. Existing Starlette/httpx warning remains.
- Unexecuted: optional S3 test module requires absent boto3; PostgreSQL/provider integration, full image deployment, native browser zoom, real-user usability and real-aircraft validation. The earlier blocked collection and browser/lint failures are retained and explained in docs/qa/tabular-library-2026-10-22.md.
- Visual review fixed actual enlarged-text mapping squeeze with container queries and a stable explicit select naming issue. CSV and XLSX save/reopen/download and frozen-source preservation verified on labelled synthetic data. No original shared server/tunnel settings changed; running source API must restart to load new routes.
- Main files: src/physimesh/projects/tabular.py, source_library.py; src/physimesh/api/source_library.py and app.py; web/js/source-library.js with editor/workbench/CSS integration. Usage: docs/technical/tabular-rotor-library.md. QA/screenshots/receipts: docs/qa/tabular-library-2026-10-22.md and .physicore/evidence/IMPORT-001-*.
- One primary implementing agent; no independent science acceptance claimed. Task/proof status: TASKS.json and .physicore/evidence. Local work only in this increment; no deployment, external contact, spending, branch deletion or autonomous background work.
- Previous GitHub delivery: main 371061918c5882e5c4aff40fc71f4d431bdb377c verified at previous delivery, including UI-001/UI-002 and SLICE-001/DOC-002/AUDIT-002 records. Preserve earlier evidence and initial research-log changes.
- Next product candidates: enhance requirement/design comparisons, then qualify a real-design data/review workflow. These need their own concrete design/scientific gates. No external database integration/license assumed.
- Scientific limits: SCI001-SCI003/DATA001 pending; reviewer UNASSIGNED, real aircraft inputs/customer accuracy UNKNOWN; DR-01 and V4 review remain pending. Imports and passing checks grant no physical acceptance.
- Other retained preparation: constants ledger and fixed-pack provenance; AUDIT-002 established no local capacity bypass and left broader boolean-mass handling as a separate reproduction proposal.
- Open release gates: measured validation, qualified/independent review, aircraft acceptance, security/endurance/restore/provider/hosting. Do not claim industry certification or demonstrated customer willingness to pay.

- User follow-up: replaced the hackathon old-workbench handoff with /web/simple-workflow.html (Configure → Review → Export). New browser test and existing intake regression passed; no project API dependency or solver execution. Details in the local hackathon QA record.

- Connected optional simple-workflow component panels to existing fixed-wing, isolated-hover BEMT and cantilever endpoints; no equations changed. Three real synthetic browser computations and 292 related Python tests passed. Exact component records export separately; aircraft remains NOT_SIMULATED. Server verified running on 127.0.0.1:8768. See local QA record.

- Fixed-wing-only Run simulation setup and existing coefficient-screening submit added. Mission defaults copied from the user's current tab: 300 kg, 1000 m, 70 m/s, 15 min. Verified real in-app screening with synthetic coefficients; no aircraft verdict or CFD claim. Original tab/STL untouched.
