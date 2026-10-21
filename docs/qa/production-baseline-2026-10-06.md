# V4 production baseline — 6 October 2026

Unoptimized application at `10efe4d968c1c7b841876c89f99b07856e75340b`. Analytic conditioned CT/CQ V4 fixture; hover, ordered energy and axial climb. One Uvicorn process, loopback HTTP, closed-loop clients without think time. Three 15-second trials per load/concurrency; drain time included in throughput. Profiling is separate from timing. This is a local resource baseline, not a hosted SLO or aircraft validation.

Cold startup: five runs, median **0.858 s** to health; median high-water RAM **86.8 MiB**.

Numbers below are medians of the three per-trial distributions, not pooled percentiles. CPU 100% means one core; peak RAM uses process VmHWM (includes seeding).

| Workload | Users | p50 ms | p95 ms | p99 ms | Successful req/s | Failures, 3 runs | CPU % | Peak RAM MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| browse | 1 | 5.0 | 395.2 | 422.7 | 18.21 | 0 | 97.3 | 109.0 |
| browse | 10 | 160.0 | 2784.4 | 3509.4 | 16.29 | 0 | 104.8 | 153.2 |
| browse | 25 | 189.6 | 11387.1 | 11867.1 | 16.69 | 0 | 106.5 | 223.4 |
| browse | 50 | 323.5 | 15823.2 | 16241.7 | 12.16 | 0 | 106.2 | 257.4 |
| author | 1 | 20.8 | 32.6 | 35.9 | 47.00 | 0 | 81.0 | 96.0 |
| author | 10 | 90.3 | 765.7 | 1691.5 | 53.65 | 0 | 108.6 | 105.5 |
| author | 25 | 125.3 | 2149.1 | 3537.6 | 53.05 | 0 | 111.0 | 117.5 |
| author | 50 | 345.9 | 3431.5 | 6476.0 | 52.94 | 8 | 112.7 | 131.9 |

Browse cycles HTML, JavaScript, inventory, detail, inspection, retained study, JSON and PDF. Author performs save → freeze → study on an individual project per client. Changing descriptions makes distinct immutable studies; it does not avoid solver evaluation.

PDF first_render: 3 observations, median 485.7 ms. The baseline renders every time; repeated bytes are deterministic.
PDF repeated_export: 6 observations, median 393.5 ms. The baseline renders every time; repeated bytes are deterministic.

Separate profiled actions (20 calls each; profiling overhead applies):
- study_evaluate: median 34.59 ms.
- pdf_export: median 1071.26 ms.
- study_export: median 1.18 ms.
- project_freeze: median 43.45 ms.
- study_compare: median 11.62 ms.

At 1,000 projects: 8,571,778 bytes; 2,002 SQL executes per listing; profiled listing/serialization median 52.07 ms.

| Simulation | Repeats | Wall median/range s | Container CPU mean % | Peak cgroup RAM MiB |
|---|---:|---:|---:|---:|
| coarse | 3 | 90.79 / 90.37–92.95 | 85.2 | 204.1 |
| medium | 3 | 265.54 / 261.81–267.39 | 94.0 | 523.8 |

Pinned sphere verification; cgroup peak includes charged cache and differs from RSS. Per-stage meshing/check/solve CPU and time plus retained metrics are in the raw receipts. No installed rotor or aircraft simulation was run.

| Native postprocessing | Runs | Wall median s | CPU median s | Peak process RSS MiB |
|---|---:|---:|---:|---:|
| coarse | 3 | 4.088 | 4.330 | 87.0 |
| medium | 3 | 12.988 | 13.172 | 209.2 |

Fresh processes verify unchanged native source hashes. Integration timing excludes imports; RSS includes imports. Pressure/shear integration and reconciliation use registered sphere units.

## Five bottlenecks and proposed fixes

1. Repeated PDF rendering: ReportLab layout dominates its profile. Reuse verified bytes bound to accepted JSON, frozen snapshot, renderer source and dependency identity; queue first render.
2. SQLite write contention: 50-user runs include unexpected failures. Use PostgreSQL row locks, short transactions and bounded pools; retain optimistic versions and explicit 503 overload responses.
3. Repeated work: identical study specifications still run LP; freeze repeatedly loads YAML. Reuse accepted studies only after source/spec checks; cache immutable schema after checksum validation.
4. Inventory fan-out: entire snapshots and all histories are included. Use keyset pages of summaries and separate bounded history/detail endpoints; prove response/query bounds at 1,000 projects.
5. Serial CFD and stage containers: benchmark stages and test controlled MPI/pipeline variants. Accept only equivalent numerical evidence with resource/isolation limits preserved.

## Evidence and limits

Raw observations are retained under `.backend/production-baseline-2026-10-06`; the [checked-in receipt archive](production-baseline-2026-10-06.tar.gz) contains sanitized metrics and request samples. Short tests do not prove 24-hour endurance, hosted targets, RPO/RTO or aircraft accuracy. Dedicated concurrent cold/cached export trials and hosted-adapter load tests remain separate acceptance work.
