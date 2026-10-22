# Retained Design Comparisons

23 October 2026 (Asia/Kolkata). COMPARE-001. Owner approved “Proceed with Design
Comparisons”, including targeted tests, browser checks and publication to main.
Baseline: cb4166f34822f55b269052d7e93e3bd1c899d4da. One primary agent; no
independent scientific acceptance claimed.

## Delivered

The existing Compare retained studies section now presents recorded before/after
outcomes, payload lower bounds, limiting cases, aggregate limits, data scope,
mission semantics, engineering approval and retained identities. Each case shows
both outcomes and active limits, plus newly/no-longer active limits. Null/missing
case outcomes remain explicitly absent rather than being treated as failures.

Frozen input changes are grouped into Mass, Battery, Rotors, Mission, Geometry,
Model settings and Other declarations. Known whole declarations have friendly
names. Exact paths and before/after JSON remain available. Whole arrays are never
matched by index or inferred identity. Missing, null, zero, false, empty string
and empty array are distinct. Unknown paths fall back to exact recorded paths.

Aggregate and case deltas require strict true API comparability and finite
numeric values. No subtraction, ranking, percentage, causal inference or
compatibility exception is introduced in the browser. Raw recorded quantities
remain visible independently of whether a delta is permitted. Exact complete
comparison JSON is available in a native disclosure. Engineering approval remains
pending as recorded. No formula, numerical policy, acceptance threshold or
backend schema changed.

Changing a selected study immediately clears old results and announces staleness.
Requests capture workspace identity, serial and exact selected studies; late,
wrong-identity and unknown-format responses cannot become current. Project open,
workspace clearing and expired connection also invalidate comparisons. Pending
and refusal states clear previous evidence. Unsaved draft edits do not invalidate
a comparison of two retained records, which is explained on screen.

## Executed evidence

| Check | Result | Record |
|---|---|---|
| Node presentation/lifecycle and existing readiness/source-binding tests | 48 passed (13 new comparison tests) | [Unit receipt](../../.physicore/evidence/COMPARE-001-test-20261022185550568776.json) |
| Existing retained studies, summary and report regressions | 35 passed; existing Starlette/httpx deprecation warning | [Regression receipt](../../.physicore/evidence/COMPARE-001-test-20261022185251007312.json) |
| Installed Chrome, disposable loopback API and fresh synthetic data | 15 checks passed; no page JS errors | [Browser receipt](../../.physicore/evidence/COMPARE-001-test-20261022185634301092.json), [checks](assets/design-comparisons/results.json) |

Browser checks create actual synthetic retained revisions/studies using the API,
select them through live controls, compare, open exact/grouped details, edit the
draft, change selection and switch project. Additional clearly labelled UI
fixtures cover refused comparability, malformed identities, API refusal, missing
cases, unknown input paths and hostile literal text. A selection event is
**injected** while a response is delayed, because normal selections are disabled
while comparing; this is a response-guard check, not an ordinary user journey.
Keyboard Enter opens native disclosures. Unit tests separately cover context and
out-of-order requests.

Screenshots: [desktop](assets/design-comparisons/desktop.png),
[desktop context](assets/design-comparisons/desktop-context.png),
[390 px phone context](assets/design-comparisons/phone-context.png),
[phone horizontally scrolled evidence](assets/design-comparisons/phone.png),
[enlarged context](assets/design-comparisons/enlarged-context.png),
[enlarged horizontally scrolled evidence](assets/design-comparisons/enlarged.png).
Screenshots were opened and visually inspected, including enlarged detail crops.
Phone and CSS body zoom=2 checks assert no document overflow and contained
selectors/controls/text. Actual horizontal scrolling exposes the last evidence
column. CSS zoom is not native browser zoom. Native zoom, screen-reader user
testing, production/provider tests and real-user usability remain unexecuted.

### Earlier failures retained

- [First browser attempt](../../.physicore/evidence/COMPARE-001-test-20261022185346311980.json) assumed an obsolete fixture name “frame”. Fixed the harness to compare exact before-array values against the API instead.
- [Second attempt](../../.physicore/evidence/COMPARE-001-test-20261022185448175952.json) tried filling the JSON editor while its disclosure was closed. The final harness opens the actual disclosure before editing, with explicit bounded waits. No product permission or evidence condition was bypassed.
- The first successful browser run is also retained. Visual review aligned table column widths and then made study selectors respond to their container width; the final browser receipt above covers the finished layout.

## Interface design law: detailed final re-check

Read the complete owner-supplied law before work and again against the completed
change. Every entry was considered; the table groups related entries for a
readable applicability record. This is an existing engineering workbench, not a
new marketing page. Historical whole-page style is outside this bounded change.

| Entries considered | Final assessment |
|---|---|
| Lucide/default thin glyphs, oversized icon tiles, boxed marks, fake/redrawn logos, gradient initials, missing/false customer proof, zero-icons reflex | No icon pack, mark, fake customer or ornamental icon introduced. Existing real geometry remains the product artifact. The comparison uses meaningful native controls and actual record IDs. A social/logo wall is not warranted. |
| Em dashes, ornamental quote glyphs/testimonials, invented metrics, filler text | Direct, scoped evidence copy; no decorative quote marks, marketing claims or invented accuracy. Explanations distinguish recorded changes from causality. |
| Pills/eyebrows/status chips, glowy/gradient CTA pills, kitchen-sink cards, gradient logo lockups, inner-glow badges and pulsing halos | None introduced. Status is readable plain text; one explicit comparison action. |
| Entire rejected font rotation, tasteful font swap, repeated Google/Fontshare pairing, mono house voice and tracked-caps costume | No type download or identity redesign. Existing Optima/Candara display and neutral system body retained. Monospace appears only in genuine JSON values. Labels, headings and tables have distinct roles. |
| Fake desktop/code windows, crude charts, floating cards/tags, accent-bar cards, graph-paper grid, candy auroras, radial halos, fixed trailing backgrounds | None added. All displayed evidence comes from the actual API or explicitly labelled browser-only test fixtures. No decorative product mockup. |
| Cool blue/indigo, beige/cream/slop-gray defaults, vivid sprayed accent, collision/seams, hard image edges | Existing green/ink tonal surfaces preserved throughout; no new palette, image edge, gradient or atmospheric layer. Text remains legible on actual screenshots. |
| Hero/default split/right-panel/default stack, pricing tiers, testimonial cards, footer CTA, kicker-H2, statement block, island form, email pill, image caption cards, numbered rails, meta-SaaS skeleton, recycled whole-page layouts | No marketing section or layout stack introduced. This is a functional evidence section ordered outcomes, cases, input changes, exact record. |
| Hairline box/ornamental rule/eyebrow tick, all-around/duplicate/hard-edged/blurred-copy shadows, botched glass | No new border decoration, shadow or glass. Native tables use existing tonal alternating rows; spacing supplies grouping. |
| Hover lift/boop, growing underline, botched fill, sun/moon switch, nav dot, reveal gate, dead/static decoration | No animation gate or moving control. Purposeful response consists of immediate invalidation, pending/current/failure announcements and native disclosure response. Content is visible by default; global reduced motion remains intact. |
| Invisible content, cuts/notches/overlaps, edge-jammed text, clipped glow, cramped display type, strike alignment, grain above text | No masks, decorative cuts, overlaps, fixed content heights or texture introduced. Parent gutters verified in context screenshots. Evidence tables deliberately scroll in named keyboard-focusable regions with an explicit instruction. Both ends were inspected, rather than treating the offscreen columns as absent. |
| Ragged comparison columns, far-edge default asymmetry, centering and footer wordmark failures | All comparison tables now share fixed corresponding column proportions. JSON value columns align on wide containers and stack on narrow containers; study selectors now respond to container width even at CSS zoom=2. No footer/brand/glyph composition added. Button label remains centered and stationary. |
| Missing real specificity, avoiding the checklist without an idea, flat/dead controls, signature artifact and coherent visual language | Real retained identities, case IDs, constraints, paths and values supply specificity. The designed interaction is safe evidence comparison with selection-aware validity. All new action/disclosure types were exercised by actual pointer or keyboard; no decorative controls masquerade as functional ones. Existing viewer supplies the product artifact. |
| Premium recipes: glass/refraction, noise/micro-grid, authored scene/glyph field, giant wordmark, signature serif/two-tone headline, icon jewels, special silhouettes, CTA arrows, library blocks, scroll effects | Evaluated for fit and omitted where they would distract from evidence. No new framework/dependency is needed for tested native buttons/selects/details/tables. Existing palette and geometry context carry the product, without a marketing redesign. |

Visual review fixed inconsistent column proportions and cramped selectors at
enlarged text. Final desktop/phone/enlarged screenshots and browser checks show
aligned corresponding values, legible text, gutters and functioning disclosures.
This review and the passing software tests do not qualify physical accuracy or
production readiness. Qualified review, authenticated measured aircraft sources
and customer-approved accuracy remain open. Original shared runtime/tunnel and
all Git branches are preserved.

## Reproduce

Use a fresh disposable loopback API/data root with existing public demo mode,
then run scripts/qa/design_comparison_browser.mjs with
PHYSIMESH_BROWSER_BASE_URL, PHYSIMESH_BROWSER_DISPOSABLE=1 and the local
PHYSIMESH_PLAYWRIGHT_MODULE path. The script refuses non-loopback targets and
requires the disposable flag. No new dependencies or server deployment are
required.
