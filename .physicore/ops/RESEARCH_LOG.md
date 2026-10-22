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
