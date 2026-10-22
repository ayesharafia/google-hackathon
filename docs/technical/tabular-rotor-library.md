# Import CSV/Excel rotor measurements

Open a project, expand **Rotors and retained performance sources**, then
**CSV/Excel import and component library**. Existing rotor-map JSON import
continues to work.

1. Choose a UTF-8 CSV or modern Excel `.xlsx`. Select the CSV delimiter or an
   Excel worksheet, declare the header row, and choose **Read table columns**.
2. Select the exact data-row range. Map four distinct columns and choose each
   source unit explicitly:

   | Measurement | Accepted source units | Retained map units |
   |---|---|---|
   | Rotational speed | rpm | rpm |
   | Thrust force | N, gf, kgf | N |
   | Absorbed shaft torque magnitude | Nm, Ncm | Nm |
   | Recorded input power | W, kW | W |

3. Declare dataset/configuration IDs, source kind and description, test density,
   axial inflow, pitch, covered continuous duration and RPM intervals. Intervals
   use `low:high`, separated by commas. Their endpoints must be retained samples.
   For shaft power, declare efficiency and its source. Electrical input power
   must not apply efficiency again. A missing torque column or unknown condition
   needs source evidence; the importer does not invent it.
4. Choose **Preview SI conversion**. Review original and converted values and
   row diagnostics. RPM remains in rpm for the existing map contract. CSV row
   numbers count parsed records, including the header; quoted embedded newlines
   belong to the same record. XLSX rows retain worksheet numbering.
5. Correct every nonblank invalid row or choose an explicit supported range.
   Blank rows are counted. No sorting, averaging, filtering, interpolation or
   silent sampling is performed. The existing map contract accepts 2–64 complete
   samples; strict ordering, power/torque consistency and coverage checks apply.
6. **Save source to library** retains the original bytes, normalized map and an
   immutable conversion manifest. This does not select a rotor. Choose matching
   rotors explicitly and apply the source; then save and inspect the draft.

Editing the file, mapping or declarations invalidates its preview. A delayed
response after settings, draft or project changes cannot restore old choices.

## Library and provenance

Use **Saved rotor sources** to search by dataset or configuration. Inspect an
entry to view its test conditions and conversion record, download its original
file or manifest, and explicitly use it in the current project. Refreshing or
restarting the server preserves the catalog. Repeated identical saves are
idempotent; a changed declaration/mapping produces a new immutable record.

An entry belongs to a project. Shared local mode retains its existing shared
access. In hosted mode, users see entries only from projects they can read in
the selected organization. Copying requires source read and target write access
within the same organization. Viewers can inspect/download but cannot import or
reuse into a read-only project. Copying verifies/grants the original file, map
and manifest through existing scoped storage and quota handling.

Each manifest records original filename/hash, selected worksheet/range,
column/unit mapping, source declarations, conversion factors/version, original
values/converted rows and normalized-map hash. Reads verify hashes and reproduce
the conversion before returning the retained dataset. Library reuse leaves old
project revisions unchanged. Existing study/PDF exports do not yet embed the
complete tabular manifest chain; use the library provenance/download controls.

## Supported files and budgets

- CSV: UTF-8 with optional BOM; comma, semicolon or tab delimiter.
- Excel: `.xlsx`, explicit worksheet, literal numeric measurement cells.
- Formulas, error cells, booleans and nonfinite measurement values are refused.
  Formula caches are not used. Legacy `.xls`, macros, encrypted workbooks and
  external workbook relationships are unsupported.
- File limit 2 MiB; expanded XLSX contents 20 MiB; at most 256 archive members,
  16 sheets, 5,000 rows, 64 columns and 2,048 characters per text cell.
- Four concurrent table readers per process; excess requests return retryable
  overload responses. These are resource budgets, not physics tolerances.

Force conversion uses [NIST SP 811 Appendix B.9](https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b9):
1 kgf = 9.80665 N; 1 gf = 0.00980665 N. Ncm and kW use exact SI-prefix factors.
Mass kg is not accepted as a force unit.

Successful conversion establishes software contract consistency, not measured
accuracy or installed-aircraft applicability. Source declarations, model
eligibility and qualified engineering acceptance remain distinct.
