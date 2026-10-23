# Study Review Pack v1

Select a retained study, open **Study Review Pack**, inspect its contents/limits
and choose **Download study review pack**. Unsaved draft inputs are excluded.
Existing JSON and PDF exports remain available separately.

## Contents

| Member | Meaning |
|---|---|
| study.json | Exact retained result bytes |
| snapshot.json | Exact frozen revision's canonical input JSON, not the mutable draft |
| report.pdf | Existing verified PDF for this result and frozen input |
| report-receipt.json | Existing renderer/result/input identity plus PDF byte hash |
| sources/SDIGEST.json | Exact retained rotor JSON, named by its SHA-256; conditioned sources also include their raw JSON dependency |
| manifest.json | Project/study/revision/model identity, recorded outcome/qualification, source dependency links, limits and exclusions |
| hashes.json | SHA-256 and byte count for every other member; excludes itself |
| README.txt | Contents, checksum interpretation and exclusions |

SDIGEST above denotes an actual 64-character hexadecimal file digest. Archive
paths use fixed names/digests; filenames from user data never become ZIP paths.

The manifest's snapshot_sha256 uses the existing si_numeric_snapshot_v1 study
binding, which normalizes equivalent JSON numbers. snapshot_json_sha256 and
hashes.json identify the exact snapshot file bytes. The existing PDF receipt
keeps its snapshot_sha256 JSON byte-hash convention. These identities have
different purposes and are not interchangeable.

Check every extracted member against hashes.json using a SHA-256 tool. The
workbench additionally verifies the complete ZIP checksum before downloading.
Checksums establish byte consistency, not authenticated authorship, scientific
accuracy or operational approval. Model/source limitations remain as recorded.

Excluded: CAD/STL, original CSV/XLSX and conversion manifests, authenticated
engineering signatures, executable solver/build/container/runtime dependencies.
A raw rotor-map JSON is not the original measurement spreadsheet. This is not
a complete project backup or a standalone solver replay. No unique original
spreadsheet association is inferred from a normalized map hash.

## API

GET /api/drone/projects/{project_id}/studies/{study}/review-pack

- Uses existing local/public-demo or hosted individual/project permissions.
  The archive and all required source artifacts must be readable in that project.
- 200 application/zip: X-Project-ID, X-Study-SHA256, X-Revision-SHA256,
  X-Review-Pack-Schema=study_review_pack_v1 and X-Pack-SHA256 identify the response.
  Cache-Control is private, no-store.
- 202: existing hosted report-preparation job. Poll its project job route, then
  request the same pack again. No new worker job kind or solver run. Repeated
  preparation uses existing report idempotency and PDF reuse.
- 401/403: existing session, project or artifact denial. 404: missing association.
  422: invalid/missing/corrupt required evidence or size/member limit exceeded.
  503 with Retry-After: both per-process pack build slots are busy.

Limits: 128 ZIP members, 40 MiB total uncompressed, existing 500000-byte rotor
source and retained/PDF size limits. Two pack builders per process. The browser
refuses ZIP bodies over 41 MiB, which allows container overhead above the
uncompressed limit. A failed build produces no partial ZIP or retained archive.
Only existing PDF generation/cache work may persist artifacts.

Sorted members, fixed timestamps/modes and stable metadata give repeatable ZIP
bytes in a fixed renderer/Python/compression environment. Cross-runtime binary
identity is not promised. A renderer update can change PDF and pack bytes while
the original study/source bytes stay intact.
