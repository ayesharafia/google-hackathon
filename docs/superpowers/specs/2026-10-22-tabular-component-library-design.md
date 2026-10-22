# Tabular rotor-source import and reusable library

Status: approved by owner on 22 October 2026: “Proceed with this design”.
Approval covers importer/library behavior, parser dependencies, targeted tests and
browser checks. It grants no scientific acceptance or deployment authorization.

## User and outcome

A drone engineer imports their own motor/propeller performance table, declares
its meaning and units, previews the exact conversion, and saves a reusable
source. They can explicitly bind it to matching rotors in another authorized
project without copying a hash. Existing JSON import remains usable.

First library scope is rotor-performance datasets. This does not pretend to
provide a populated vendor catalog, battery characterization or a generic parts
marketplace. Each library entry represents one configuration and set of test
conditions, not an interchangeable motor independent of its propeller and setup.

## Approach considered

1. Browser conversion and browser-only catalog: little server work but weak
   persistence, reproducibility and shared-access semantics. Not selected.
2. Server parsing/validation, immutable import receipts and an indexed library,
   with a guided browser mapping/preview: recommended. Reuses existing storage,
   metadata and rotor-map validation; allows consistent authorization.
3. External component-database integration first: licensing, access and mappings
   are unconfirmed. Defer until an actual permitted source is available.

## Workflow

1. In the rotor editor choose CSV or modern Excel (.xlsx). For CSV choose comma,
   semicolon or tab delimiter; use UTF-8, including a permitted BOM. For XLSX,
   choose a worksheet explicitly. Show the selected filename and input bounds.
2. Select header and data-row range. Map distinct source columns to RPM, thrust,
   absorbed shaft torque and input power. Require explicit unit choices; proposed
   supported units are RPM; N/gf/kgf; Nm/Ncm; W/kW respectively. No unit is inferred
   from a header, and mass kg is not interpreted as a force measurement.
3. Declare dataset/configuration identity, source kind and description, density,
   axial inflow, pitch, continuous-duration coverage, covered RPM intervals and
   electrical/shaft power basis. Shaft power retains the existing requirement
   for efficiency and its source. Never supply guessed operating conditions,
   coverage, torque or efficiency to make a file acceptable.
4. Preview original and SI values with physical worksheet/CSV row numbers,
   conversion factors, included/blank/error counts and actionable diagnostics.
   Explicitly expose missing torque or other unsupported columns. Nonblank bad
   rows block acceptance; no silent averaging, sorting, outlier filtering,
   sampling, deduplication or interpolation. Existing model limits remain in
   force, including 2–64 retained points. The user must select a supported source
   range rather than silently reducing a larger dataset.
5. “Save source to library” revalidates file, mapping and declarations on the
   server. It persists original bytes, normalized map and a versioned manifest
   tying together file hash, sheet/range, original rows, mapping, units/factors,
   declarations and conversion version. The normalized map uses the unchanged
   rotor_map_v1 contract. Exact source integrity remains verifiable.
6. Offer the existing explicit matching-rotor binding preview. Saving a library
   entry does not silently modify a project. Applying a selection marks the
   draft unsaved and clears readiness. Stale/context changes refuse assignment.
7. A searchable, paginated library shows label, configuration, declared source
   kind, test conditions and provenance identity. Selecting an entry exposes its
   details before the existing binding step. Refresh/restart retains entries.

## Access and persistence

Each entry has an owning project. In the shared local workspace, entries can be
reused between its projects. In hosted mode, listing and reading expose only
entries whose owning projects the current user can read, within the selected
organization. Organization membership alone grants no new project access.

Copying a source into another project requires current source-project read
permission, target-project write permission and the same organization. The
server verifies/grants the original bytes, normalized map and manifest through
existing scoped artifact/quota mechanisms. Digests are never entitlements.
Unknown or unauthorized IDs reveal no private filenames, metadata or bytes.

Use the existing SQLite/PostgreSQL metadata boundary for transactional catalog
indexing, with an explicit versioned migration. Immutable files remain in the
artifact store. A partial storage/index failure never returns a completed
catalog entry. Retries with the same owner and manifest are idempotent; another
mapping/declaration creates another immutable import record. Referenced source
objects are not overwritten or removed. Existing saved revisions remain valid.
A library provenance view/export must resolve and verify the full manifest chain;
existing study exports must not be advertised as including that chain until
explicitly wired and checked.

## Files and module seams

- A new projects tabular-import module: bounded CSV/XLSX reading, mapping,
  explicit conversion, row diagnostics, unchanged RotorMapV1 validation and
  versioned receipt construction. It performs no model fitting or solver work.
- A separate library repository/service: metadata migrations, authorized
  listing/reuse, content integrity, idempotency and artifact quota coordination.
- Project-scoped preview/save/list/detail/reuse routes. Keep parsing and storage
  out of endpoint bodies; apply existing authentication and project authorization.
- A dedicated browser import/library module mounted from input-editors.js,
  using existing guarded requests and rotor-source-binding.js. Avoid growing the
  general editor into a workbook parser or a storage layer.
- Existing validation schema, solver equations and tolerances remain authoritative.

## Workbook dependency and bounds

Use a pinned maintained openpyxl parser plus defusedxml, added to package metadata
and relevant locked environments. Verify the selected versions before install;
the documentation's displayed version is not proof of the latest release.

Read workbooks in read-only mode with formulas exposed and external-link
preservation disabled. Require literal numeric values in mapped measurement
cells; reject formulas rather than using potentially stale cached values. Reject
legacy .xls, macro-enabled, encrypted or unsupported workbooks with clear help.

Proposed application limits: file 2 MiB, expanded XLSX contents 20 MiB, 256 ZIP
members, 16 sheets, 5,000 inspected rows and 64 columns. Inspect ZIP headers and
actual decompressed reads, reject duplicate/unsafe members and external
relationships, cap strings/diagnostics/response size and close all resources.
These are parsing budgets, not scientific tolerances. Never trust declared XLSX
worksheet dimensions or content type alone. Tests must exercise forged bounds.

## UI design

Use the existing green/ink workbench and native labeled controls, with a clear
file -> mapping/declarations -> preview -> saved entry sequence. Original and SI
columns align; constrained table scrolling is named and keyboard reachable.
Keep errors adjacent to their fields/rows with a concise summary. Preserve focus
on validation failure and return it meaningfully after binding. Narrow screens
reflow controls and metadata; file/hash strings wrap. Content is visible by
default. Review the owner's entire interface law before shipping.

## Acceptance checks proposed with this design

- CSV dialect/quoted-cell/BOM handling and XLSX sheet selection/row provenance.
- Exact unit factors, finite/nonnegative values, duplicate/missing mapping,
  formulas/booleans/errors, invalid coverage and unchanged map acceptance rules.
- Resource bounds, malformed/oversized archives and literal-value-only behavior.
- Original-byte/hash retention; deterministic manifests and normalized values;
  integrity refusal after corruption; retry/idempotency and restart persistence.
- Authorized reuse and cross-user/cross-project/cross-organization denial,
  including no filename/byte exposure and correct target artifact ownership.
- Actual browser upload, map, preview, rejection, save, search, reuse, explicit
  rotor selection, stale import/context guards, draft save/reopen and unchanged
  frozen revision. Inspect desktop, phone and enlarged-text layouts.
- Existing JSON-import/readiness/project regressions and dependency/packaging
  checks. These verify software behavior; no aircraft accuracy follows.

## Source references checked 22 October 2026

- Existing contract: src/physimesh/drone/performance.py, projects/performance.py.
- Existing storage/access: core/artifacts.py, platform/scoped_artifacts.py,
  platform/database.py, platform/migrations.py, platform/identity.py; api/app.py.
- Existing UI: web/js/input-editors.js and rotor-source-binding.js.
- openpyxl capabilities/security:
  https://openpyxl.readthedocs.io/en/stable/
  https://openpyxl.readthedocs.io/en/stable/optimized.html
  https://openpyxl.readthedocs.io/en/stable/api/openpyxl.reader.excel.html
- NIST force conversions (explicit force units, not inferred mass):
  https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b9

No restricted vendor dataset is imported by this proposal. No spending, customer
contact, public/private access-mode change or deployment is part of this design.

## Design self-review

Checked against actual strict map fields and 64-point bound; all required physical
metadata remains explicit. Closed the library-access ambiguity by retaining
project ownership and requiring source read plus target write within one org.
Closed the raw-file provenance ambiguity with separate immutable raw/map/manifest
identities; do not rely on first-write artifact metadata as a mutable catalog.
Restricted the initial library to rotor datasets and modern .xlsx/CSV. Kept model
eligibility separate from import success. Tests and parser dependencies are
proposed explicitly rather than claimed executed/installed.
