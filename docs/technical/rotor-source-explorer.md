# Rotor Source Explorer

The component library can display the literal samples retained by a CSV or
modern Excel import. Open a project, expand **CSV/Excel import and component
library**, load matching sources, then choose **Inspect source** on an entry.
The existing source identity, test conditions and conversion downloads remain
alongside **Retained source samples**.

## Inspect a point

- Choose thrust (N), absorbed shaft torque (Nm), or recorded power (W) against RPM.
- Click a marker or choose its original row in **Retained sample**. The readout
  displays all four exact normalized quantities. The selected table row follows.
- Focus the selected marker and use Left/Right to move between samples, or
  Home/End for the endpoints. Enter/Space retains the selected point.
- Scroll the exact table horizontally to inspect every quantity and coverage
  state. Original row numbers include gaps left by blank source rows. For Excel,
  these are worksheet row numbers; the conversion record identifies the sheet.

Coverage bars reproduce declared RPM intervals. A retained point outside those
intervals stays visible as a hollow marker. No line connects points, bridges a
gap or extends coverage. Axis labels are compact display approximations; exact
stored values remain in the readout and table. Zero-valued quantities remain zero.

Power is labelled **Electrical input power, W** or **Shaft power, W** from the
retained source. The explorer does not apply efficiency, infer current, convert
torque to power, fit a curve or extrapolate. The source's test conditions still
determine its declared scope. A measured declaration does not establish
measurement quality or aircraft applicability; analytic fixtures remain labelled.

## Scope and access

This view supports existing tabular-library entries with their retained map and
conversion record. Standalone JSON imports and conditioned solver profiles are
outside this feature. Existing read permission allows inspection and downloads;
source reuse still requires target write permission and explicit rotor selection.
Viewing or choosing points changes no draft, source, revision or result.

A new source inspection or search immediately clears the previous evidence.
Changing projects or signing out removes the old view. Serial/context checks
reject late responses and detached actions. Loading another catalog page keeps
the current inspector usable. Invalid sample, coverage, identity or unsupported
format evidence is reported as unavailable instead of silently dropping rows.

## Implementation and evidence

`web/js/source-explorer.js` projects the existing source-detail response, maps
coordinates for display and renders native selectors, a discrete SVG plot and
an exact table. Identity checks compare the selected entry and returned binding
fields; cryptographic bundle validation and conversion replay remain on the
existing server. The browser does not reconstruct and hash the canonical map.

No dependency, API, schema, permission, physical model or tolerance changes.
See [executed QA](../qa/rotor-source-explorer-2026-10-23.md) for the synthetic
fixtures, browser evidence and remaining limits.
