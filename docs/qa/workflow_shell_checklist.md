# Workflow shell QA checkpoint

2026-10-02, Task 1.5 shell plus implementation-status text maintenance.
Reviewed the full user-supplied design law again before this checkpoint.
This is an application workspace, with no marketing hero, pricing or testimonial blocks.

## Actual browser checks

- All six workflow tabs clicked with a pointer; each selects the corresponding content.
- Health retry clicked; it returns Server reachable. No browser console errors.
- Keyboard navigation verified during initial shell review: ArrowDown changes selection.
- Desktop and mobile screenshots retained in `.backend/qa/workflow-shell.jpg` and
  `.backend/qa/workflow-mobile-verified.jpg`.
- Mobile viewport 390 px: nav and sheet span x=24 through x=366, both with 24 px gutters.
- No clipping or horizontal overflow in the checked layout. Notch only clips the
  background; live copy sits below its cut and remains visible.
- Revised stale status text after backend contracts were implemented; UI entry
  and upload functions remain explicitly pending.

## Full design-law recheck

Every law entry was checked for applicability and against the actual shell.
Entries about absent marketing elements, photography, grids, glass, gradients,
pricing, testimonials, logo walls, artificial urgency, or image transitions are
not applicable; those elements were not introduced.

- Typography and composition: native Optima/Candara display and neutral body,
  no Google-font rotation or mono house voice. Data alone uses tabular/mono type.
  The workspace uses an input sheet and stage navigation, not a sales hero stack.
- Palette and depth: one restrained green paper/ink system, no blue-charcoal,
  candy wash, saturated accent splashes, halos or duplicate shadow boxes.
  The sheet silhouette serves the input-document metaphor; no fake app window.
- Shapes and marks: bare authored brand mark, no icon tiles, decorative tick,
  status pills, invented customer marks, gradient avatar, accent-bar cards,
  default CTA pair or canned footer wordmark.
- Motion and controls: tonal state changes only; no hover lift, boop, animated
  underline or reveal that hides content. Reduced motion respected. Every
  visible control has confirmed browser behavior; future controls are absent.
- Legibility and geometry: deliberate gutters, clear text contrast, aligned
  stage states and data rows, visible focus treatment, no content beneath grain,
  cut edges, overlapping sections, clipped glyphs or cramped display tracking.
- Content integrity: no fake aircraft values, solver capability claims or result
  panels. 750 kg is labelled carried payload; incomplete inputs remain unknown.
- Cohesion and specificity: one document-desk visual language, explicit study
  prerequisites, separate application configuration and engineering evidence.

This check accepts the present shell scope, not Task 3.5 viewer functionality,
Release A or aircraft validation.
