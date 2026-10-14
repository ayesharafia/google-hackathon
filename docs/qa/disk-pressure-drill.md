# Bounded local disk-pressure drill (A05)

Run from the repository with its installed Python environment:

```sh
PYTHONPATH=src python scripts/qa/disk_pressure_drill.py --receipt /tmp/physicore-disk-pressure-receipt.json
python -m pytest tests/test_disk_pressure_drill.py
```

The script operates only in its own `TemporaryDirectory`. It does not consume free
space to exhaustion, launch a worker/solver, access a hosted service, or read
credentials. It runs exactly two scenarios, each with one fixed 336-byte synthetic
payload and at most three job attempts. SQLite schema/journal files also consume a
small amount of disposable space. At scenario completion, the drill measures
aggregate retained file sizes and rejects observations above 4 MiB; this is an
after-write observation, not a filesystem quota or a bound on transient peak bytes. The directory is cleaned on successful return
and ordinary exception unwinding; abrupt process/host termination can prevent
Python cleanup. The requested receipt remains outside that directory.

## What is exercised

Both scenarios call the actual `ArtifactStore.put_bytes` implementation. A scoped
patch raises `OSError(ENOSPC)` at its object or metadata first-write `os.link`,
after a real bounded tempfile write and fsync. The implementation's exception
handler removes that tempfile. The patch is restored before recovery. It neither
mocks the whole storage method nor changes production files. The link patch
temporarily affects the process-wide `os` module: run this standalone sequential
CLI in isolation, not alongside threaded storage writes in a shared interpreter.

At an object-link failure, neither object nor metadata exists. At a metadata-link
failure, the immutable object **already exists** and metadata is absent. This
partial state is recorded, not claimed to be an atomic rollback. Retrying the
same bytes retains the existing object and publishes metadata.

Each scenario uses real `MetadataDB` and `Jobs` against disposable SQLite:

1. Claim generation 1, inject storage failure, and call `Jobs.fail(retry=True)`.
   Check queued state, absent accepted result, and retry backoff enforcement.
2. Advance the injected clock by 2 seconds, claim generation 2, then advance by
   6 seconds past its 5-second lease. Verify expired claim publication refusal.
3. Claim generation 3 through actual lease recovery, write/read/verify the
   artifact and metadata, then complete the job. Verify attempt states
   `failed`, `expired`, `accepted`.
4. Reject publication by both old claims and the already accepted claim. Verify
   the accepted result is unchanged and persists through reopening SQLite.

The receipt contains fixed observations, sizes and attempt states, without local
paths, design inputs, credentials, worker/job/attempt identities, raw exception
strings, or raw result contents. A failing drill exits nonzero and does not write
a new success receipt; an existing receipt path is refused to preserve earlier evidence. Choose a new
path for each run. Elapsed time and observed end-of-run disposable file bytes
are included without disclosing local paths.

## Evidence boundaries

This is **injected ENOSPC**, not actual OS disk or quota exhaustion. It does not
verify ENOSPC during write/flush/fsync, directory fsync durability, SQLite writes,
PostgreSQL, remote object storage, the worker orchestration path, or solver
publication. Lease time advances through an injected clock, not a real wait.
Artifact object publication, metadata publication, and job completion are separate
operations. No artifact-plus-job transaction is demonstrated. The fixture is
storage/job bookkeeping evidence, not engineering or flight validation.

Temporary-directory cleanup is guaranteed by context management during ordinary
exception handling, not under SIGKILL or machine failure. Test receipt output
paths are supplied by the caller; only synthetic files and a sanitized receipt
are produced.
