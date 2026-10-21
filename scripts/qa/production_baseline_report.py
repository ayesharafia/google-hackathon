#!/usr/bin/env python3
"""Aggregate repeated raw baseline observations; never infer unrun campaigns."""
import argparse
import json
import statistics
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    api = json.loads((args.directory/'api-results.json').read_text())
    function = json.loads((args.directory/'function-results.json').read_text())
    metadata = json.loads((args.directory/'metadata.json').read_text())
    startup = statistics.median(r['startup_s'] for r in api['startup_runs'])
    lines = ['# V4 production baseline — 6 October 2026', '',
             (f"Unoptimized application at `{metadata['commit']}`. Analytic conditioned CT/CQ V4 fixture; "
             'hover, ordered energy and axial climb. One Uvicorn process, loopback HTTP, closed-loop '
             'clients without think time. Three 15-second trials per load/concurrency; drain time included '
             'in throughput. Profiling is separate from timing. This is a local resource baseline, '
             'not a hosted SLO or aircraft validation.'), '',
             (f"Cold startup: five runs, median **{startup:.3f} s** to health; "
             f"median high-water RAM **{statistics.median(r['resources']['process_hwm_bytes'] for r in api['startup_runs'])/2**20:.1f} MiB**."), '',
             ('Numbers below are medians of the three per-trial distributions, not pooled percentiles. '
             'CPU 100% means one core; peak RAM uses process VmHWM (includes seeding).'), '',
             '| Workload | Users | p50 ms | p95 ms | p99 ms | Successful req/s | Failures, 3 runs | CPU % | Peak RAM MiB |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for workload in ('browse', 'author'):
        for concurrency in (1, 10, 25, 50):
            runs = [r for r in api['load_runs'] if r['workload'] == workload and r['concurrency'] == concurrency]
            assert len(runs) == 3
            values = [statistics.median(r['request_latency_ms'][p] for r in runs) for p in ('p50', 'p95', 'p99')]
            throughput = statistics.median(r['throughput_rps'] for r in runs)
            failures = sum(r['total_requests']-r['successful_requests'] for r in runs)
            cpu = statistics.median(r['resources']['cpu_mean_pct_one_core'] for r in runs)
            ram = max(r['resources']['process_hwm_bytes'] for r in runs)/2**20
            lines.append(f'| {workload} | {concurrency} | {values[0]:.1f} | {values[1]:.1f} | {values[2]:.1f} | '
                         f'{throughput:.2f} | {failures} | {cpu:.1f} | {ram:.1f} |')
    lines += ['', ('Browse cycles HTML, JavaScript, inventory, detail, inspection, retained study, JSON '
              'and PDF. Author performs save → freeze → study on an individual project per client. '
              'Changing descriptions makes distinct immutable studies; it does not avoid solver evaluation.'), '']
    for phase in ('first_render', 'repeated_export'):
        runs = [r for r in api['export_runs'] if r['phase'] == phase]
        lines.append(f"PDF {phase}: {len(runs)} observations, median "
                     f"{statistics.median(r['latency_ms'] for r in runs):.1f} ms. "
                     'The baseline renders every time; repeated bytes are deterministic.')
    lines += ['', 'Separate profiled actions (20 calls each; profiling overhead applies):']
    for name, value in function.items():
        if 'profiled_latency_ms' in value:
            lines.append(f"- {name}: median {value['profiled_latency_ms']['p50']:.2f} ms.")
    scale = function['inventory_scaling'][-1]
    lines += ['', (f"At 1,000 projects: {scale['response_bytes'][0]:,} bytes; "
              f"{scale['sql_execute_calls_3_runs']//3:,} SQL executes per listing; "
              f"profiled listing/serialization median {scale['profiled_list_plus_json_latency_ms']['p50']:.2f} ms."), '']
    simulations = args.directory/'simulation-results.json'
    if simulations.exists():
        data = json.loads(simulations.read_text())
        lines += ['| Simulation | Repeats | Wall median/range s | Container CPU mean % | Peak cgroup RAM MiB |',
                  '|---|---:|---:|---:|---:|']
        for level in sorted({r['level'] for r in data['runs']}):
            runs = [r for r in data['runs'] if r['level'] == level]
            times = [r['caller_elapsed_s'] for r in runs]
            cpu = [sum(s['cpu_s'] for s in r['stages'])/r['caller_elapsed_s']*100 for r in runs]
            lines.append(f"| {level} | {len(runs)} | {statistics.median(times):.2f} / "
                         f"{min(times):.2f}–{max(times):.2f} | {statistics.median(cpu):.1f} | "
                         f"{max(r['metrics']['peak_memory_bytes'] for r in runs)/2**20:.1f} |")
        lines += ['', ('Pinned sphere verification; cgroup peak includes charged cache and differs from RSS. '
                  'Per-stage meshing/check/solve CPU and time plus retained metrics are in the raw receipts. '
                  'No installed rotor or aircraft simulation was run.')]
    else:
        lines += ['Simulation measurements are still running; this report currently establishes the API baseline only.']
    postprocess = args.directory/'postprocessing-results.json'
    if postprocess.exists():
        records = json.loads(postprocess.read_text())['runs']
        lines += ['', '| Native postprocessing | Runs | Wall median s | CPU median s | Peak process RSS MiB |',
                  '|---|---:|---:|---:|---:|']
        for level in ('coarse', 'medium'):
            runs = [r for r in records if r['level'] == level]
            lines.append(f"| {level} | {len(runs)} | {statistics.median(r['wall_s'] for r in runs):.3f} | "
                         f"{statistics.median(r['cpu_s'] for r in runs):.3f} | "
                         f"{max(r['peak_process_rss_bytes'] for r in runs)/2**20:.1f} |")
        lines += ['', ('Fresh processes verify unchanged native source hashes. Integration timing excludes imports; '
                  'RSS includes imports. Pressure/shear integration and reconciliation use registered sphere units.')]
    lines += ['', '## Five bottlenecks and proposed fixes', '',
              ('1. Repeated PDF rendering: ReportLab layout dominates its profile. Reuse verified bytes '
              'bound to accepted JSON, frozen snapshot, renderer source and dependency identity; queue first render.'),
              ('2. SQLite write contention: 50-user runs include unexpected failures. Use PostgreSQL row locks, '
              'short transactions and bounded pools; retain optimistic versions and explicit 503 overload responses.'),
              ('3. Repeated work: identical study specifications still run LP; freeze repeatedly loads YAML. '
              'Reuse accepted studies only after source/spec checks; cache immutable schema after checksum validation.'),
              ('4. Inventory fan-out: entire snapshots and all histories are included. Use keyset pages of summaries '
              'and separate bounded history/detail endpoints; prove response/query bounds at 1,000 projects.'),
              ('5. Serial CFD and stage containers: benchmark stages and test controlled MPI/pipeline variants. '
              'Accept only equivalent numerical evidence with resource/isolation limits preserved.'), '',
              '## Evidence and limits', '',
              ('Raw observations are retained under `.backend/production-baseline-2026-10-06`; '
              'the [checked-in receipt archive](production-baseline-2026-10-06.tar.gz) contains sanitized metrics and request samples. '
              'Short tests do not prove 24-hour endurance, hosted targets, RPO/RTO or aircraft accuracy. '
              'Dedicated concurrent cold/cached export trials and hosted-adapter load tests remain separate acceptance work.')]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    main()
