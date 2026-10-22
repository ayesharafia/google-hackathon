# Engineering Readiness: bounded UI delivery

22 October 2026. Task UI-001; user explicitly approved the concrete design and
targeted tests/browser review. Source baseline: `5477f94`. Work is local.

## Delivered workflow

The workbench now opens a separate saved-draft inspection sheet above geometry.
One action inspects saved inputs. Mass completeness, battery declaration
consistency and per-case model eligibility remain distinct. Source evidence is
not assessed by this endpoint; engineering acceptance remains pending qualified
review. None of these rows calculates payload or changes a study's qualification.

Each actionable issue opens an appropriate existing editor and moves keyboard
focus there. Stable editor-group keys replace matching against displayed group
names. Unknown diagnostics open full input JSON; backend text is rendered with
textContent, never HTML. Separate supplied-point screening checks are available
in an explicitly labelled disclosure, without overriding bounded-model status.

Structured and JSON edits clear previous check results. Saved-version mismatch,
request failure and replies arriving after edits/project switches cannot make
old checks look current. The panel states that it describes the saved draft
even when the viewer shows a frozen revision. Existing freeze/run controls,
geometry, revision/result bytes, authentication/access mode and physics code
are unchanged.

## Application files

- [engineering-readiness.js](../../web/js/engineering-readiness.js): presentation
  projection and DOM rendering, no model calculation.
- [workbench.js](../../web/js/workbench.js): inspection lifecycle/context guard,
  staleness, controls and editor navigation.
- [input-editors.js](../../web/js/input-editors.js): stable group keys.
- [workbench.html](../../web/workbench.html) and
  [workbench.css](../../web/css/workbench.css): panel placement, accessible state,
  width-dependent row layout and wrapping for long frozen-revision messages.

No server endpoint, schema, model coefficient, acceptance tolerance or dependency
was added or modified. Existing local access choices remain in force.

## Executed checks

| Check | Observed result | Receipt |
|---|---|---|
| node --test tests/web/test_engineering_readiness.mjs | 20 tests passed; incomplete/partial input, source/review claim separation, per-case eligibility, diagnostics and all navigation destinations | [Recorded unit run](../../.physicore/evidence/UI-001-test-20261022152251238982.json); final rerun also retained in task evidence |
| python3 -m pytest -q tests/projects/test_local_studies.py tests/projects/test_project_geometry.py | 26 passed in 1.90 s; one existing Starlette/httpx deprecation warning | [Recorded regression run](../../.physicore/evidence/UI-001-test-20261022152253318960.json) |
| Disposable Chrome browser acceptance | 18 checks passed, zero page JavaScript errors | [Final browser receipt](assets/engineering-readiness/browser-checks.json), [recorded command](../../.physicore/evidence/UI-001-test-20261022153436393527.json) |
| JS syntax, Ruff, git whitespace | Passed | Final static record in task evidence |

Browser checks include actual incomplete and labelled synthetic saved projects,
every introduced action, keyboard focus/activation, structured and JSON edits,
late real replies, project switching, frozen-view context, mismatched version,
network failure/retry, inert diagnostic text, disclosure, reopen and responsive
layout. Diagnostics/version/failure injections are UI fixtures, not physics
results. The frozen-revision test creates a disposable synthetic revision only.

Screenshots inspected: [desktop](assets/engineering-readiness/desktop.png),
[390 px](assets/engineering-readiness/mobile.png),
[CSS 200%](assets/engineering-readiness/zoom-200-css.png),
[720 CSS px](assets/engineering-readiness/narrow-720.png).
Native browser zoom, human usability, real aircraft data and production-provider
qualification were not assessed. CSS enlargement and a halved layout viewport
are recorded explicitly rather than called native zoom.

### Failures retained and corrected

- An early browser script waited for a project editor after reload before
  selecting a project. Corrected the wait to the workspace's available controls.
- Visual inspection caught cramped/clipped two-column detail text under CSS
  enlargement despite a passing document-overflow check. Switched rows to a
  one-column default and named container query for wide panels; added checks
  against both element boxes and actual text ranges.
- The added held-reply/project-switch fixture initially removed its route too
  early. Corrected the harness to await fulfillment before removing interception.
- Frozen-view phone testing found actual overflow from long hashes in the
  existing message/revision-summary paragraphs. Added overflow-wrap:anywhere and
  reran the complete browser journey successfully.

Earlier failed test receipts remain in .physicore/evidence; they are not silently
relabeled as passing. The corrected full browser run is the final UI evidence.

## Interface law review

Rechecked the owner's entire supplied design law against the new panel and its
integration. The following ledger records applicability, not certification of
every pre-existing page or control in the repository.

| Rule family checked point by point | Result in this delivery |
|---|---|
| Lucide/default outline glyphs, oversized icon tiles, fake/redrawn brand marks, boxed logos, gradient initials, missing/fake customer logos, no-icons overcorrection | No icon pack, decorative glyph, fake brand/customer or boxed mark introduced. Actions use meaningful text. No brand/social wall is warranted for an input-check panel. Existing real product geometry stays the visual artifact. |
| Em dashes, decorative quotation marks, quote/testimonial presets, fake metrics, generic filler copy | New copy is direct and scoped to saved inputs. Removed redundant explanatory copy during review; no testimonials, invented savings, accuracy or customer proof. |
| Pills/eyebrows/status chips, glowy buttons, gradient-icon pills, kitchen-sink cards, gradient lockups, inner glows/live-dot halos | No contained status chips, ornamental kickers, glows or gradient treatments. States are plain, legible text. |
| Fraunces/Work Sans, Space Grotesk, Cormorant/Didone presets, Sora/JetBrains, Syne, Archivo/Inter default brand voice, full rejected Google rotation, tasteful font-swap reflex, repeated house pairings | No font download/pairing introduced. The existing workbench's display face and neutral body remain consistent; no mono house voice or tracked-cap label costume added. JSON remains actual data. |
| Fake macOS/code windows, crude CSS diagrams, floating cards/tags, grid-paper backdrops, accent-bar cards, background blobs/halos, candy auroras, pastel gradients, fixed trailing backgrounds | None added. This is the actual working input UI, not a mock product prop. Existing geometry viewer remains separate and unchanged. |
| Blue-purple/cool-blue defaults, beige/cream/slop-gray surfaces, vivid accent sprayed everywhere, colliding palettes and section seams | Reused the app's considered green/ink tonal palette. No new saturated accent, gradient seam or unrelated color system. Text clears its surfaces. |
| Default CTA pairs, pricing tiers, pre-footer slabs, split/default/side-panel hero stacks, kicker-H2 starts, serif statement blocks, inset form islands, email pills, overlay image cards, numbered rails, standard footer/meta-SaaS skeleton, stacking/recycling compositions | No marketing section or new page skeleton introduced. The panel is a saved-input inspection sheet, with five distinct evidence roles and one inspection action. Existing page hero/footer are outside this bounded redesign. |
| Hairline-box reflex, decorative square rules/eyebrow ticks, all-around shadows, offset duplicate-box shadows, hard-edged shadows, blurred-copy blooms, botched glass | No new border, decorative rule, shadow, bloom or glass. Separation uses spacing and tonal rows. |
| Card/button hover lift/boop, animated underline fills, botched fill caps, sun-moon toggle, active-nav dots, gratuitous entrance animation | No moving button, reveal gate, new toggle or decoration. Hover changes state without translating controls. Content is visible by default; reduced motion is honored by existing global rules. |
| Invisible content, cut-off glows, content sliced by cuts/overlaps, edge-jammed text, crowded display words, off-center strike lines, grain above text, hard image seams | No clipping, masks, overlap or grain added. Zoom clipping found and fixed. Final element/text-range checks and screenshots show contained text and controls with gutters. |
| Ragged comparison columns, flung-to-the-edge composition, centering failures, oversized footer wordmark failures | Wide rows share the same title/detail grid; narrow panels stack. No comparison-tier/price/button baselines, glyph centering or footer wordmark introduced. Header action and title align deliberately; button labels are centered by existing padding/line-height. |
| Real specificity, meaningful product artifact, coherent typography/palette, purpose rather than mechanical avoidance, restrained authored interaction, no dead controls | Actual draft version/case IDs and backend reasons are used. Jump-to-editor plus focus, explicit staleness and guarded responses are purposeful interactions. All newly introduced action/disclosure types were clicked; keyboard activation and fallback navigation passed. |
| Premium-tool recipes: glass/refraction, self-colored borders, bespoke silhouette, micro-grid/noise gradients, cinematic scenes, animated fields, logo walls, giant wordmarks, scroll motion, signature serif/two-tone type, icon jewels/arrows, prebuilt blocks | Evaluated for fit and not added gratuitously. An engineering inspection sheet does not need these ornamental techniques. No new framework/library or generic component kit is required for native sections, buttons and details. |

No promise of industry-wide readiness follows from this UI increment. Measured
source qualification, current-model review, real-design acceptance, provider
security/endurance/restore and hosting decisions retain their existing gates.

## Reproduce

Unit: node --test tests/web/test_engineering_readiness.mjs (Node 22+).
Regression: use the existing project .venv and the pytest command above.
Browser: start a fresh disposable loopback app using a new data root and local
public mode; set PHYSIMESH_BROWSER_BASE_URL to that server and
PHYSIMESH_BROWSER_DISPOSABLE=1, then run
node scripts/qa/engineering_readiness_browser.mjs. Playwright and Chrome must
already be available; PHYSIMESH_PLAYWRIGHT_MODULE may point to an existing
Playwright installation. PHYSIMESH_BROWSER_EVIDENCE_DIR controls output. Never
target client data. No dependency was installed by this work.
