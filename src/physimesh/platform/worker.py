"""Study/report worker with fenced acceptance and bounded isolated subprocesses."""
import argparse
import hashlib
import json
import os
import resource
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .database import Overloaded
from .identity import Denied
from .jobs import StaleAttempt
from .scoped_artifacts import artifact_scope


def accept_publication(app, job):
    """Idempotently materialize only the ledger's accepted immutable result.

    A crash after ledger acceptance is repaired by the job-read route or a later
    worker pass. Attempt files and stale receipts never enter accepted associations.
    """
    if job['state'] != 'succeeded':
        return
    receipt = json.loads(job['result_json'])
    project_id = job['project_id']
    digest = receipt['artifact_sha256']
    with app.state.artifact_backend.open(digest) as stream:
        raw = stream.read(5_000_001)
    if len(raw) > 5_000_000 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('accepted worker artifact integrity failed')
    spec = json.loads(job['spec_json'])
    with artifact_scope(project_id):
        app.state.identity.grant_artifact(project_id, digest, len(raw))
        if job['kind'] == 'study':
            result = json.loads(raw)
            if (result['specification']['project_id'] != project_id
                    or result['specification']['revision_sha256'] != spec['revision_sha256']
                    or result['study_sha256'] != receipt['study_sha256']):
                raise ValueError('accepted worker study association failed')
            app.state.projects.repository.retain_study(project_id, spec['revision_sha256'],
                                                       receipt['study_sha256'], digest)
            app.state.studies.read(project_id, receipt['study_sha256'])
        else:
            if receipt['report_identity'] != spec['report_identity'] or not raw.startswith(b'%PDF-'):
                raise ValueError('accepted worker report association failed')
            app.state.studies.retain_pdf(project_id, spec['study_sha256'], raw, receipt['report_identity'])


def _rss(process):
    try:
        status = Path(f'/proc/{process.pid}/status').read_text()
        return int(next(line.split()[1] for line in status.splitlines() if line.startswith('VmRSS:')))*1024
    except (FileNotFoundError, StopIteration):
        return 0


@contextmanager
def _publication_lease(jobs, claim):
    """Keep leases alive during bounded object-store transfers; fence before acceptance."""
    stopped, errors = threading.Event(), []
    def renew():
        while not stopped.wait(min(5, jobs.lease_s/3)):
            try:
                jobs.heartbeat(claim, .95, 'verifying and storing attempt evidence')
            except (StaleAttempt, Overloaded, OSError) as exc:
                errors.append(exc)
                return
    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=20)
        if thread.is_alive():
            raise Overloaded('publication heartbeat did not finish')
    if errors:
        raise errors[0]


def run_one(app, worker_id, *, wall_s=120, memory_bytes=2*1024**3, disk_bytes=20_000_000):
    claim = app.state.jobs.claim(worker_id, build_sha256=app.state.build.get('build_sha256'))
    if claim is None:
        return False
    root = app.state.settings.data_root/'attempts'
    root.mkdir(parents=True, exist_ok=True)
    usage_start = resource.getrusage(resource.RUSAGE_CHILDREN)
    evidence = {}
    try:
        with tempfile.TemporaryDirectory(prefix=claim['attempt_id']+'-', dir=root) as directory:
            directory = Path(directory)
            input_file, output_file = directory/'input.json', directory/'output.json'
            input_file.write_text(json.dumps(claim, sort_keys=True))
            with (directory/'compute.log').open('wb') as log:
                process = subprocess.Popen([sys.executable, '-m', 'physimesh.platform.compute',
                                            str(input_file), str(output_file)],
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                           env={**os.environ, 'PHYSIMESH_SUPERVISOR_PID': str(os.getpid()),
                                                'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
                                                'MKL_NUM_THREADS': '1'})
                (directory/'compute.pid').write_text(str(process.pid))
                started, next_beat, peak_rss = time.monotonic(), 0., 0
                try:
                    while process.poll() is None:
                        elapsed = time.monotonic()-started
                        peak_rss = max(peak_rss, _rss(process))
                        size = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
                        if elapsed > wall_s or peak_rss > memory_bytes or size > disk_bytes:
                            raise ValueError('worker wall/RAM/disk budget exceeded')
                        if elapsed >= next_beat:
                            app.state.jobs.heartbeat(claim, .1, f'isolated computation; {elapsed:.1f} s elapsed',
                                                     resources={'wall_s': elapsed, 'peak_sampled_rss_bytes': peak_rss})
                            next_beat = elapsed+min(5, app.state.jobs.lease_s/3)
                        time.sleep(.1)
                    if process.returncode != 0:
                        log.flush()
                        failure_log = (directory/'compute.log').read_bytes()[:100000]
                        with artifact_scope(claim['project_id']):
                            evidence['log_sha256'] = app.state.projects.artifacts.put_bytes(
                                failure_log, kind='worker_attempt_log', meta={'attempt_id': claim['attempt_id']})
                        raise ValueError('isolated computation failed; no accepted result published')
                    app.state.jobs.heartbeat(claim, .95, 'verifying attempt output')
                    if not output_file.exists() or output_file.stat().st_size > 5_000_000:
                        raise ValueError('worker output missing or exceeds budget')
                    if claim['kind'] == 'study':
                        raw = output_file.read_bytes()
                        result = json.loads(raw)
                        from physimesh.drone.local_results import LocalCapacityV3, LocalCapacityV4
                        contract = LocalCapacityV4 if result.get('schema_version') == 'local_mission_capacity_v4' else LocalCapacityV3
                        contract.model_validate_json(raw)
                        with _publication_lease(app.state.jobs, claim):
                            digest = app.state.artifact_backend.put_bytes(raw, kind=result['schema_version'], meta={})
                        accepted = {'artifact_sha256': digest, 'study_sha256': result['study_sha256']}
                    else:
                        raw = output_file.with_suffix('.pdf').read_bytes()
                        if len(raw) > 5_000_000 or not raw.startswith(b'%PDF-'):
                            raise ValueError('worker PDF missing or exceeds budget')
                        receipt = json.loads(output_file.read_text())
                        with _publication_lease(app.state.jobs, claim):
                            digest = app.state.artifact_backend.put_bytes(raw, kind='retained_local_study_pdf_v1', meta=receipt)
                        accepted = {'artifact_sha256': digest, 'report_identity': receipt}
                    usage_end = resource.getrusage(resource.RUSAGE_CHILDREN)
                    accepted['resources'] = {'wall_s': time.monotonic()-started, 'peak_sampled_rss_bytes': peak_rss,
                                             'cpu_s': usage_end.ru_utime+usage_end.ru_stime-usage_start.ru_utime-usage_start.ru_stime,
                                             'application_build': app.state.build.get('build_sha256'),
                                             'limits': {'wall_s': wall_s, 'rss_bytes': memory_bytes,
                                                        'disk_bytes': disk_bytes, 'cpu_s': 60,
                                                        'virtual_memory_bytes': 2*1024**3,
                                                        'thread_environment': {'OPENBLAS_NUM_THREADS': '1',
                                                                               'OMP_NUM_THREADS': '1',
                                                                               'MKL_NUM_THREADS': '1'}}}
                    app.state.jobs.complete(claim, accepted)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        accept_publication(app, app.state.jobs.get(claim['project_id'], claim['job_id']))
    except StaleAttempt:
        # A revoked generation cannot alter the current attempt or accepted result.
        pass
    except (OSError, ValueError, KeyError, Overloaded, Denied) as exc:
        try:
            app.state.jobs.fail(claim, str(exc), retry=isinstance(exc, (OSError, Overloaded)), resources=evidence or None)
        except StaleAttempt:
            pass
    return True


def main():
    from physimesh.api.app import create_app
    from physimesh.api.settings import load_settings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    app = create_app(load_settings(os.environ))
    if not app.state.settings.hosted_mode:
        raise ValueError('durable worker requires explicit hosted mode')
    worker_id = socket.gethostname()+':'+uuid4().hex
    try:
        while True:
            worked = run_one(app, worker_id)
            if args.once:
                break
            if not worked:
                time.sleep(1)
    finally:
        app.state.metadata.close()


if __name__ == '__main__':
    main()
