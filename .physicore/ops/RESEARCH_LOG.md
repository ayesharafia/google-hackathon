# Research log (append dated, decision-relevant notes only)

## 2026-10-22: CEO product direction, proposed for owner approval

Decision: choose the first useful industry-pilot workflow for this existing
drone app. Proposed initial user/buyer: small drone engineering teams preparing
payload/mission design reviews; the engineering lead is the hypothesized buyer.
No customer interviews, willingness-to-pay or commercial demand established.
The owner explicitly requested strategic app changes toward industry readiness.

### Actual application source observations

- web/workbench.html already exposes saved geometry, frozen revisions, studies,
  retained JSON/PDF, comparison and scoped review. Do not re-propose these as
  absent features or claim their behavior was exercised in this research.
- web/js/input-editors.js imports rotor_map_v1 JSON and instructs users to copy
  the returned SHA-256 into matching rotors. This is a concrete intake-friction
  candidate, not a measured user drop-off result.
- web/js/workbench.js showReadiness mainly lists hover reasons and heuristically
  routes by message words. The inspection endpoint also exposes separate mass,
  pack, screening and per-case model eligibility data that can support a more
  actionable presentation without changing physics.
- Source intake and client workflow already have C02/C03/C06 specifications in
  docs/production/client-delivery-plan.md; prefer a bounded increment there.
  Real model review, measurements, security/endurance/restore qualification and
  hosting decisions remain open in plan.md. No new release status is granted.

### Three relevant alternative workflows, official sources read today

- [eCalc xcopterCalc](https://ecalc.ch/xcoptercalc.php?lang=en): exposes propulsion
  component inputs plus flight-time, payload and electrical outputs. Establishes
  an existing component-sizing workflow, not independently verified accuracy,
  demand for PhysiCore, or absence of competing evidence features. Accessed
  public page only; no subscription, scraping or component-data reuse.
- [Tyto Robotics database](https://database.tytorobotics.com/): supports uploading
  and sharing propulsion test data. Establishes a measured-data ecosystem that
  may inform user-supplied source intake. No dataset downloaded, license granted
  or compatibility/installation-validity claim made. Check rights and metadata
  before any later import.
- [SimScale collaboration documentation](https://www.simscale.com/docs/platform/collaboration/):
  documents project sharing and view/copy/edit permission choices. Establishes
  review/access expectations in engineering platforms, not a comparison proving
  competitors lack traceability. Public/private handling belongs in a later
  explicit hosting/access decision; preserve the owner's current open demo mode.

### Readiness framework and limits

[OWASP ASVS official overview](https://asvs.owasp.org/) identifies stable 5.0.0,
published 30 May 2025, as a technical web-application security verification
framework. Suitable for the future security qualification backlog already in
C07; this lookup is not an assessment or compliance claim. Aircraft regulatory
and certification applicability remains UNKNOWN without jurisdiction/intended
use and qualified advice. No standard clause text or compliance claim invented.

### Options and recommended sequence, not yet approved for implementation

Options considered: (A) guided intake-to-design-review workflow, recommended;
(B) extend mission/battery physics first, requiring current-model review and
data qualification; (C) broaden hosted enterprise infrastructure first, requiring
provider/access/recovery decisions before a customer workflow is validated.

At most three proposed priorities:
1. A bounded Engineering Readiness presentation in the existing workbench:
   separate saved mass/pack/model-case checks, actionable links, draft-staleness
   and explicit unknown/unassessed evidence. No invented completeness score or
   new readiness/aircraft-approval claim. Reuse existing inspection API.
2. Guided source intake: explicit retained-map selection/binding instead of
   manual hash copying; later original CSV/unit mapping requires its own data
   contract/design. Preserve raw bytes, configuration coverage and provenance.
3. Pilot release gate: evaluate complete intake/frozen-run/review/export journey
   against real supplied evidence and the named reviewer; qualify access,
   recovery and deployment separately. No anonymous demo reconfiguration now.

Opportunity is an INFERRED product hypothesis: reduce setup mistakes and make
design decisions auditable. Proposed metrics: completion of one genuine design
journey without manual hash copying/JSON edits, time to resolve a blocker,
source traceability coverage and matched frozen report identity. All measured
baseline values UNKNOWN. No revenue, accuracy or time-saving promise.

First-slice engineering estimate: roughly 2-4 focused developer days including
integration/QA, not a delivery guarantee; no new dependency, paid compute or
solver work expected. Source architecture review supports this bounded scope;
real user usability and browser behavior are not yet assessed. Full industry
readiness needs the separate model/data/security/operations release gates.

The brainstorming skill requires approval of the concrete design before app
implementation. Research is complete; no application changes, tests, new ready
tasks, publication, contacts, spending or deployment performed for this request.

Follow-up: the owner subsequently approved Engineering Readiness first, including
targeted tests/browser/interface review. UI-001 implements that bounded increment
locally; see docs/qa/engineering-readiness-2026-10-22.md. The preceding paragraph
records the research phase before approval, not the final implementation state.
The remaining product ideas are proposals; no commercial/physical claim promoted.

No online market research has been executed by this starter kit. Entries must include date, question, source title/URL or DOI, what it supports, license/access conditions where relevant, implications and remaining uncertainty. No fabricated citations.

## 2026-10-22: SLICE-001 narrow numerical-source lookup

Question: do primary references establish the exact atmospheric parameter set,
and what do the selected solver settings mean? This is source investigation,
not market research, calibration or experimental validation.

- [COMSOL 6.4 Sutherland's Law, table 5-2](https://doc.comsol.com/6.4/doc/com.comsol.help.cfd/cfd_ug_fluidflow_high_mach.08.46.html): public vendor HTML read. Lists air mu0=1.716e-5 Pa s, T0=273 K, S=111 K. The code uses 273.15 K and 110.4 K, so this table does not establish the exact code triplet. Do not replace parameters or transfer a validity/error range from a different triplet. No dataset or software downloaded/licensed.
- [SciPy linprog HiGHS interface](https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html): public vendor HTML read (returned v1.18.0 docs, not asserted as installed runtime). Describes time_limit seconds, maxiter and status=2. Supports meanings only, not the repository's selected magnitudes or physical accuracy. Defaults remain runtime-version dependent.
- [NOAA U.S. Standard Atmosphere 1976 PDF](https://www.ngdc.noaa.gov/stp/space-weather/online-publications/miscellaneous/us-standard-atmosphere-1976/us-standard-atmosphere_st76-1562_noaa.pdf): search located primary archive; full-text fetch failed with size limit (18,267,064 bytes). No primary-value verification, altitude interpretation or license conclusion claimed from unread contents.

Implication: preserve existing code values; mark unresolved primary provenance,
applicability and scientific tolerance rationale explicitly in the constants
ledger. Qualified review remains pending. No external contact, spending or
physical claim publication.

## 2026-10-22: DOC-002 exact time conversion

Read [NIST SP 811 chapter 5, table 6](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-5-units-outside-si),
public primary HTML. It states an hour equals 3600 seconds. Used only to source
the exact time conversion underlying J/Wh; no battery chemistry, specific
energy, efficiency, reserve policy or physical error allowance follows from
it. No dataset/download, measurement, paid service or new licensing dependency.

## 2026-10-22: competitive position and proposed market roadmap

Owner asked what PhysiCore is building and which features should be planned for
market competition. Read current README, plan, state/strategy and actual
workbench comparison/export/review controls. This is a planning recommendation;
no feature implementation, task promotion, model approval or publication follows.

**Proposed first customer:** small commercial multirotor engineering teams whose
lead engineer reviews payload/endurance design changes. Buyer, willingness to
pay, current spreadsheet workflow and switching cost remain hypotheses requiring
interviews. Existing implementation includes retained projects/STL preview,
restricted map-based payload/constant-hover segment accounting, readiness,
source assignment, revisions, comparisons and reports; hosted collaboration
foundations exist but operational/physical acceptance gates remain open.

Official sources checked on 22 October 2026:

- [eCalc xcopterCalc help](https://ecalc.ch/calcinclude/help/xcoptercalchelp.htm):
  fixed-pitch RC multirotor setup with battery/ESC/motor/propeller selection and
  environmental inputs. Main calculator search excerpt was available; direct
  main-page fetch returned 429. Help HTML was read successfully. Supports a
  component-sizing comparison, not a complete independent feature/pricing audit.
- [Tyto Flight Stand 50](https://www.tytorobotics.com/pages/flight-stand-50) and
  [motor/propeller database](https://database.tytorobotics.com/): measurement
  equipment/software and shared propulsion-test/component records. An initially
  guessed software URL was inaccessible; no claims derived from that URL.
  Treat Tyto as an adjacent alternative/data ecosystem and potential integration
  target, not a presumed partner. Public visibility grants no bulk-reuse license.
- [SimScale drone simulation](https://www.simscale.com/simulations/drone/):
  vendor describes cloud CFD, structural and thermal analysis and design sweeps.
  These are vendor-described capabilities; performance/accuracy/usage marketing
  metrics were not independently verified or adopted.
- [OWASP ASVS](https://owasp.org/projects/asvs): official page lists stable
  5.0.0 and its web-control verification purpose. Proposed future hosted-security
  assessment framework only; no audit, compliance or airworthiness claim.

**Inference:** a focused measured-component-data -> supported mission assessment
-> explained design comparison -> reviewable evidence workflow is a practical
position to test. No claim that competitors lack provenance or review features;
no defensible moat or customer demand has been established by these pages.

**Three proposed priorities, not implementation-ready backlog tasks:**
1. Data-to-decision: CSV/Excel mapping with explicit units, original-byte retention,
   reusable authorized component records, coverage diagnostics and enhanced
   variant/requirement comparisons. First bounded slice: preview CSV columns,
   units and rejected rows before conversion to the existing map contract.
2. Measured evidence: compare frozen predictions with owner-authorized test data,
   disclose errors and valid ranges; qualified review precedes physical claims.
   Battery state/temperature/age or new flight regimes require separate data,
   specs and validation. Existing report/review foundations should be extended.
3. Paid-pilot delivery: optional private team workspaces, reliable job/recovery,
   access isolation, backups/restore and support; preserve existing public demo.
   Validate willingness to pay before choosing exact prices or expanding scope.

Proposed launch gates: three design partners (target, none claimed recruited),
reviewed measurement comparisons for declared scope, an end-to-end repeatable
customer workflow, and verified private-data/restore behavior. Target metric:
time from authorized raw component data to a reviewable design decision, plus
pilot completion/conversion and error within agreed scope. Values/baselines
unknown. No customer contact, spending, dataset import, tests or deployment.

## 2026-10-23: proposed frozen-study engineering handoff

Owner asked “build more CEO”. Clean main f214660; no eligible task. Observed:
local studies have verified JSON and frozen-input access, existing local/queued
PDF exports, exact map bytes including conditioned/raw dependencies, and scoped
artifact permissions. The separate retained sphere/CFD results path already uses
a deterministic ZIP, but the local drone-study handoff has no single package.
Source-library manifests are not bound into frozen study records; do not invent
a unique original CSV/XLSX lineage from a normalized map hash.

Customer job (hypothesis): a small multirotor engineering team's lead needs to
inspect a colleague's result/input/source set outside the running app. Buyer,
willingness to pay, review time and switching cost remain unknown.

Primary sources checked on 23 October 2026:
- SimScale post-processing docs, https://www.simscale.com/docs/post-processing/
  (page last updated 10 June 2025): result-control data and local result database
  can be downloaded; formats depend on the simulation. Export is an expected
  workflow in this alternative, not a claimed competitor gap.
- Tyto Flight Stand Software manual, https://www.tytorobotics.com/blogs/manuals-and-datasheets/flight-stand-software-user-manual
  (8 July 2024): saved tests can be exported; data-handling section describes CSV
  export/resampling. Adjacent measured-component ecosystem, not an integration
  or reuse-license grant. Read public HTML only; no test data downloaded.
- W3C PROV overview, https://www.w3.org/TR/prov-overview/, Working Group Note
  30 April 2013: describes data provenance and points to PROV Recommendations.
  General traceability context only; this proposal does not implement a PROV
  serialization or claim standards, security, aviation or scientific compliance.

Recommendation (proposed, not implemented): one bounded extension to the current
retained export path. An authenticated/current-project study review ZIP contains
the verified PDF plus receipt, exact result and canonical frozen snapshot,
referenced retained performance JSON and conditioned-map raw dependencies,
readable limitations/contents and SHA-256 member checksums. Member paths derive
from fixed names/digests; bounded to 128 members and 40 MiB uncompressed. Reuse
PDF job preparation, avoid solver re-execution, new dependencies or new storage
subsystems. Corrupt/missing required artifacts refuse the package.

Known limits: original tabular files/manifests, CAD, human review/signatures,
solver source/build/container and runtime dependencies are excluded and listed.
This is an input/result handoff, not a complete project backup or guaranteed
standalone solver replay. Checksums prove byte consistency, not authentic
engineering approval or physical truth. Existing public-demo/private access
semantics and all branches stay intact.

Alternatives considered: continuing separate downloads is simpler but leaves
assembly to the reviewer; a full project backup with raw import/CAD/build lineage
requires additional bindings, larger storage/permission design and is a later
feature. No public sharing link or new deployment is required. Expected compute:
bounded reads/hash/ZIP/PDF generation through existing code, no paid service or
physics run; roughly one focused implementation slice after design approval.
Acceptance: exact bytes/member hashes, deterministic repeat output in a fixed
environment, conditioned closure, missing/corrupt/wrong-project/access refusal,
real browser download/unzip, stale-selection guard and full UI review. Target
learning metric: whether a reviewer can identify the result, inputs, model and
sources from this one artifact; no baseline or savings claimed.
