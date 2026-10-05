# Local retained-study reports

Date: 5 October 2026. Scope: local fixture workflow, not aircraft approval or hosted sharing.

`projects/reports.py` renders verified canonical study bytes and their exact frozen input snapshot. `LocalStudies.report_inputs` checks the project/study association, byte SHA-256, typed result and snapshot binding before either PDF or comparison. The report path never calls the solver. The PDF is retained with its source JSON hash, canonical snapshot hash, renderer source fingerprint and ReportLab version. Existing corrupted PDF bytes refuse export. Deterministic PDF metadata uses a fixed timestamp; that timestamp is not the evaluation date. The study-history database records the actual retention time.

The PDF displays a payload only for a feasible outcome. Its two-decimal headline is rounded down; the exact value, case outcomes, aggregate limit, chronological energy, qualification and complete evidence/input appendices remain available. Unicode source text is represented by ASCII escapes in the PDF's built-in fonts; literal markup is escaped. The JSON export is authoritative. Reports larger than one million formatted characters or 12,000 wrapped evidence lines refuse with an exact-JSON fallback.

Comparison uses two retained studies in the same local project. Changes are JSON pointers; arrays are whole values so indexes are not mistaken for stable component identity. Added and removed fields are distinct. Boolean and numeric values remain distinct. A numerical payload difference is shown only for matching model identity, result schema, mission semantics and data scope with both outcomes feasible. The changed fields do not establish causation. More than 500 changes refuses rather than truncating silently. Mutable draft edits cannot change either comparison input.

Protected routes:

- `GET /api/drone/projects/{project}/studies/{study}/pdf`
- `POST /api/drone/projects/{project}/comparisons`, with `before` and `after` study digests

Browser proof: an existing retained sequence study was selected through study history, compared with itself, and displayed identical frozen inputs and zero recorded change. The actual PDF button downloaded `hover-study-d64a47b42477ee0dbed18d432ef33a6bf286aa1ef3aaf2d5f1f62f71edb43c4e.pdf`. The downloaded file matches the response bytes and PDF SHA-256 `d39748ae12a09167a6ce4c570725e2fac0ff608c5d0c6f158c2377f0ebe754e0`. Browser automation did not emit its download event; the exact expected native file was verified independently. That receipt applies to the stated renderer observation, not later edited outputs.

Printed QA: rendered all 22 pages of the labelled sequence report with Poppler. Inspected page overviews, first two pages at full resolution, margins, table columns, full-length hashes, evidence wrapping and footers. No clipping, overlap or missing glyphs observed. Complete JSON appendix round-trips independently in a test. The example number is artificial and is not client aircraft capacity.

Automated evidence at this checkpoint: 465 local tests passed with three backend tests deselected; 118 reference tests passed; Ruff and JavaScript syntax checks passed. Native OpenFOAM was not rerun for these changes. Tests cover authorization, same-project scope, deterministic output, source/result/PDF corruption, unchanged retained comparisons after draft edits, numeric-comparison refusal and bounded rendering.

Full IP16 remains pending: assembly editing, repair/undo journeys, authenticated sharing/review, two presentation rehearsals and a backup recording. Responsive and full design-law acceptance of the expanded workbench remains pending the ongoing browser audit.

## Compatibility and renderer correction

New studies use local V3. Historical V2 sequence bytes produced from exact commit `07b9f192d55fd79c0cb209ece063bd029ce3d93e` are preserved in a labelled compatibility fixture. A regression seeds their exact artifact/revision associations, restarts the service, reads/exports the unchanged bytes and generates a qualified historical PDF without invoking the current model. The fixture was generated now from historical code; it is not a historical measured observation. V3 refuses the same sequence without participating bounds.

The PDF now embeds its renderer source SHA-256 as well as its version. A source-only identity change changes the PDF digest; retained artifact metadata and HTTP renderer/source headers agree for both outputs. Responsive checks found unequal export-button heights and squeezed mobile table columns. Both were corrected; final expanded-control/visual acceptance remains in progress.

The initial broad V2 adapter failed a Claude follow-up. Historical policies now dispatch only for exact known source fingerprints from 07b9f19, 0db6bb0 and 3f9b01d. Unknown/later V2 records must satisfy the stronger checks. Regression tests refuse contradictory required bounds/outcomes, nonattaining labels, uncertified infeasibility and nonbinding aggregate labels for those stronger-policy reads. V3 never selects a weaker policy based on historical source metadata. Source fingerprints are documentary identity, not authenticated engineering approval.
