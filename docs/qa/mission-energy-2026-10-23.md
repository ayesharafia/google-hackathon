# Mission Energy Budget: retained-evidence UI

23 October 2026 (Asia/Kolkata). ENERGY-001. Owner approved “Proceed with Mission
Energy Budget”, including targeted tests/browser/interface review and publication
to main. Baseline: 0715aec7b65113fe4d75c1f3e8d91a663c30720d. One primary agent;
no independent physical acceptance is claimed.

## Delivered workflow

A selected retained study now has a Mission energy budget section: usable budget,
recorded energy used and remaining usable energy in J. Ordered segment rows
show source notes, referenced case, duration s, electrical power W, energy used J,
remaining usable J and declared power profile. Study/revision identities and
exact energy JSON are explicit. The complete existing result JSON download
remains unchanged. Missing sequence evidence is unavailable, never a zero budget
or a successful mission. Partial quantities remain unavailable.

Known retained reserve/integration declarations receive readable explanations;
unknown declarations stay explicitly unrecognized with exact evidence available.
The browser does not multiply power by time, subtract totals/reserve, convert
units, clamp small negative remainders, infer SOC/endurance, or promote numerical
results into aircraft approval. Values retain their actual numerical precision.
Scenario and allowable results remain separate from this recorded energy ledger.

Each eligible segment has a View case action. It selects the exact referenced
case in the same frozen-study viewer. From a draft or other revision view it
restores that study's retained revision first, preserving unsaved draft edits.
Workspace/study/revision/project/case guards reject stale actions. Missing or
ambiguous case references have no live navigation button. Controls disable while
busy/disconnected; focus moves to the viewer case selector after it is enabled.
Native controls and scoped styles reuse the existing workbench palette.

## Evidence and scope

| Check | Observed result | Receipt |
|---|---|---|
| Node presentation/identity checks and existing comparison/readiness/source binding units | 61 passed, including 13 new energy tests | [Unit evidence](../../.physicore/evidence/ENERGY-001-test-20261022191300039523.json) |
| Existing local retained studies/reports/summary and hover-pilot regressions | 65 passed; one existing Starlette/httpx deprecation warning | [Regression evidence](../../.physicore/evidence/ENERGY-001-test-20261022191248745407.json) |
| Disposable installed Chrome mission-energy journey | 16 checks passed, zero page JS errors | [Final browser receipt](../../.physicore/evidence/ENERGY-001-test-20261022191736357074.json), [checks](assets/mission-energy/results.json) |
| Existing design-comparison Chrome journey | 15 checks passed, zero page JS errors | [Comparison regression](../../.physicore/evidence/ENERGY-001-test-20261022191527728339.json), [checks](assets/mission-energy/comparison-regression-checks.json) |
| Workbench and new module syntax | Passed | [Workbench](../../.physicore/evidence/ENERGY-001-test-20261022191736435503.json), [energy module](../../.physicore/evidence/ENERGY-001-test-20261022191736514269.json) |

The main browser journey uses a fresh disposable loopback API/data root. It
creates actual synthetic alternative-case and ordered-sequence retained studies,
checks every displayed budget/segment value against the result, exercises real
pointer/keyboard actions and JSON download, changes an unsaved layout and
restores the referenced frozen case. Exact retained result bytes match the
download before and after navigation/edits. A delayed revision response confirms
busy controls. Injected API-response fixtures cover missing values/cases, unknown
policies and tiny negative remaining energy; these are UI checks, not solver
evidence. Injected detached old-button clicks confirm stale study/project refusal.

Visual evidence opened and inspected: [desktop ledger](assets/mission-energy/desktop.png),
[desktop context](assets/mission-energy/desktop-context.png),
[phone context](assets/mission-energy/phone-context.png),
[phone right-hand evidence columns](assets/mission-energy/phone.png),
[enlarged context](assets/mission-energy/enlarged-context.png),
[enlarged right-hand evidence](assets/mission-energy/enlarged.png).
The 390 px and CSS body zoom=2 runs check document overflow, budget text containment
and actual scrolling to the last table column. Text Range checks ensure table
text remains inside its own cell; matching rows/columns align. CSS zoom is not
native browser zoom. Native zoom, screen-reader usability, real-user testing,
hosted/provider qualification and real-aircraft validation remain unexecuted.

### Failures retained and corrected

- [Initial unit receipt](../../.physicore/evidence/ENERGY-001-test-20261022191245821273.json): new test used result_json instead of the historical fixture's original_result_json key. Corrected the test adapter; historical fixture bytes/assertions were not edited.
- [First browser receipt](../../.physicore/evidence/ENERGY-001-test-20261022191432550015.json): synthetic departure exceeded the referenced case's declared duration. The API correctly returned unsupported with no sequence evidence. Corrected only the disposable setup to 60 s departure/300 s hold; no model or tolerance changed.
- [Second browser receipt](../../.physicore/evidence/ENERGY-001-test-20261022191507420967.json): visible-layout assertion read a closed disclosure. The final journey opens the real disclosure before checking displayed frozen/draft coordinates.
- Source review fixed focus timing so the target selector is enabled before focus moves. Visual review found inherited no-wrap/min-width styles crowding new table headings. Scoped wrapping and table width now fit desktop, preserve cell boundaries and allow accessible horizontal scrolling on narrow containers. Final rerun above covers the finished styles. Earlier successes remain retained too.

## Complete interface-law re-check

The entire owner-supplied design law was read before work and checked again
against the finished increment. The applicability ledger below groups each
related family; it does not claim a whole-app redesign.

| Entries considered point by point | Result |
|---|---|
| Lucide/default thin glyphs, oversized icon tiles, boxed icons/logos, redrawn/fake marks, gradient initials, fake/omitted social proof, zero-icons reflex | No icon pack, tile, logo or false customer introduced. Native disclosure triangles and meaningful text actions belong to the existing engineering UI; no decorative social row is warranted. |
| Em dashes, ornamental quotes/testimonials, invented metrics and filler | No ornamental quote, customer claim or accuracy statistic. Short scoped explanations distinguish recorded energy from SOC/endurance and separate scenario/allowable evidence. |
| Eyebrow/pill/chip defaults, glowy buttons, gradient icon pills, kitchen-sink cards, gradient lockups, inner glows/live-dot halos | None added. Plain headings, a native ledger and a functional action in each case cell. |
| Rejected Google/Fontshare rotation, trendy font swaps, repeated display/body pairing, mono house voice, tracked-caps costume | No new font/dependency. Existing Optima/Candara identity and neutral body retained; values use ordinary tabular numerals. Monospace stays in exact JSON. Typography roles differ. |
| Fake app/code windows, crude graphics, floating cards/tags, accent bars, paper grids, blobs/auroras/halos, fixed trailing backgrounds | No decorative artifact/background. All main screen values are actual retained records. Browser-only refusal fixtures are identified as fixtures. Existing real geometry remains the product artifact. |
| Blue-purple/cool slate defaults, beige/cream/slop-gray, vivid sprayed accent, colliding palette and hard image/section seams | Existing green/ink tonal system reused. No gradient, photo seam or new saturated hue. Text and buttons have clear value contrast in inspected screenshots. |
| Default hero/side-panel/CTA pair, pricing tiers, testimonial/pre-footer slabs, kicker-heading/serif statement, inset form/email pill, image-caption cards, numbered rails, standard footer and SaaS meta-skeleton, recycled house layouts | No new marketing structure. The composition is an evidence ledger: bound identity, three recorded totals, ordered rows and exact evidence. Functional case buttons occupy shared table columns, not a preset primary/ghost pair. |
| Hairline box/rule/eyebrow tick, all-around/duplicate/hard-edged/blurred-copy shadows, botched glass | No new ornamental border, rule, shadow or glass. Tonal surfaces and spacing supply grouping. Actual keyboard focus outlines are retained for accessibility. |
| Hover boop/lift, underline fill, botched fill caps, sun/moon toggle, active-nav dot, stranded entrance reveal, gratuitous scroll/background motion | No moving controls or reveal gate. All content is visible by default. Native disclosure, guarded restoration and focused case selection provide purposeful interaction. Existing reduced-motion rules remain intact. |
| Cut-off glow, invisible/clipped content, notches/overlaps, edge-jammed text, cramped display numbers, off-center strike, grain above content | No masks, overlays, fixed content heights, display tracking or texture added. Context screenshots show parent gutters. Native evidence table scrolling is named, focusable and instructed; both sides were inspected. Per-cell Range checks catch overflow instead of accepting shaved headings. |
| Ragged parallel columns, default far-edge asymmetry, incorrect centering and footer wordmark failures | Summary totals align in equal wide columns and stack on narrow containers. Shared table cells preserve column alignment. View case labels are centered with consistent padding and stationary on hover. No footer/wordmark geometry changed. |
| Dead controls, generic specificity, checklist avoidance without a product idea, professional-but-lifeless work | The signature is real evidence-to-case navigation: exact ordered segment/source values drive the same retained viewer while protecting unsaved work. Both case actions, restore path, exact disclosures and existing download were clicked; keyboard and stale-request behavior are demonstrated. |
| Premium recipes: glass/refraction, self-colored borders, bespoke silhouette, micro-grid/noise gradients, cinematic scene/glyph field, giant wordmark, signature serif/two-tone, logo jewels/walls, arrows, prebuilt blocks and scroll motion | Evaluated for fit; not added as ornament to a scientific ledger. Accessible native table/select/button/details behavior is the appropriate foundation without a new UI framework. Coherence with the actual workbench and clear data interaction take priority. |

Final review fixed crowded table headings and focus timing, then re-ran the full
mission journey. No solver, backend contract, dependency, source bytes, retained
results, tolerance, reserve policy or access setting changed. Passing software
checks and this UI review do not establish physical accuracy, customer acceptance
or production readiness. The original shared server/tunnel remains untouched;
only the disposable QA server is started/stopped. All branches are retained.

## Reproduce

Run scripts/qa/mission_energy_browser.mjs against a freshly provisioned disposable
loopback API using PHYSIMESH_BROWSER_BASE_URL, PHYSIMESH_BROWSER_DISPOSABLE=1
and PHYSIMESH_PLAYWRIGHT_MODULE. The script refuses non-loopback targets and
requires the disposable flag. No new dependency or production deployment.
