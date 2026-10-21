# Bounded synthetic study/PDF soak

`scripts/qa/bounded_soak.py` is a standalone QA helper for the approved bounded
study/PDF journey scope. Production and numerical source is unchanged. It creates
a disposable hosted-mode SQLite app, authenticates a synthetic owner, saves and
revises the analytic V4 example, submits a real study, runs the actual local worker,
requests a real report job and verifies PDF bytes and cached reuse. It lists projects
and study history. This is not aircraft validation, production latency qualification
or a 24-hour soak.

```sh
PYTHONPATH=src python scripts/qa/bounded_soak.py \
  --seconds 30 --requests 100 --journeys 2 \
  --storage-bytes 67108864 --memory-bytes 1073741824 \
  --receipt /tmp/new-bounded-soak-receipt.json
```

The receipt must not exist; exclusive creation prevents replacement. No credentials,
raw HTTP bodies, input geometry, exception strings, paths or process identifiers are
retained. Internal progress is atomically updated in the disposable directory. Request
observations include unfinished requests, HTTP status, body byte count and full buffered
response latency, not URLs. A successful CLI exit requires the configured journeys,
zero failures, normal child exit, successful ledger cleanup and no observed surviving
owned processes. Budget exhaustion deliberately exits nonzero and retains partial evidence.

## Bounds and observations

- Duration defaults to 30 seconds and is restricted to `(0, 60]`; setup is included.
  The parent checks approximately every 50 ms and preempts a blocked child. Long
  synchronous requests and worker calls do not extend the workload deadline by a
  separate per-request or per-job wait.
- Request count includes login, project creation and all journey calls; allowed
  range is 1–1,000. Journey count is restricted to 1–20; there is no 24-hour mode.
- File-byte threshold is sampled over the entire disposable root, with a 256 MiB
  configuration ceiling. It is an observational stop threshold, **not a filesystem
  quota**; writes and filesystem allocation may overshoot between samples.
- Memory threshold is sampled aggregate RSS for the owned supervisor and observed
  descendants, including compute children with separate sessions. Configuration ceiling
  is 2 GiB. Sampled RSS is not peak memory; summed currently live process `VmHWM`
  values are not a simultaneous tree high-water mark. Short-lived children can evade
  a sample; these measurements are not hard OS resource quotas.
- Process wait allows 3 seconds with a bounded 0.5-second kill/reap retry;
  timeout or OS errors are retained as `process_cleanup_error` and prevent a
  successful CLI exit, while ledger cancellation/fencing and receipt writing
  still run. Descendant-exit observation allows 0.5 seconds,
  and ledger cleanup has a separate 5-second signal deadline. Native operations may
  delay Python signal delivery. Directory deletion and OS scheduling are not hard
  real-time bounded. Workload duration and cleanup duration are reported separately.

Linux `/proc` is required. A preflight verifies that `/proc/self/stat` and `os.getpid()`
refer to the same PID namespace **before any process is created**. If they differ,
the run stops with `incompatible_proc_pid_namespace`: it does not guess PID mappings,
signal proc-enumerated IDs or claim resource monitoring succeeded. The current cloud
execution environment exhibits this mismatch, so a monitored real-worker soak remains
unverified here. Reproduce on a compatible Linux host or pinned CI before acceptance.

## Stop and cancellation

On normal completion, budget stop, error or KeyboardInterrupt, the parent freezes its
own created supervisor, refreshes descendants, checks PID start times and kills only
confirmed owned processes. It observes survivor count, then opens the app's actual
`projects.sqlite` durable ledger. All queued/running accepted jobs are cancelled; succeeded
and failed jobs are preserved. Real stale-completion checks use previously running claims
and require `Jobs.complete` to raise `StaleAttempt`. If no running claim exists, zero
checks means **not observed**, not a passed forced-stop fence. State counts are derived
from all rows in the disposable ledger rather than a truncated API page; `accepted_jobs`
means ledger rows, not independently counted HTTP acceptance responses.

The helper does not test owner-versus-viewer access, logout/revocation, PostgreSQL,
hosted object stores, actual disk exhaustion or real aircraft data. Existing platform
privacy tests remain a separate gate. API exceptions are classified with safe labels;
cleanup failures and incomplete observations stay visible rather than being represented
as successful qualification.
