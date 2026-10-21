#!/usr/bin/env python3
"""Aggregate measured campaigns without hiding overloads or claiming unrun targets."""
import argparse
import json
import statistics
from pathlib import Path


def table(runs, modes):
    lines = ['| Workload | Users | Trials | p50 ms | p95 ms | p99 ms | Success req/s | Non-2xx | API CPU % | API peak RAM MiB |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for mode in modes:
        for users in (1, 10, 25, 50):
            group = [r for r in runs if r['workload'] == mode and r['concurrency'] == users]
            if not group:
                continue
            assert len(group) == 3, 'retain all three trials'
            med = lambda field, group=group: statistics.median(field(r) for r in group)
            percentiles = [med(lambda r, key=key: r['request_latency_ms'][key]) for key in ('p50', 'p95', 'p99')]
            failures = sum(r['total_requests']-r['successful_requests'] for r in group)
            cpu = med(lambda r: r['resources']['cpu_mean_pct_one_core'])
            ram = max(r['resources']['process_hwm_bytes'] for r in group)/2**20
            lines.append(f'| {mode} | {users} | 3 | {percentiles[0]:.1f} | {percentiles[1]:.1f} | '
                         f'{percentiles[2]:.1f} | {med(lambda r: r["throughput_rps"]):.2f} | {failures} | {cpu:.1f} | {ram:.1f} |')
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.backend'))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    after = json.loads((args.root/'production-after-2026-10-06/api-results.json').read_text())
    exports = json.loads((args.root/'production-export-load-2026-10-06/results.json').read_text())
    postgres = json.loads((args.root/'production-postgres-load-2026-10-06/results.json').read_text())
    profile = json.loads((args.root/'production-after-2026-10-06/function-results.json').read_text())
    soak = json.loads((args.root/'production-endurance-2026-10-06.json').read_text())
    lines = ['# Platform repeat audit — 6 October 2026', '',
        ('Compare with the [fresh V4 pre-change baseline](production-baseline-2026-10-06.md). '
        'These are local source-build experiments on the same cloud machine, with analytic fixtures, '
        'one Uvicorn process and closed-loop clients without think time. CPU 100% means one core. '
        'Tables show medians of three per-trial distributions, not pooled quantiles; memory is maximum '
        'process VmHWM and includes seeding. Startup/resource identities and individual request observations '
        'are retained in the [receipt archive](production-performance-2026-10-06.tar.gz). '
        'No provider SLO or aircraft validation is established.'), '',
        (f"Five cold starts: median **{statistics.median(r['startup_s'] for r in after['startup_runs']):.3f} s**; "
        f"median process high-water RAM **{statistics.median(r['resources']['process_hwm_bytes'] for r in after['startup_runs'])/2**20:.1f} MiB**."), '',
        '## Same mixed local workloads', '',
        ('Three 15-second trials per workload/concurrency, same 50 seeded projects and V4 bound checks. '
        'Browse includes first renders for previously unexported studies; it is not a fully warm-cache test. '
        'Author changes a description on every save/freeze/study cycle, producing a new specification. '
        'SQLite now has short two-second write waits and explicit 503 overload responses. All non-success '
        'responses are counted; none are hidden as successful requests.'), '']
    lines += table(after['load_runs'], ('browse', 'author'))
    lines += ['', '## First-render versus verified cached exports', '',
        ('Each cold trial requests a distinct previously unexported study per user exactly once. '
        'Finite bursts contain 1/10/25/50 observations; small-n tail quantiles are descriptive, not '
        'SLO confidence estimates. All studies are then successfully warmed outside timing, followed '
        'by a 15-second cached-export trial. This tests the explicit local synchronous profile; '
        'the hosted API queues first rendering (verified separately in browser/image journeys).'), '']
    lines += table(exports['runs'], ('cold_export', 'warm_export'))
    lines += ['', '## Hosted-mode PostgreSQL metadata path', '',
        ('Private individual sessions; separate project per client; eight API pool connections. '
        'Fresh job submission is one request per user per trial against a frozen revision; computation '
        'does not run on the API. Accepted jobs are cancelled outside timing so the queue stays bounded. '
        'Saves run for 15 seconds/trial and preserve optimistic versions. PostgreSQL is the pinned '
        'disposable one-CPU/1-GiB service with a 512-MiB data tmpfs; private artifacts use local files. '
        'This is not a managed provider or a 50-user full engineering workspace acceptance.'), '']
    lines += table(postgres['runs'], ('submission', 'save'))
    db_cpu = [r['database_resources']['cpu_s'] for r in postgres['runs']]
    lines += ['', (f"Database CPU per trial ranges **{min(db_cpu):.3f}–{max(db_cpu):.3f} s**. "
        f"Service lifetime cgroup high-water memory **{max(r['database_resources']['process_container_hwm_bytes'] for r in postgres['runs'])/2**20:.1f} MiB** "
        'includes prior trials/cache and is distinct from API RSS. Raw per-trial counters are retained.')]
    lines += ['', '## Separate profiles and scale checks', '',
        '| Action | Profiled median ms, 20 calls |', '|---|---:|']
    for name, value in profile.items():
        if isinstance(value, dict) and 'profiled_latency_ms' in value:
            lines.append(f"| {name} | {value['profiled_latency_ms']['p50']:.2f} |")
    scale = profile['inventory_scaling'][-1]
    lines += ['', (f"At 1,000 projects the default 25-summary page is **{scale['response_bytes'][0]:,} bytes**, "
        f"**{scale['sql_execute_calls_3_runs']//3} SQL executes** (including connection PRAGMA), "
        f"**{scale['profiled_list_plus_json_latency_ms']['p50']:.3f} ms** median under profiling. "
        'Unit checks visit all 1,000 without duplication, enforce at most one SELECT/page and bounded '
        'payloads at 100/page, and read long history through separate cursors. These are bounds on '
        'returned data/query count; they do not promise constant database planner cost.'), '',
        ('CFD execution was not optimized. The six original coarse/medium runs and six native '
        'postprocessing runs remain the simulation baseline; no numerical equivalence or MPI speedup is claimed.'), '',
        '## Bounded endurance and recovery', '',
        (f"The hosted SQLite journey soak ran **{soak['elapsed_s']:.1f} s** against a real API and separate "
        f"worker, completed **{soak['complete_study_and_pdf_journeys']}** distinct study/PDF journeys, "
        f"and recorded **{soak['failures']} failures**. Every accepted result was read and cached PDF bytes "
        'were checked. This is a single-client bounded soak; the proposed 24-hour campaign is unrun.')]
    for key in ('api', 'worker_supervisor'):
        samples = [s[key] for s in soak['samples'] if s[key]]
        lines.append(f"{key}: initial/final sampled RSS {samples[0]['rss_bytes']/2**20:.1f}/"
                     f"{samples[-1]['rss_bytes']/2**20:.1f} MiB, peak process HWM "
                     f"{max(s['hwm_bytes'] for s in samples)/2**20:.1f} MiB. Child attempt limits/resource "
                     'receipts are retained per accepted job; these supervisor numbers exclude child compute memory.')
    lines += [(f"Final sampled data footprint: **{soak['samples'][-1]['data_bytes']/2**20:.2f} MiB**. "
        'Expected immutable evidence grows with completed studies; bounded retention/storage policies need '
        'the client decision. The [worker kill/restart drill](production-worker-failure-2026-10-06.json) '
        'and transactional backup/corruption tests are separate. No hosted RPO/RTO claim is made.'), '',
        '## Remaining five bottlenecks and next fixes', '',
        ('1. First PDF layout remains CPU-heavy and local concurrent publication can overload SQLite. '
        'Keep first render queued on isolated workers; size worker capacity from measured demand and reuse verified receipts.'),
        ('2. The local write path still saturates. Use the hosted PostgreSQL path, bounded pools/transactions '
        'and explicit backoff; extend failure/long-history/scale trials on agreed deployment resources.'),
        ('3. Freeze and job preparation still repeatedly parse schema/model inputs. Qualify immutable '
        'schema/revision caching keyed by original bytes and model/dependencies after current-model review; '
        'do not substitute a cached result for changed inputs.'),
        ('4. Cached exports still validate and serialize retained evidence on every download. Profile '
        'validation/authorization/receipt I/O independently; introduce verified immutable read reuse only '
        'with corruption/source/identity checks and no hash-based authorization bypass.'),
        ('5. Serial CFD and native postprocessing remain unchanged. Preregister controlled MPI/pipeline '
        'experiments and preserve mesh/domain/convergence/force-ledger evidence; qualify before capacity coupling.'), '',
        ('Production targets remain proposed. Short loopback tests, finite submission bursts and a bounded '
        'soak do not establish 24-hour reliability, external latency, managed failover or real engineering claims.')]
    args.report.write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    main()
