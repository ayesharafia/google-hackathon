#!/usr/bin/env python3
"""Measure the unmodified application; all data are isolated synthetic fixtures.

Run with the repository's .venv/bin/python. Runtime output is ignored .backend data.
The API uses its documented single Uvicorn process, unchanged logging, thread and
BLAS defaults. Profiling is separate from primary timing runs.
"""
from __future__ import annotations

import argparse
import asyncio
import cProfile
import gzip
import hashlib
import importlib.util
import io
import json
import os
import platform
import pstats
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np

IMAGE = 'opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb'
ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'pyproject.toml').exists():
    ROOT = Path('/workspace/Drone-Project')
sys.path.insert(0, str(ROOT/'src'))
TICKS = os.sysconf('SC_CLK_TCK')


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def proc(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        status = Path(f'/proc/{pid}/status').read_text()
        values = {key: int(match.group(1)) for key in ('VmRSS', 'VmHWM', 'Threads')
                  if (match := re.search(rf'^{key}:\s+(\d+)', status, re.MULTILINE))}
        return {'cpu_s': (int(fields[11])+int(fields[12]))/TICKS,
                'rss_bytes': values.get('VmRSS', 0)*1024,
                'hwm_bytes': values.get('VmHWM', 0)*1024,
                'threads': values.get('Threads', 0)}
    except (FileNotFoundError, ProcessLookupError):
        return None


class Monitor:
    def __init__(self, pid):
        self.pid = pid
        self.samples = []
        self.stop_event = threading.Event()

    def start(self):
        self.started = time.perf_counter()
        self.first = proc(self.pid)
        self.client_first = proc(os.getpid())
        self.thread = threading.Thread(target=self.collect, daemon=True)
        self.thread.start()
        return self

    def collect(self):
        while not self.stop_event.is_set():
            sample = proc(self.pid)
            if sample:
                self.samples.append({'t_s': time.perf_counter()-self.started, **sample})
            self.stop_event.wait(.1)

    def finish(self):
        self.stop_event.set()
        self.thread.join()
        elapsed = time.perf_counter()-self.started
        last = proc(self.pid) or (self.samples[-1] if self.samples else self.first)
        client_last = proc(os.getpid())
        cpu = (last['cpu_s']-self.first['cpu_s']) if last and self.first else None
        peaks = []
        for before, after in zip(self.samples, self.samples[1:]):
            dt = after['t_s']-before['t_s']
            if dt > 0:
                peaks.append(100*(after['cpu_s']-before['cpu_s'])/dt)
        return {'elapsed_s': elapsed, 'cpu_s': cpu,
                'cpu_mean_pct_one_core': 100*cpu/elapsed if cpu is not None else None,
                'cpu_peak_pct_100ms': max(peaks, default=0),
                'peak_sampled_rss_bytes': max((s['rss_bytes'] for s in self.samples), default=0),
                'process_hwm_bytes': last['hwm_bytes'] if last else None,
                'max_threads': max((s['threads'] for s in self.samples), default=0),
                'load_generator_cpu_s': client_last['cpu_s']-self.client_first['cpu_s'],
                'samples': self.samples}


def metadata():
    def read(path):
        p = Path(path)
        return p.read_text().strip() if p.exists() else None
    return {'utc': datetime.now(UTC).isoformat(),
            'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'python': sys.version, 'platform': platform.platform(), 'visible_cpus': os.cpu_count(),
            'cpu_model': next((s.split(':', 1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines()
                               if s.startswith('model name')), None),
            'cpu_max': read('/sys/fs/cgroup/cpu.max'), 'memory_max': read('/sys/fs/cgroup/memory.max'),
            'numpy': np.__version__, 'httpx': httpx.__version__, 'docker_image': IMAGE,
            'workload_fixture': 'conditioned CT/CQ V4 hover, energy and axial climb; analytic inputs only',
            'numeric_thread_env': {k: os.environ.get(k) for k in
                                   ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
            'api_config': 'one Uvicorn process, default thread/BLAS settings and access logs; loopback HTTP',
            'cpu_convention': '100% = one CPU core; host quota is cpu.max quota/period',
            'sampling': 'API process /proc every 100 ms; Linux VmHWM; per-container cgroup CPU and memory.peak',
            'latency': 'monotonic request start through full response body; closed-loop zero think time'}


class Server:
    def __init__(self, data, log_dir):
        self.data = Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        self.token = secrets.token_urlsafe(32)
        self.auth = {'Authorization': 'Bearer '+self.token}
        self.env = {**os.environ, 'PHYSIMESH_API_TOKEN': self.token,
                    'PHYSIMESH_DATA_ROOT': str(self.data), 'PHYSIMESH_DB_PATH': str(self.data/'jobs.sqlite'),
                    'MPLCONFIGDIR': '/workspace/.cache/matplotlib', 'XDG_CACHE_HOME': '/workspace/.cache'}
        self.log = (log_dir/'server.log').open('ab')
        started = time.perf_counter()
        self.process = subprocess.Popen([str(ROOT/'.venv/bin/python'), '-m', 'uvicorn',
            'physimesh.api.app:app_from_environment', '--factory', '--host', '127.0.0.1',
            '--port', str(self.port)], cwd=ROOT, env=self.env, stdout=self.log,
            stderr=subprocess.STDOUT, start_new_session=True)
        self.start_monitor = Monitor(self.process.pid).start()
        self.client = httpx.Client(base_url=self.url, headers=self.auth, timeout=120, trust_env=False)
        while time.perf_counter()-started < 60:
            if self.process.poll() is not None:
                raise RuntimeError(f'API exited {self.process.returncode}; inspect {log_dir}/server.log')
            try:
                response = self.client.get('/api/health')
                if response.status_code == 200 and response.json()['status'] == 'ok':
                    self.startup_s = time.perf_counter()-started
                    self.startup_resources = self.start_monitor.finish()
                    break
            except httpx.TransportError:
                pass
            time.sleep(.02)
        else:
            raise RuntimeError('API startup timed out')

    def request(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response

    def seed(self, count):
        users = []
        for _ in range(count):
            project = self.request('POST', '/api/drone/projects/examples/realistic').json()
            base = '/api/drone/projects/'+project['project_id']
            rev = self.request('POST', base+'/revisions', json={'expected_version': project['draft_version']}).json()
            report = self.request('POST', base+'/studies', json={'revision_sha256': rev['revision_sha256']}).json()
            assert report['outcome'] == 'feasible'
            assert report['schema_version'] == 'local_mission_capacity_v4'
            assert abs(report['payload_lower_bound_kg']-4.2531506527296115) < 1e-7
            users.append({'base': base, 'study': report['study_sha256'],
                          'snapshot': json.loads(project['snapshot_json']), 'version': project['draft_version']})
        return users

    def stop(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.client.close()
        self.log.close()


def distribution(values):
    if not values:
        return {'n': 0}
    a = np.asarray(values, dtype=float)
    return {'n': len(values), 'mean': float(a.mean()), 'min': float(a.min()),
            'p50': float(np.percentile(a, 50)), 'p95': float(np.percentile(a, 95)),
            'p99': float(np.percentile(a, 99)), 'max': float(a.max())}


async def load(server, users, workload, concurrency, seconds, directory):
    samples = []
    transactions = []
    errors = []
    statuses = Counter()
    ready = asyncio.Event()
    deadlines = {}

    async def worker(index):
        user = users[index]
        base = user['base']
        study = base+'/studies/'+user['study']
        paths = [('/web/workbench.html', 'html'), ('/web/js/workbench.js', 'javascript'),
                 ('/api/drone/projects', 'inventory'), (base, 'project'),
                 (base+'/inspection', 'inspection'), (study, 'study_read'),
                 (study+'/export', 'json_export'), (study+'/pdf', 'pdf_export')]
        client = httpx.AsyncClient(base_url=server.url, headers=server.auth,
                                   timeout=120, trust_env=False,
                                   limits=httpx.Limits(max_connections=1, max_keepalive_connections=1))
        async def call(method, path, name, **kwargs):
            started = time.perf_counter()
            status, length, error, response = 0, 0, None, None
            try:
                response = await client.request(method, path, **kwargs)
                status, length = response.status_code, len(response.content)
                if status >= 400:
                    error = response.text[:300]
            except httpx.HTTPError as exc:
                error = f'{type(exc).__name__}: {exc}'
            elapsed = time.perf_counter()-started
            samples.append({'endpoint': name, 'status': status, 'latency_ms': elapsed*1000,
                            'bytes': length, 'worker': index})
            statuses[str(status)] += 1
            if error:
                if len(errors) < 200:
                    errors.append({'endpoint': name, 'error': error, 'status': status})
                return None
            return response
        await ready.wait()
        sequence = 0
        try:
            while time.perf_counter() < deadlines['end']:
                if workload == 'browse':
                    path, name = paths[(sequence+index) % len(paths)]
                    await call('GET', path, name)
                else:
                    started = time.perf_counter()
                    snapshot = user['snapshot']
                    snapshot['identity']['description'] = f'Synthetic audit client {index} edit {sequence}'
                    response = await call('PUT', base+'/draft', 'draft_save',
                                          json={'expected_version': user['version'],
                                                'snapshot_json': json.dumps(snapshot)})
                    if response is not None:
                        user['version'] = response.json()['draft_version']
                        frozen = await call('POST', base+'/revisions', 'freeze',
                                            json={'expected_version': user['version']})
                        if frozen is not None:
                            report = await call('POST', base+'/studies', 'study_evaluate',
                                json={'revision_sha256': frozen.json()['revision_sha256']})
                            if report is not None and report.json().get('outcome') == 'feasible':
                                transactions.append((time.perf_counter()-started)*1000)
                            elif report is not None:
                                errors.append({'endpoint': 'study_evaluate', 'error': 'non-feasible fixture outcome'})
                sequence += 1
                if server.process.poll() is not None:
                    break
        finally:
            await client.aclose()

    tasks = [asyncio.create_task(worker(i)) for i in range(concurrency)]
    await asyncio.sleep(0)
    monitor = Monitor(server.process.pid).start()
    started = time.perf_counter()
    deadlines['end'] = started+seconds
    ready.set()
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter()-started
    resources = monitor.finish()
    grouped = defaultdict(list)
    for sample in samples:
        grouped[sample['endpoint']].append(sample['latency_ms'])
    with gzip.open(directory/'requests.jsonl.gz', 'wt') as fh:
        for sample in samples:
            fh.write(json.dumps(sample)+'\n')
    successful = [s for s in samples if 200 <= s['status'] < 400]
    return {'workload': workload, 'concurrency': concurrency, 'configured_seconds': seconds,
            'elapsed_s_including_drain': elapsed, 'total_requests': len(samples),
            'successful_requests': len(successful), 'status_counts': dict(statuses),
            'errors': errors, 'request_latency_ms': distribution([s['latency_ms'] for s in samples]),
            'successful_request_latency_ms': distribution([s['latency_ms'] for s in successful]),
            'endpoints_latency_ms': {k: distribution(v) for k, v in grouped.items()},
            'throughput_rps': len(successful)/elapsed,
            'workflow_latency_ms': distribution(transactions),
            'completed_workflows': len(transactions), 'workflow_throughput_per_s': len(transactions)/elapsed,
            'resources': resources, 'server_exit_code': server.process.poll(),
            'raw_samples': str(directory/'requests.jsonl.gz')}


def api(args):
    output = args.output.resolve()
    dump(output/'metadata.json', metadata())
    summary = {'startup_runs': [], 'load_runs': [], 'export_runs': []}
    for repeat in range(1, 6):
        directory = output/f'startup-{repeat}'
        server = Server(directory/'data', directory)
        try:
            server.request('GET', '/web/workbench.html')
            summary['startup_runs'].append({'repeat': repeat, 'startup_s': server.startup_s,
                                           'resources': server.startup_resources})
        finally:
            server.stop()
    dump(output/'api-results.json', summary)
    for repeat in range(1, args.repeats+1):
        # Rotate concurrency order to distribute order/warm-cache effects.
        levels = [1, 10, 25, 50]
        levels = levels[repeat-1:]+levels[:repeat-1]
        for workload in ('browse', 'author'):
            for concurrency in levels:
                directory = output/f'{workload}-c{concurrency}-r{repeat}'
                server = Server(directory/'data', directory)
                try:
                    users = server.seed(50)
                    # Separately label cold versus repeated exports; do not warm every study.
                    if concurrency == 1 and workload == 'browse':
                        path = users[0]['base']+'/studies/'+users[0]['study']+'/pdf'
                        for phase in ('first_render', 'repeated_export', 'repeated_export'):
                            monitor = Monitor(server.process.pid).start()
                            started = time.perf_counter()
                            exported = server.request('GET', path).content
                            summary['export_runs'].append({'repeat': repeat, 'phase': phase,
                                'latency_ms': (time.perf_counter()-started)*1000,
                                'sha256': hashlib.sha256(exported).hexdigest(), 'resources': monitor.finish()})
                    # Equal seeded inventory and fixed per-user fixtures across all trials.
                    for user in users[:concurrency]:
                        server.request('GET', user['base']+'/inspection')
                    server.request('GET', '/api/drone/projects')
                    result = asyncio.run(load(server, users, workload, concurrency, args.seconds, directory))
                    result['repeat'] = repeat
                    result['startup_s'] = server.startup_s
                    result['seeded_projects'] = 50
                    dump(directory/'result.json', result)
                    summary['load_runs'].append(result)
                    dump(output/'api-results.json', summary)
                    lat = result['request_latency_ms']
                    print(f"{workload} c={concurrency} r={repeat}: {result['throughput_rps']:.2f} rps, "
                          f"p50/p95/p99={lat.get('p50', 0):.1f}/{lat.get('p95', 0):.1f}/{lat.get('p99', 0):.1f} ms, "
                          f"statuses={result['status_counts']}", flush=True)
                finally:
                    server.stop()


def simulations(args):
    from physimesh.core.artifacts import ArtifactStore
    from physimesh.core.jobs import Budgets, JobLedger
    from physimesh.solver import runner
    from physimesh.solver.openfoam_cases import refinement_levels
    module_spec = importlib.util.spec_from_file_location('demo_run', ROOT/'scripts/demo_run.py')
    demo = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(demo)
    original = runner.docker_run_args
    def measured_args(image, case, command, budgets):
        command = list(command)
        script = command[-1]
        script = script.replace('cat /sys/fs/cgroup/memory.peak; exit $stage_status',
            "cat /sys/fs/cgroup/memory.peak; printf '\\nAUDIT_CPU_STAT_BEGIN\\n'; "
            "cat /sys/fs/cgroup/cpu.stat; printf 'AUDIT_CPU_STAT_END\\n'; exit $stage_status")
        command[-1] = script
        return original(image, case, command, budgets)
    # Runtime measurement only: same application runner, stage commands, inputs and isolation.
    runner.docker_run_args = measured_args
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    specs = dict(zip(('coarse', 'medium', 'fine'), refinement_levels(demo.demo_spec(args.iterations), 1.5, 3)))
    summary = {'image': IMAGE, 'iteration_cap': args.iterations, 'runs': []}
    for repeat in range(1, args.repeats+1):
        levels = args.levels.split(',')
        if repeat % 2 == 0:
            levels.reverse()
        for level in levels:
            directory = output/f'{level}-r{repeat}'
            directory.mkdir(parents=True, exist_ok=True)
            ledger = JobLedger(directory/'jobs.sqlite')
            store = ArtifactStore(directory/'artifacts')
            prepare_start = time.perf_counter()
            inputs = demo.registered_case_files(specs[level])
            preparation_s = time.perf_counter()-prepare_start
            profile = cProfile.Profile()
            monitor = Monitor(os.getpid()).start()
            started = time.perf_counter()
            if args.profile_runner:
                profile.enable()
            job_id = runner.run_case(ledger, store, inputs, IMAGE, Budgets(2, 4, 5, 7200, 512), directory/'runs')
            if args.profile_runner:
                profile.disable()
            elapsed = time.perf_counter()-started
            resources = monitor.finish()
            if args.profile_runner:
                profile.dump_stats(str(directory/'runner.prof'))
                listing = io.StringIO()
                pstats.Stats(profile, stream=listing).strip_dirs().sort_stats('cumulative').print_stats(45)
                (directory/'runner-profile.txt').write_text(listing.getvalue())
            job = ledger.get(job_id)
            if job.state != 'completed':
                dump(directory/'failure.json', {'state': job.state, 'reason': job.reason})
                raise RuntimeError(f'Simulation {level} r{repeat} failed: {job.reason}')
            case = Path(job.payload['case_dir'])
            record = json.loads((case/'run_record.json').read_text())
            stages = []
            for item in record['stages']:
                log = (case/(item['stage'].split()[0]+'.log')).read_text()
                cpu_match = re.search(r'AUDIT_CPU_STAT_BEGIN\n(.*?)AUDIT_CPU_STAT_END', log, re.DOTALL)
                cpu = {k: int(v) for k, v in re.findall(r'^(\w+) (\d+)$', cpu_match[1], re.MULTILINE)} if cpu_match else {}
                solver_cpu = re.findall(r'ExecutionTime = ([\d.]+) s', log)
                stages.append({**item, 'container_cpu_stat': cpu,
                    'cpu_s': cpu.get('usage_usec', 0)/1e6,
                    'cpu_mean_pct_one_core': cpu.get('usage_usec', 0)/1e6/item['wall_time_s']*100,
                    'container_user_s': cpu.get('user_usec', 0)/1e6,
                    'container_system_s': cpu.get('system_usec', 0)/1e6,
                    'solver_reported_execution_time_s': float(solver_cpu[-1]) if solver_cpu else None})
            metrics = demo.metrics(case)
            result = {'level': level, 'repeat': repeat, 'job_id': job_id, 'case_dir': str(case),
                      'preparation_s': preparation_s, 'caller_elapsed_s': elapsed,
                      'metrics': metrics, 'stages': stages, 'orchestrator_resources': resources,
                      'disk_bytes': record['disk_bytes'],
                      'input_hashes_sha256': hashlib.sha256(json.dumps(record['inputs'], sort_keys=True).encode()).hexdigest(),
                      'profile_note': 'Python orchestration cProfile enabled' if args.profile_runner else 'profiling disabled'}
            dump(directory/'result.json', result)
            summary['runs'].append(result)
            dump(output/'simulation-results.json', summary)
            print(f"{level} r={repeat}: {metrics['cells']} cells, {metrics['iterations']} iterations, "
                  f"{elapsed:.2f}s, peak cgroup {metrics['peak_memory_bytes']/2**20:.1f} MiB; "
                  f"stages="+str([(s['stage'], round(s['wall_time_s'], 2)) for s in stages]), flush=True)
    runner.docker_run_args = original


def profiles(args):
    from physimesh.api.app import create_app
    from physimesh.api.settings import Settings
    from physimesh.projects.realistic import create_realistic_example
    output = args.output.resolve()
    directory = output/'function-profile'
    data = directory/'data'
    app = create_app(Settings(data, data/'jobs.sqlite', secrets.token_urlsafe(32), None))
    projects = app.state.projects
    studies = app.state.studies
    project = create_realistic_example(projects)
    pid = project['project_id']
    rev = projects.freeze(pid, project['draft_version'], 'screening')['revision_sha256']
    result = studies.run(pid, rev)
    study = result['study_sha256']
    changed = json.loads(project['snapshot_json'])
    changed['masses']['items'][0]['mass_kg'] += .2
    projects.save(pid, project['draft_version'], json.dumps(changed))
    second_revision = projects.freeze(pid, project['draft_version']+1, 'screening')['revision_sha256']
    second = studies.run(pid, second_revision)
    comparison = studies.compare(pid, study, second['study_sha256'])
    assert comparison['comparable_numeric_results']
    assert abs(comparison['payload_change_kg']+.2) < 1e-7
    raw = studies.export(pid, study)
    pdf, receipt = studies.pdf(pid, study)
    assert pdf.startswith(b'%PDF-')
    assert receipt['study_json_sha256'] == hashlib.sha256(raw).hexdigest()
    assert receipt['pdf_sha256'] == hashlib.sha256(pdf).hexdigest()
    actions = {'study_evaluate': lambda: studies.run(pid, rev),
               'pdf_export': lambda: studies.pdf(pid, study),
               'study_export': lambda: studies.export(pid, study),
               'project_freeze': lambda: projects.freeze(pid, project['draft_version']+1, 'screening'),
               'study_compare': lambda: studies.compare(pid, study, second['study_sha256'])}
    results = {}
    for name, action in actions.items():
        profiler = cProfile.Profile()
        profiler.enable()
        times = []
        for _ in range(20):
            started = time.perf_counter()
            action()
            times.append((time.perf_counter()-started)*1000)
        profiler.disable()
        profiler.dump_stats(str(directory/(name+'.prof')))
        listing = io.StringIO()
        pstats.Stats(profiler, stream=listing).strip_dirs().sort_stats('cumulative').print_stats(40)
        (directory/(name+'.txt')).write_text(listing.getvalue())
        rows = []
        stats = pstats.Stats(profiler)
        for (filename, line, func), (primitive, calls, own, cumulative, callers) in stats.stats.items():
            rows.append({'file': filename, 'line': line, 'function': func, 'calls': calls,
                         'self_s': own, 'cumulative_s': cumulative})
        rows.sort(key=lambda row: row['cumulative_s'], reverse=True)
        results[name] = {'profiled_latency_ms': distribution(times), 'top_functions': rows[:60]}
    # Measure project listing growth using the exact repository create/list code.
    scaling = []
    raw_snapshot = project['snapshot_json']
    count = 1
    for target in (1, 100, 500, 1000):
        while count < target:
            projects.repository.create(f'Audit inventory {count}', raw_snapshot)
            count += 1
        times, sizes = [], []
        profiler = cProfile.Profile()
        profiler.enable()
        for _ in range(3):
            started = time.perf_counter()
            listing = projects.repository.list_projects()
            encoded = json.dumps({'projects': listing}).encode()
            times.append((time.perf_counter()-started)*1000)
            sizes.append(len(encoded))
        profiler.disable()
        stats = pstats.Stats(profiler)
        db_calls = sum(v[1] for k, v in stats.stats.items() if "execute' of 'sqlite3.Connection'" in k[2])
        scaling.append({'projects': target, 'profiled_list_plus_json_latency_ms': distribution(times),
                        'response_bytes': sizes, 'sql_execute_calls_3_runs': db_calls})
    results['inventory_scaling'] = scaling
    results['functional_checks'] = {'changed_mass_study_comparison': 'passed',
                                     'retained_json_and_pdf_sha256_binding': 'passed'}
    dump(output/'function-results.json', results)
    print('Function profiles and inventory scaling complete.', flush=True)


def main():
    os.environ.setdefault('MPLCONFIGDIR', '/workspace/.cache/matplotlib')
    os.environ.setdefault('XDG_CACHE_HOME', '/workspace/.cache')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('api', 'simulations', 'profiles'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--levels', default='coarse,medium')
    parser.add_argument('--iterations', type=int, default=3000)
    parser.add_argument('--profile-runner', action='store_true', help='Diagnostic only; exclude from primary timing results')
    args = parser.parse_args()
    if args.seconds <= 0 or args.repeats < 1:
        parser.error('seconds and repeats must be positive')
    if any(level not in ('coarse', 'medium', 'fine') for level in args.levels.split(',')):
        parser.error('levels must be selected from coarse,medium,fine')
    result_name = {'api': 'api-results.json', 'simulations': 'simulation-results.json',
                   'profiles': 'function-results.json'}[args.phase]
    if (args.output/result_name).exists():
        parser.error('this phase already has results in the output directory; select a new output')
    args.output.mkdir(parents=True, exist_ok=True)
    {'api': api, 'simulations': simulations, 'profiles': profiles}[args.phase](args)


if __name__ == '__main__':
    main()
