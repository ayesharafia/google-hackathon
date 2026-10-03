# P00.1: frozen production baseline

Date: 3 October 2026. Scope: baseline inventory, read-only verification and explicit local demonstration configuration. No aircraft data has been supplied.

This task preserves and identifies the existing reviewed MVP. It changes no existing solver, case template, physics calculation, plot, browser asset or published evidence byte. The new verifier checks the original source files and retained evidence against a committed inventory before the demo launcher starts. It does not establish hosted production readiness, aircraft validation or human release approval.

## Artifacts and identities

| Item | Exact identity |
|---|---|
| Original source snapshot | `d17f97a6d37d4458e08f005a20ecf5db870b3235`; 130 original runtime/script/web/reference/lock/build files |
| Original solver-run provenance | `4798f8434610e48f170ef9bc1abbfba5f6e1b2a2`, retained in the immutable run group |
| Claude follow-up review candidate | `f19cbebddffaf788df76f8a5cd35adf8b99d3cea`; bounded MVP PASS |
| Reviewed local data root | `.backend/demo-reviewed` |
| Run-group SHA-256 | `acd1b8716144aeaa045019515bdf377018ae4a74ce3a0403cf50c52da007ff6a` |
| Package manifest SHA-256 | `e5c2a75cca8b009aa69fce0205fced8e74442bab12aa26f0a42a5a335348cbc9` |
| Reviewed exported ZIP SHA-256 | `c3fe646f64e44a80d2ecb176aef374fcf475e08ff7b7fda31f8043ed193bf6c7` |
| ZIP size | 2,579,327 bytes; 33 manifest-listed members plus `hashes.json` |
| Inventory SHA-256 | `a7f96c610b80e7f37db027b2fee9a511e974e48ecf8da4f03ebbc22910f291be` |
| OpenFOAM image | `opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb` |
| Vendor v2606 archive SHA-256 | `2a1310e3ed192cc4c521e1d22dcc176f57bec61160c878dc4348f21d6672294d` |

The source snapshot, solver-run provenance and external review candidate are deliberately separate. The solver runs precede the review corrections; the corrected package derives from those unchanged native files. The review verdict is not silently extended to future source changes. The manifest fingerprint identifies the published revision more precisely than its short study ID.

The authoritative bytes and their sizes are in [production-baseline.json](production-baseline.json). The [reviewed-demo preset](../demo/reviewed-demo.json) binds that inventory by hash. [production-baseline-checks.json](production-baseline-checks.json) records performed checks and hashes of the new verification tooling and local test receipts. Documentary record hashes preserve their assertions; they do not independently authenticate a reviewer or reproduce the asserted experiment.

The inventory contains:

- Original source byte fingerprints taken from Git objects at the source snapshot, rather than assigning the old commit ID to modified working-tree bytes.
- All 33 package members and the original raw manifest fingerprint.
- Three native execution-record fingerprints, 23 input hashes per case, and 35 native output fingerprints per case.
- The synthetic request plus its retained source objects/metadata: 31 supporting files.
- Vendor archive identity and hashes of the historical review, reproduction, MVP gate and backend-pin records.
- Explicit pending human approval/presentation fields and `not_established` aircraft validation.

## Implementation and refusal behavior

[The verifier](../../src/physimesh/postpro/baseline.py) belongs to postprocessing because it validates the results contract; the shared core remains independent of result/aircraft modules. It streams large native files, validates a strict inventory schema and rejects duplicate JSON keys, nonfinite JSON, unsafe paths and file escapes.

A read-only verification checks:

1. Every frozen original source file and documentary record.
2. The exact raw package manifest, member hashes/sizes, expected member set and `ResultsV1` semantics.
3. The run-group hash, backend digest and original solver-code provenance.
4. The selected synthetic example and retained source objects/metadata.
5. When requested, all native input/output bytes and their execution-record bindings, and the vendor archive.

Unchecked native/vendor scopes are explicitly reported as false. The verifier does not run CFD, regenerate images, mutate a package, attach an authenticated review or promote evidence. Results retain `unverified` and the machine envelope's `independent_review: pending`. The separately recorded Claude PASS remains limited to its original scope.

The historical `.backend/demo-final` package still exists unchanged. It shares the short run-group ID but has manifest SHA-256 `f13d986134e613e17f8293ea74fbb1ca89c7b872dcd26dbe643ef7bca2469ab9`. Its bytes differ from the reviewed package, so the new preset refuses it. This task resolves presentation selection ambiguity; general content-addressed result revisions remain P00.2/P01/P05 work.

Verification is a point-in-time check of a trusted committed inventory, not a continuous security monitor or signed physics attestation. API routes retain their existing requested-artifact integrity checks. Do not edit the inventory/preset to force a changed package through. Future reviewed revisions need their own explicitly recorded inventory/preset; preserve this baseline.

The launcher additionally refuses a root containing another API-visible result group. The existing browser defaults to its first group; requiring a dedicated single-group root prevents an unrelated study from becoming the presentation default. Ordinary read-only verification can still check the frozen group in a multi-study root.

## Performed checks on 3 October 2026

| Check | Actual result | Scope |
|---|---|---|
| New refusal/portability tests | 25 passed, included in the unit suite | Changed sources/examples/records, rehashed same-ID historical package, native tampering, escaped/extra members, ambiguous JSON, relocated roots and token-safe launcher behavior |
| Unit suite | 315 passed; 3 backend tests deselected | Includes architecture guard and new baseline tests |
| Retained reference suite | 118 passed | Executed independently |
| Pinned backend fixture suite | 3 passed; 315 non-backend tests deselected | New actual fixture execution on the pinned image; not a new three-mesh campaign |
| Ruff | Passed | Current source and new tooling |
| Frozen source/package/native/vendor verification | 130 source files, 33 package members, 31 supporting files and 105 native outputs checked | All matched; 69 native input hashes and execution-record hashes also checked |
| Retained API result/export | Auth required; results accepted; all ZIP members/hash bindings verified | Export SHA-256 matches the reviewed ZIP above; evidence/review unchanged |
| Synthetic payload/missing case | 52.232730994123955 kg; removing climb yields no headline | Existing illustrative vertical-force ceiling only |
| Real historical-root refusal | Refused | Uses actual preserved `demo-final` bytes |
| Actual copied-package tampering | Refused | Changed a copied plot in a temporary directory; original package unchanged |
| Real launcher HTTP smoke | Passed on a free loopback port; process stopped afterward | Overrides inherited wrong root/public bind setting; reviewed result and web route served; no token printed |

The first full unit run detected an architecture violation when the verifier was placed in `core`. It was moved to `postpro`, then the architecture and full unit checks passed. No existing layering rule was weakened.

The retained JUnit/XML and detailed local receipts live under `.backend/p00-*`; their fingerprints and counts are in the committed checks record. The existing Starlette/httpx TestClient deprecation warning remains. This task does not replace the dependency stack merely to suppress that warning.

Original fresh-clone evidence is [recorded separately](fresh_clone_reproduction.md): three actual sphere runs/reuse at `58a9596`, plus Linux pinned backend fixtures at `73ee812`. Those historical records are not reported as a fresh solver campaign at this task revision. The current new tooling's fresh-checkout exercise is recorded below after execution.

## Local use and reproducibility

Install the committed dependencies/package using [README](../../README.md). On the machine retaining the baseline:

```sh
.venv/bin/python scripts/verify_baseline.py verify --native --vendor
.venv/bin/python scripts/verify_baseline.py demo --check-only
.venv/bin/python scripts/verify_baseline.py demo
```

The launcher requests a local session token privately or uses `PHYSIMESH_API_TOKEN`. It fixes the selected data root, database path, image and bind host to the preset and starts on `127.0.0.1`, default port 8766. It never includes the token in printed arguments or the verification report. Use `--port` when another local server owns that port. It leaves existing servers and evidence untouched.

For a moved exact copy of the published baseline:

```sh
.venv/bin/python scripts/verify_baseline.py verify --data-root /path/to/copied-demo-reviewed
.venv/bin/python scripts/verify_baseline.py demo --data-root /path/to/copied-demo-reviewed --check-only
```

Copy the whole reviewed data root, including examples and source objects, not just its `results` folder. Original absolute paths inside old run records are retained unchanged as provenance. Verification uses the inventory's repository-relative native locations, so copying the native directories to matching relative locations permits `--native` in another checkout.

GitHub contains code, configuration and fingerprints, not `.backend` CFD outputs, source archive, private token, local database or exported ZIP. A clone without those files must fail with a missing-file diagnostic; it must not silently create fabricated evidence. README generation commands can produce a new study in fresh output/publishing roots. Execution IDs, timings and group hashes may differ. A new study cannot pretend to match the frozen original package.

For a complete original-evidence handover, transfer the reviewed data root, the three inventory-listed native case directories, the pinned vendor archive and source checkout over the agreed private channel. Check hashes afterward. The same-ID superseded package is retained for audit and is not selected for presentation.

## Release status and next task

| Gate | Status |
|---|---|
| P00.1 baseline identification and read-only checks | Implemented; independent software review pending |
| Claude bounded MVP physics review | PASS at `f19cbeb`; scoped external report, not machine attestation |
| Remaining F4-F11/N1 corrections and general contracts | P00.2 and later tasks pending |
| Real geometry, rotor maps, mass/CG/pack and mission | Missing; real aircraft capacity remains unavailable |
| Real-aircraft validation and human engineering acceptance | Not established |
| Human product/final wording/release approval | Pending |
| Two complete timed narrated rehearsals | Pending under P09.3 |
| Playable backup recording and inspected playback | Pending under P09.3 |
| Private hosted deployment/security/recovery | Planned; not provided by this local launcher |

The next task is P00.2. Its physics/result-semantic changes require independent review of their own candidate and must not inherit this baseline's PASS. Presentation-only work and missing real-aircraft data do not block independent software tasks.

## Design-law recheck

The full supplied law was reread for this task. Every original browser asset matches the source inventory: no font, layout, palette, icon, control, animation, clip, shadow or displayed number changed. Existing screenshots/interaction records remain historical; this task claims an HTTP launch check, not a new visual or pointer/keyboard review. No new UI has been falsely marked reviewed. UI-changing tasks must perform the full point-by-point visual/interaction audit prescribed by the plan.
