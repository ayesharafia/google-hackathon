# Tabular rotor-source importer and library: implementation evidence

22 October 2026. IMPORT-001, baseline main `3710619`. Owner explicitly approved
[the concrete design](../superpowers/specs/2026-10-22-tabular-component-library-design.md),
including parser dependencies, targeted tests and browser checks. One primary
agent implemented and reviewed this increment. This is local software evidence;
no independent scientific acceptance, production deployment or new accuracy claim.

## Delivered

- Bounded UTF-8 CSV and modern XLSX parsing, worksheet/header/range selection,
  four distinct mapped measurement columns and explicit units/test declarations.
- Original/converted row preview, errors, blank counts, strict existing map
  validation and preview invalidation. No inferred torque, test conditions,
  silent row reduction, fitting or tolerance change.
- Original bytes, canonical map and reproducible versioned manifest retained
  separately. Hash verification and conversion reproduction precede library use.
- Persistent, searchable, cursor-paginated project-owned catalog. Authorized
  cross-project reuse copies/grants the complete source chain without changing
  a draft until explicit rotor selection. Identical retries are idempotent.
- Existing project/organization roles preserved. Viewers can inspect and download;
  import/reuse requires write permission. Revocation, same-user cross-org denial,
  artifact ownership and private metadata/byte denial are checked.
- Source/manifest downloads, retained draft bindings and unchanged frozen source
  references. No existing model equations, assertions or acceptance thresholds
  changed. Existing JSON import remains available.

Usage and limits: [import/library guide](../technical/tabular-rotor-library.md).

## Executed verification

| Check | Observed result | Recorded command |
|---|---|---|
| Project/platform suite, excluding optional S3 module and integration marker | 187 passed, 3 deselected; existing Starlette/httpx deprecation warning | [Python regression](../../.physicore/evidence/IMPORT-001-test-20261022181719481660.json) |
| Existing readiness/source-binding Node unit tests | 35 passed | [UI units](../../.physicore/evidence/IMPORT-001-test-20261022181121083142.json) |
| Tabular CSV/XLSX browser journey | 12 checks passed, zero page errors | [Final browser run](../../.physicore/evidence/IMPORT-001-test-20261022182337202648.json), [check list](assets/tabular-library/browser-checks.json) |
| Actual hosted viewer browser journey | 4 checks passed: read-only search/pagination/inspection/download, disabled writes, sign-out clearing | [Role browser run](../../.physicore/evidence/IMPORT-001-test-20261022182107905315.json) |
| Existing readiness browser regression | 18 checks passed | [Readiness](../../.physicore/evidence/IMPORT-001-test-20261022181908112189.json) |
| Existing JSON import/source binding browser regression | 10 checks passed | [JSON binding](../../.physicore/evidence/IMPORT-001-test-20261022182216417889.json) |
| Wheel and new parser installation | Eight source/web assets match wheel bytes; dependency lock identity matches; fresh hash-required installation of openpyxl 3.1.5, defusedxml 0.7.1 and et-xmlfile 2.0.0 succeeds | [Package check](../../.physicore/evidence/IMPORT-001-test-20261022181640390341.json) |
| Ruff | Passed after corrections | [Final lint](../../.physicore/evidence/IMPORT-001-test-20261022182214284772.json) |
| Syntax, whitespace, links, protected paths and final source hashes | Passed | [Static record](../../.physicore/evidence/IMPORT-001-static.json) |

Python checks include numeric/unit errors, unchanged map restrictions, formulas,
boolean/nonfinite/error cells, CSV dialects/BOM/quoting, forged XLSX dimensions,
external relationships, XML entities, expanded archive limits, parser admission,
original-byte retention, corruption refusal, concurrent/idempotent saves,
storage failure without a completed entry, restart persistence, catalog cursors,
role/organization isolation, grant/revocation behavior and newer migration refusal.

Browser checks use actual synthetic CSV and XLSX file selection, mapping/unit
controls, declaration edits, conversion records, downloads, search/reuse,
explicit rotor choices, save/reopen, frozen preservation and a held response after
settings change. The hold fixture reconstructs the browser-submitted spec with
the actual synthetic XLSX bytes before delaying a successful real API response.

## Retained failures and limits

- The first browser run timed out locating a select whose surrounding label text
  changed when options were populated. Added stable explicit accessible names;
  the complete journey then passed.
- Visual review found that enlarged text still squeezed the two-column mapping
  controls although their outer boxes fit. Changed to one column by default and
  a container-width query for wider panels; added a structural assertion and
  inspected readable detail screenshots.
- A held-response browser fixture initially replayed an intercepted disk upload
  without its file bytes. That produced an empty-file refusal rather than the
  intended successful held response. Reconstructed that synthetic multipart
  request with its actual file bytes and browser-submitted spec, asserted a valid
  response, then verified stale refusal. Earlier failed receipts remain intact.
- A broader suite collection attempt could not import boto3 from the optional
  S3 test module. The final 187-check run explicitly excludes that module and
  deselects the three integration-marked cases. No S3/PostgreSQL/provider run is
  claimed. The new library SQL uses the existing SQLite/PostgreSQL boundary;
  PostgreSQL execution remains unqualified here.
- Ruff initially reported helper import/style issues; corrected and retained
  the failing receipt. The local venv has no pip; installed approved parsers with
  uv. Added actual PyPI release hashes to hashed runtime/platform/test locks
  before successful package verification. Existing unrelated pins were preserved.

Native browser zoom, real user usability, deployed identity/storage providers,
full Docker image installation, production load/recovery, aircraft measurements
and qualified engineering acceptance were not assessed. The wheel check concerns
source/web bytes and the three new parser packages, not a full hosted release.

## Interface-law review

Re-read the owner's entire law and the complete
[existing rule-family ledger](engineering-readiness-2026-10-22.md#interface-law-review),
checking every item again against this integration:

- Composition and typography: actual working import sheet and source catalog in
  the existing green/ink workbench. No marketing hero/footer/pricing/quote preset,
  default font rotation, ornamental kicker, fabricated customer mark or metric.
- Palette/material/icons: tonal surfaces and native controls. No saturated accent
  spray, purple/candy gradient, glow, tiled/boxed icon, artificial shadow, glass,
  background grid, decorative rule or blanket texture introduced. Icons and
  invented imagery are unnecessary for this measurement worksheet.
- Layout/containment: deliberate gutters, aligned mapping roles, a full-width
  multiline source description, wrapping hashes and a one-column narrow layout.
  Container queries use actual available width. Data tables scroll in named,
  keyboard-focusable regions; data columns retain shared row baselines. No
  clipped live text, ornamental cuts, overlapping panels or edge-jammed labels.
- Controls and motion: stable visible content, stationary buttons and native
  focus/selection. File/sheet/column/unit inputs, every action type, disclosures,
  downloads, catalog pagination, refusal and explicit application were exercised.
  Import settings have busy/status feedback, stale previews cannot enable saving,
  and readonly controls have verified role-appropriate behavior. No entrance
  gate, hover boop, active-nav dot or animated underline was added.
- Specificity and cohesion: actual selected file, headers, rows, values, conditions,
  source hashes and provenance records drive the UI. The imported measurement
  table is the meaningful artifact; no mock dashboard or synthetic sales proof.

Screenshots inspected: [desktop](assets/tabular-library/desktop.png),
[390 px](assets/tabular-library/mobile.png),
[CSS 200%](assets/tabular-library/zoom-200-css.png),
[phone mapping detail](assets/tabular-library/mobile-mapping-detail.png),
[enlarged mapping detail](assets/tabular-library/zoom-mapping-detail.png).
CSS enlargement is not claimed as native browser zoom.

## Reproduce

Use the existing venv and install the approved locked dependencies. Run the Python
and Node commands in the receipts. scripts/qa/verify_tabular_package.py builds a
local wheel and verifies only the new parser packages in a fresh venv.

For scripts/qa/tabular_library_browser.mjs, use a deliberately disposable loopback
app with local public mode, PHYSIMESH_BROWSER_BASE_URL,
PHYSIMESH_BROWSER_DISPOSABLE=1 and PHYSIMESH_BROWSER_XLSX_FIXTURE naming the
synthetic four-column Measurements worksheet. PHYSIMESH_BROWSER_EVIDENCE_DIR
selects output; PHYSIMESH_PLAYWRIGHT_MODULE can name the existing installation.
The viewer script additionally needs a fresh hosted-mode fixture, its selected
project ID, and synthetic viewer credentials as defined in that harness. Never
point these mutation-based browser checks at client data. Original shared server
and tunnel settings were not changed by this delivery.
