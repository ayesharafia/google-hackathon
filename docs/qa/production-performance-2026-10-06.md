# Platform repeat audit — 6 October 2026

Compare with the [fresh V4 pre-change baseline](production-baseline-2026-10-06.md). These are local source-build experiments on the same cloud machine, with analytic fixtures, one Uvicorn process and closed-loop clients without think time. CPU 100% means one core. Tables show medians of three per-trial distributions, not pooled quantiles; memory is maximum process VmHWM and includes seeding. Startup/resource identities and individual request observations are retained in the [receipt archive](production-performance-2026-10-06.tar.gz). No provider SLO or aircraft validation is established.

Five cold starts: median **0.897 s**; median process high-water RAM **88.6 MiB**.

## Same mixed local workloads

Three 15-second trials per workload/concurrency, same 50 seeded projects and V4 bound checks. Browse includes first renders for previously unexported studies; it is not a fully warm-cache test. Author changes a description on every save/freeze/study cycle, producing a new specification. SQLite now has short two-second write waits and explicit 503 overload responses. All non-success responses are counted; none are hidden as successful requests.

| Workload | Users | Trials | p50 ms | p95 ms | p99 ms | Success req/s | Non-2xx | API CPU % | API peak RAM MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| browse | 1 | 3 | 3.5 | 16.4 | 17.4 | 178.85 | 0 | 83.7 | 104.7 |
| browse | 10 | 3 | 45.0 | 125.4 | 165.3 | 125.67 | 0 | 110.8 | 143.9 |
| browse | 25 | 3 | 109.5 | 288.2 | 12470.6 | 41.33 | 0 | 107.1 | 201.5 |
| browse | 50 | 3 | 265.8 | 22279.7 | 22652.8 | 8.92 | 40 | 105.5 | 239.7 |
| author | 1 | 3 | 21.8 | 36.4 | 42.5 | 44.65 | 0 | 80.9 | 95.4 |
| author | 10 | 3 | 130.5 | 658.2 | 1571.6 | 49.54 | 10 | 115.4 | 105.8 |
| author | 25 | 3 | 178.2 | 2047.5 | 2140.4 | 48.90 | 147 | 116.5 | 121.3 |
| author | 50 | 3 | 461.1 | 2302.2 | 2381.5 | 46.91 | 390 | 117.9 | 137.7 |

## First-render versus verified cached exports

Each cold trial requests a distinct previously unexported study per user exactly once. Finite bursts contain 1/10/25/50 observations; small-n tail quantiles are descriptive, not SLO confidence estimates. All studies are then successfully warmed outside timing, followed by a 15-second cached-export trial. This tests the explicit local synchronous profile; the hosted API queues first rendering (verified separately in browser/image journeys).

| Workload | Users | Trials | p50 ms | p95 ms | p99 ms | Success req/s | Non-2xx | API CPU % | API peak RAM MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cold_export | 1 | 3 | 521.4 | 521.4 | 521.4 | 1.92 | 0 | 96.9 | 103.5 |
| cold_export | 10 | 3 | 4849.6 | 4860.5 | 4861.3 | 2.06 | 0 | 103.4 | 141.3 |
| cold_export | 25 | 3 | 11963.3 | 12021.2 | 12047.1 | 2.07 | 0 | 104.2 | 197.2 |
| cold_export | 50 | 3 | 22217.6 | 24052.2 | 24057.5 | 1.23 | 62 | 105.1 | 254.8 |
| warm_export | 1 | 3 | 6.9 | 7.8 | 8.9 | 141.57 | 0 | 85.2 | 103.8 |
| warm_export | 10 | 3 | 64.7 | 91.4 | 108.2 | 151.78 | 0 | 124.5 | 142.5 |
| warm_export | 25 | 3 | 162.0 | 221.9 | 251.6 | 153.39 | 0 | 125.9 | 198.4 |
| warm_export | 50 | 3 | 341.0 | 443.7 | 488.3 | 147.01 | 0 | 126.3 | 254.8 |

## Hosted-mode PostgreSQL metadata path

Private individual sessions; separate project per client; eight API pool connections. Fresh job submission is one request per user per trial against a frozen revision; computation does not run on the API. Accepted jobs are cancelled outside timing so the queue stays bounded. Saves run for 15 seconds/trial and preserve optimistic versions. PostgreSQL is the pinned disposable one-CPU/1-GiB service with a 512-MiB data tmpfs; private artifacts use local files. This is not a managed provider or a 50-user full engineering workspace acceptance.

| Workload | Users | Trials | p50 ms | p95 ms | p99 ms | Success req/s | Non-2xx | API CPU % | API peak RAM MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| submission | 1 | 3 | 15.7 | 15.7 | 15.7 | 62.48 | 0 | 57.3 | 137.9 |
| submission | 10 | 3 | 149.4 | 164.1 | 164.6 | 58.35 | 0 | 93.0 | 140.4 |
| submission | 25 | 3 | 286.1 | 322.9 | 327.2 | 73.88 | 0 | 93.1 | 142.5 |
| submission | 50 | 3 | 485.6 | 592.1 | 595.2 | 81.07 | 0 | 91.1 | 145.4 |
| save | 1 | 3 | 10.1 | 11.8 | 13.8 | 95.97 | 0 | 62.0 | 139.1 |
| save | 10 | 3 | 95.5 | 129.2 | 152.8 | 102.63 | 0 | 115.6 | 142.8 |
| save | 25 | 3 | 243.2 | 292.4 | 317.2 | 101.45 | 0 | 115.3 | 147.1 |
| save | 50 | 3 | 503.8 | 582.1 | 617.8 | 97.88 | 0 | 115.0 | 152.3 |

Database CPU per trial ranges **0.022–2.892 s**. Service lifetime cgroup high-water memory **245.8 MiB** includes prior trials/cache and is distinct from API RSS. Raw per-trial counters are retained.

## Separate profiles and scale checks

| Action | Profiled median ms, 20 calls |
|---|---:|
| study_evaluate | 8.99 |
| pdf_export | 6.33 |
| study_export | 1.31 |
| project_freeze | 43.20 |
| study_compare | 12.57 |

At 1,000 projects the default 25-summary page is **4,764 bytes**, **2 SQL executes** (including connection PRAGMA), **0.578 ms** median under profiling. Unit checks visit all 1,000 without duplication, enforce at most one SELECT/page and bounded payloads at 100/page, and read long history through separate cursors. These are bounds on returned data/query count; they do not promise constant database planner cost.

CFD execution was not optimized. The six original coarse/medium runs and six native postprocessing runs remain the simulation baseline; no numerical equivalence or MPI speedup is claimed.

## Bounded endurance and recovery

The hosted SQLite journey soak ran **303.8 s** against a real API and separate worker, completed **67** distinct study/PDF journeys, and recorded **0 failures**. Every accepted result was read and cached PDF bytes were checked. This is a single-client bounded soak; the proposed 24-hour campaign is unrun.
api: initial/final sampled RSS 107.6/113.7 MiB, peak process HWM 113.7 MiB. Child attempt limits/resource receipts are retained per accepted job; these supervisor numbers exclude child compute memory.
worker_supervisor: initial/final sampled RSS 83.5/92.4 MiB, peak process HWM 98.7 MiB. Child attempt limits/resource receipts are retained per accepted job; these supervisor numbers exclude child compute memory.
Final sampled data footprint: **6.64 MiB**. Expected immutable evidence grows with completed studies; bounded retention/storage policies need the client decision. The [worker kill/restart drill](production-worker-failure-2026-10-06.json) and transactional backup/corruption tests are separate. No hosted RPO/RTO claim is made.

## Remaining five bottlenecks and next fixes

1. First PDF layout remains CPU-heavy and local concurrent publication can overload SQLite. Keep first render queued on isolated workers; size worker capacity from measured demand and reuse verified receipts.
2. The local write path still saturates. Use the hosted PostgreSQL path, bounded pools/transactions and explicit backoff; extend failure/long-history/scale trials on agreed deployment resources.
3. Freeze and job preparation still repeatedly parse schema/model inputs. Qualify immutable schema/revision caching keyed by original bytes and model/dependencies after current-model review; do not substitute a cached result for changed inputs.
4. Cached exports still validate and serialize retained evidence on every download. Profile validation/authorization/receipt I/O independently; introduce verified immutable read reuse only with corruption/source/identity checks and no hash-based authorization bypass.
5. Serial CFD and native postprocessing remain unchanged. Preregister controlled MPI/pipeline experiments and preserve mesh/domain/convergence/force-ledger evidence; qualify before capacity coupling.

Production targets remain proposed. Short loopback tests, finite submission bursts and a bounded soak do not establish 24-hour reliability, external latency, managed failover or real engineering claims.
