#!/usr/bin/env python3
"""Repeated hosted PostgreSQL save/submission and cold/warm export measurements.

Synthetic credentials remain in process memory. PostgreSQL service state is private,
ignored and managed by platform_services.py. No production SLO is implied.
"""
import argparse
import asyncio
import gzip
import json
import secrets
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from benchmark_baseline import Monitor, Server, distribution, dump, metadata


async def requests(server, users, mode, concurrency, seconds, directory):
    samples = []
    ready = asyncio.Event()
    ending = {}
    async def user_run(user):
        async with httpx.AsyncClient(base_url=server.url, headers=user.get('auth', server.auth),
                                     timeout=120, trust_env=False) as client:
            await ready.wait()
            sequence = 0
            while True:
                started = time.perf_counter()
                try:
                    if mode == 'save':
                        user['snapshot']['identity']['description'] = f'Synthetic load edit {sequence}'
                        response = await client.put(user['base']+'/draft', json={
                            'expected_version': user['version'], 'snapshot_json': json.dumps(user['snapshot'])})
                        if response.status_code == 200:
                            user['version'] = response.json()['draft_version']
                    elif mode == 'submission':
                        response = await client.post(user['base']+'/studies', json={'revision_sha256': user['revision']})
                    else:
                        response = await client.get(user['base']+'/studies/'+user['study']+'/pdf')
                    if mode == 'submission' and response.status_code == 202:
                        user['submitted_job'] = response.json()['job_id']
                    status = response.status_code
                    length = len(response.content)
                except httpx.HTTPError:
                    status, length = 0, 0
                samples.append({'latency_ms': (time.perf_counter()-started)*1000, 'status': status, 'bytes': length})
                sequence += 1
                if mode in ('submission', 'cold_export') or time.perf_counter() >= ending['time']:
                    break
    tasks = [asyncio.create_task(user_run(user)) for user in users[:concurrency]]
    await asyncio.sleep(0)
    monitor = Monitor(server.process.pid).start()
    started = time.perf_counter()
    ending['time'] = started+seconds
    ready.set()
    await asyncio.gather(*tasks)
    elapsed, resources = time.perf_counter()-started, monitor.finish()
    directory.mkdir(parents=True, exist_ok=True)
    with gzip.open(directory/'requests.jsonl.gz', 'wt') as stream:
        for sample in samples:
            stream.write(json.dumps(sample)+'\n')
    ok = sum(200 <= s['status'] < 300 for s in samples)
    return {'workload': mode, 'concurrency': concurrency, 'request_latency_ms': distribution(
        [s['latency_ms'] for s in samples]), 'total_requests': len(samples), 'successful_requests': ok,
        'throughput_rps': ok/elapsed, 'elapsed_s': elapsed, 'status_counts': dict(Counter(str(s['status']) for s in samples)),
        'resources': resources}


def hosted_server(directory, url):
    # Server reads this subclass's environment override before launching Uvicorn.
    server = Server(directory/'data', directory, environment={
        'PHYSIMESH_MODE': 'hosted', 'PHYSIMESH_DATABASE_URL': url, 'PHYSIMESH_POOL_SIZE': '8'})
    from physimesh.api.app import create_app
    from physimesh.api.settings import Settings
    bootstrap = create_app(Settings(server.data, server.data/'jobs.sqlite', '', None,
                                    hosted_mode=True, database_url=url))
    users = []
    for index in range(50):
        password, email = secrets.token_urlsafe(24), 'load-'+secrets.token_hex(8)+'@example.test'
        uid = bootstrap.state.identity.provision(email, password=password)
        org = bootstrap.state.identity.organization(uid, f'Synthetic load user {index}')
        token = server.client.post('/api/drone/platform/login', json={'email': email, 'password': password})
        token.raise_for_status()
        headers = {'Authorization': 'Bearer '+token.json()['token'], 'X-Organization-ID': org}
        response = server.client.post('/api/drone/projects/examples/realistic', headers=headers)
        response.raise_for_status()
        project = response.json()
        base = '/api/drone/projects/'+project['project_id']
        rev = server.client.post(base+'/revisions', headers=headers, json={'expected_version': project['draft_version']})
        rev.raise_for_status()
        users.append({'base': base, 'auth': headers, 'version': project['draft_version'],
                      'snapshot': json.loads(project['snapshot_json']), 'revision': rev.json()['revision_sha256']})
    bootstrap.state.metadata.close()
    return server, users


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('exports', 'postgres'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--service-state', type=Path, default=ROOT/'.backend/platform-services/private.json')
    args = parser.parse_args()
    output = args.output.resolve()
    meta = metadata()
    meta['qualification'] = ('Local SQLite exports or hosted-mode API with disposable PostgreSQL and private files; '
        'API-only process resources, excludes PostgreSQL container/load client; source build, one process. '
        'Submission/cold export are finite bursts: one request/user/trial; tail estimates at small n are descriptive.')
    dump(output/'metadata.json', meta)
    results = {'runs': []}
    for repeat in range(1, args.repeats+1):
        for concurrency in (1, 10, 25, 50):
            directory = output/f'{args.phase}-c{concurrency}-r{repeat}'
            if args.phase == 'exports':
                server = Server(directory/'data', directory)
                users = server.seed(50)
                modes = ('cold_export', 'warm_export')
            else:
                private = json.loads(args.service_state.read_text())
                server, users = hosted_server(directory, private['url'])
                modes = ('submission', 'save')
            try:
                for mode in modes:
                    before_db = None
                    if args.phase == 'postgres':
                        before_db = subprocess.check_output(['docker', 'exec', private['container'], 'cat',
                            '/sys/fs/cgroup/cpu.stat'], text=True)
                    measured = asyncio.run(requests(server, users, mode, concurrency, args.seconds, directory/mode))
                    if before_db is not None:
                        after_db = subprocess.check_output(['docker', 'exec', private['container'], 'cat',
                            '/sys/fs/cgroup/cpu.stat'], text=True)
                        memory = subprocess.check_output(['docker', 'exec', private['container'], 'cat',
                            '/sys/fs/cgroup/memory.peak'], text=True)
                        usage = lambda raw: int(dict(line.split() for line in raw.splitlines())['usage_usec'])/1e6
                        measured['database_resources'] = {'cpu_s': usage(after_db)-usage(before_db),
                            'process_container_hwm_bytes': int(memory), 'note': 'cgroup peak includes all earlier test service work/cache'}
                    measured['repeat'] = repeat
                    results['runs'].append(measured)
                    dump(output/'results.json', results)
                    if mode == 'submission':
                        for user in users[:concurrency]:
                            if user.get('submitted_job'):
                                cancelled = server.client.post(user['base']+'/jobs/'+user['submitted_job']+'/cancel',
                                                               headers=user['auth'])
                                cancelled.raise_for_status()
                    if mode == 'cold_export':
                        for user in users[:concurrency]:
                            server.request('GET', user['base']+'/studies/'+user['study']+'/pdf')
                    print(f"{mode} c={concurrency} r={repeat}: p95={measured['request_latency_ms']['p95']:.1f} ms, "
                          f"{measured['throughput_rps']:.2f} req/s, statuses={measured['status_counts']}", flush=True)
            finally:
                server.stop()
    # Descriptive per-trial medians, never pooled percentiles.
    for mode in {r['workload'] for r in results['runs']}:
        for concurrency in (1, 10, 25, 50):
            runs = [r for r in results['runs'] if r['workload'] == mode and r['concurrency'] == concurrency]
            print(mode, concurrency, 'median trial p95', statistics.median(r['request_latency_ms']['p95'] for r in runs))


if __name__ == '__main__':
    main()
