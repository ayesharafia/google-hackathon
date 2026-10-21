"""Disposable synthetic hosted study/PDF journeys, never a hosted SLO or flight acceptance.

Linux parent watchdog includes setup and supervises only its own created child tree.
RSS and filesystem budgets are observational sampled stop thresholds, not quotas.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src'))


@dataclass(frozen=True)
class Budgets:
    seconds: float = 30
    requests: int = 100
    journeys: int = 2
    storage_bytes: int = 64 * 1024**2
    memory_bytes: int = 1024 * 1024**2

    def validate(self):
        if (not math.isfinite(self.seconds) or not 0 < self.seconds <= 60
                or any(isinstance(v, bool) or not isinstance(v, int)
                       for v in (self.requests, self.journeys, self.storage_bytes, self.memory_bytes))
                or not 1 <= self.requests <= 1000 or not 1 <= self.journeys <= 20
                or not 1 <= self.storage_bytes <= 256 * 1024**2
                or not 1 <= self.memory_bytes <= 2 * 1024**3):
            raise ValueError('invalid bounded smoke budgets')


class StopRun(Exception):
    pass


class Runner:
    """Serial, instrumented API journey; parent preempts blocking calls/worker.

    All API calls including setup count toward the request budget. Direct worker
    calls are local execution, not HTTP requests. No exception text is retained.
    """
    def __init__(self, client, work, budgets, save=lambda _: None):
        self.client, self.work, self.budgets, self.save = client, work, budgets, save
        self.report = {'requests': 0, 'completed_journeys': 0, 'failures': 0,
                       'stop_reason': 'running', 'request_observations': []}

    def request(self, method, path, **kwargs):
        if self.report['requests'] >= self.budgets.requests:
            raise StopRun('request_budget')
        self.report['requests'] += 1
        started = time.monotonic()
        observation = {'ordinal': self.report['requests'], 'status': None,
                       'response_bytes': None, 'error': 'unfinished_request', 'elapsed_ms': None}
        self.report['request_observations'].append(observation)
        self.save(self.report)
        try:
            response = self.client.request(method, path, **kwargs)
            observation.update(status=response.status_code, response_bytes=len(response.content), error=None)
            if response.status_code >= 400:
                raise StopRun('http_error')
            return response
        except StopRun:
            observation['error'] = 'http_error'
            raise
        except Exception:  # noqa: BLE001 - sanitize private response/transport errors
            observation['error'] = 'request_exception'
            raise StopRun('request_exception') from None
        finally:
            observation['elapsed_ms'] = round((time.monotonic()-started)*1000, 3)
            self.save(self.report)

    def execute(self, password, org):
        try:
            token = self.request('POST', '/api/drone/platform/login', json={
                'email': 'bounded@example.test', 'password': password}).json()['token']
            self.client.headers.update({'Authorization': 'Bearer '+token, 'X-Organization-ID': org})
            project = self.request('POST', '/api/drone/projects/examples/realistic').json()
            base = '/api/drone/projects/'+project['project_id']
            snapshot, version = json.loads(project['snapshot_json']), project['draft_version']
            for index in range(self.budgets.journeys):
                snapshot['identity']['description'] = f'Synthetic bounded journey {index}'
                saved = self.request('PUT', base+'/draft', json={
                    'expected_version': version, 'snapshot_json': json.dumps(snapshot)}).json()
                version = saved['draft_version']
                revision = self.request('POST', base+'/revisions', json={'expected_version': version}).json()
                submitted = self.request('POST', base+'/studies', json={
                    'revision_sha256': revision['revision_sha256']}).json()
                study_result = self.finish_job(base, submitted)
                study_path = base+'/studies/'+study_result['study_sha256']
                study = self.request('GET', study_path).json()
                if study['outcome'] != 'feasible':
                    raise StopRun('synthetic_study_mismatch')
                first = self.request('GET', study_path+'/pdf')
                if first.status_code != 202:
                    raise StopRun('expected_report_job')
                self.finish_job(base, first.json())
                pdf = self.request('GET', study_path+'/pdf').content
                if not pdf.startswith(b'%PDF-') or self.request('GET', study_path+'/pdf').content != pdf:
                    raise StopRun('pdf_integrity_mismatch')
                self.request('GET', '/api/drone/projects')
                self.request('GET', base+'/history/studies')
                self.report['completed_journeys'] += 1
                self.save(self.report)
            self.report['stop_reason'] = 'journey_budget'
        except StopRun as exc:
            self.report['stop_reason'] = str(exc)
            if str(exc) not in ('request_budget',):
                self.report['failures'] += 1
        except Exception:  # noqa: BLE001 - retain only an allowlisted failure label
            self.report.update(stop_reason='journey_exception', failures=self.report['failures']+1)
        finally:
            self.save(self.report)
        return self.report

    def finish_job(self, base, submitted):
        if not self.work():
            raise StopRun('worker_did_not_claim')
        job = self.request('GET', base+'/jobs/'+submitted['job_id']).json()
        if job['state'] != 'succeeded':
            raise StopRun('job_not_succeeded')
        return json.loads(job['result_json'])


def child(root, budgets):
    budgets.validate()
    from fastapi.testclient import TestClient

    from physimesh.api.app import create_app
    from physimesh.api.settings import Settings
    from physimesh.platform.worker import run_one

    # Compute children consult environment. Remove inherited provider/production
    # settings even when a QA test invokes this internal child directly.
    for name in list(os.environ):
        if name.startswith('PHYSIMESH_'):
            del os.environ[name]
    os.environ.update(PHYSIMESH_MODE='hosted', PHYSIMESH_DATA_ROOT=str(root),
                      PHYSIMESH_DB_PATH=str(root/'jobs.sqlite'))
    app = create_app(Settings(root, root/'jobs.sqlite', '', None, hosted_mode=True))
    try:
        password = secrets.token_urlsafe(24)
        owner = app.state.identity.provision('bounded@example.test', password=password)
        org = app.state.identity.organization(owner, 'Disposable synthetic bounded soak')

        def save(report):
            # Internal progress may be replaced; the user receipt is exclusive.
            temporary = root/'progress.next'
            temporary.write_text(json.dumps(report, allow_nan=False), encoding='utf-8')
            temporary.replace(root/'progress.json')

        with TestClient(app) as client:
            Runner(client, lambda: run_one(app, 'bounded-synthetic-worker', wall_s=30),
                   budgets, save).execute(password, org)
    finally:
        app.state.metadata.close()


def processes():
    """Linux PID -> (parent, start ticks, RSS bytes, HWM bytes); tolerate exit races."""
    values = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry/'stat').read_text()
            fields = raw[raw.rindex(')')+2:].split()
            if fields[0] == 'Z':
                continue
            status = dict(line.split(':', 1) for line in (entry/'status').read_text().splitlines()
                          if ':' in line)
            values[int(entry.name)] = (int(fields[1]), int(fields[19]),
                                      int(status.get('VmRSS', '0 kB').split()[0])*1024,
                                      int(status.get('VmHWM', '0 kB').split()[0])*1024)
        except (OSError, ValueError, IndexError):
            continue
    return values


def discover(table, owned):
    while True:
        added = {pid: row[1] for pid, row in table.items() if pid not in owned
                 and row[0] in owned and table.get(row[0], (None, None))[1] == owned[row[0]]}
        if not added:
            return
        owned.update(added)


def file_bytes(root):
    total = 0
    for path in root.rglob('*'):
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            pass  # Owned worker may remove an ephemeral attempt between samples.
    return total


def compatible_process_namespace():
    """Never signal proc-enumerated IDs from a different PID namespace."""
    try:
        return int(Path('/proc/self/stat').read_text().split(' ', 1)[0]) == os.getpid()
    except (OSError, ValueError):
        return False


def cleanup_jobs(root):
    """Actual ledger cancellation after workers stop, checking old completion fences."""
    from physimesh.platform.database import MetadataDB
    from physimesh.platform.jobs import Jobs, StaleAttempt

    result = {'accepted_jobs': 0, 'states_before_cleanup': {}, 'states_after_cleanup': {},
              'cancelled_unfinished': 0, 'stale_completion_checks': 0, 'cleanup_error': None}
    result['accepted_jobs_source'] = 'actual durable ledger rows, not HTTP response count'
    if not (root/'projects.sqlite').exists():
        return result
    database = MetadataDB(root/'projects.sqlite')
    try:
        jobs = Jobs(database)
        with database.connection() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM durable_jobs').fetchall()]
        result['accepted_jobs'] = len(rows)
        for row in rows:
            state = row['state']
            result['states_before_cleanup'][state] = result['states_before_cleanup'].get(state, 0)+1
            if state in ('queued', 'running'):
                jobs.cancel(row['project_id'], row['job_id'])
                result['cancelled_unfinished'] += 1
                if state == 'running':
                    try:
                        jobs.complete(row, {'synthetic': 'must not publish'})
                    except StaleAttempt:
                        result['stale_completion_checks'] += 1
                    else:
                        raise RuntimeError('stale completion unexpectedly accepted')
            after = jobs.get(row['project_id'], row['job_id'])['state']
            result['states_after_cleanup'][after] = result['states_after_cleanup'].get(after, 0)+1
    except Exception:  # noqa: BLE001 - no SQL/path/credential exception disclosure
        result['cleanup_error'] = 'ledger_cleanup_exception'
    finally:
        database.close()
    return result


def run(budgets):
    budgets.validate()
    if sys.platform != 'linux' or not Path('/proc').exists():
        raise ValueError('Linux proc monitoring is required')
    if not compatible_process_namespace():
        return {'schema_version': 1, 'budgets': asdict(budgets), 'stop_reason': 'incompatible_proc_pid_namespace',
                'completed_journeys': 0, 'requests': 0, 'failures': 0, 'cleanup_error': None,
                'child_exit_code': None, 'samples': [], 'processes_started': 0,
                'not_verified': ['bounded real worker journey and owned process-tree monitoring'],
                'qualification': 'Stopped before process creation; proc IDs cannot safely be signalled here'}
    started = time.monotonic()
    samples, reason, owned = [], None, {}
    report = {'requests': 0, 'completed_journeys': 0, 'failures': 0,
              'request_observations': [], 'stop_reason': 'child_no_progress'}
    with tempfile.TemporaryDirectory(prefix='physicore-bounded-soak-') as directory:
        root = Path(directory)
        env = {**{key: value for key, value in os.environ.items() if not key.startswith('PHYSIMESH_')},
               'PHYSIMESH_MODE': 'hosted', 'PHYSIMESH_DATA_ROOT': str(root),
               'PHYSIMESH_DB_PATH': str(root/'jobs.sqlite'), 'PYTHONPATH': str(ROOT/'src')}
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--child',
                                    str(root), '--config', json.dumps(asdict(budgets))],
                                   cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        table = processes()
        if process.pid in table:
            owned[process.pid] = table[process.pid][1]
        elif process.poll() is None:
            # Only the Popen handle is trustworthy if proc lookup fails. Do not
            # infer ownership from an empty tree or continue unmonitored work.
            process.kill()
            reason = 'owned_process_identity_unavailable'
        try:
            while process.poll() is None:
                table = processes()
                discover(table, owned)
                current = [row for pid, row in table.items() if owned.get(pid) == row[1]]
                storage = file_bytes(root)
                sample = {'elapsed_s': round(time.monotonic()-started, 3),
                          'owned_live_processes': len(current), 'rss_bytes': sum(r[2] for r in current),
                          'summed_live_process_hwm_bytes': sum(r[3] for r in current), 'file_bytes': storage}
                samples.append(sample)
                if sample['elapsed_s'] >= budgets.seconds:
                    reason = 'duration_budget'
                elif storage > budgets.storage_bytes:
                    reason = 'storage_observation_budget'
                elif sample['rss_bytes'] > budgets.memory_bytes:
                    reason = 'memory_observation_budget'
                if reason:
                    break
                time.sleep(min(.05, max(.001, budgets.seconds-(time.monotonic()-started))))
        except KeyboardInterrupt:
            reason = 'interrupted'
        except Exception:  # noqa: BLE001 - all owned-child error paths need cleanup
            reason = 'monitor_exception'
        finally:
            cleanup_started = time.monotonic()
            process_cleanup_error = None
            # Freeze the supervisor first so it cannot create new children while
            # discovering its last descendant tree, including new-session compute.
            table = processes()
            if owned.get(process.pid) == table.get(process.pid, (None, None))[1]:
                try:
                    os.kill(process.pid, signal.SIGSTOP)
                except ProcessLookupError:
                    pass
            table = processes()
            discover(table, owned)
            for pid, start_ticks in owned.items():
                if table.get(pid, (None, None))[1] == start_ticks:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # Reaping can lag behind the sampled SIGKILL. Keep the trusted
                # Popen fallback bounded, but always proceed to ledger fencing
                # and the receipt even if the process remains unresponsive.
                try:
                    process.kill()
                    process.wait(timeout=.5)
                except subprocess.TimeoutExpired:
                    process_cleanup_error = 'process_wait_timeout'
                except OSError:
                    process_cleanup_error = 'process_wait_error'
            except OSError:
                process_cleanup_error = 'process_wait_error'
            descendant_deadline = time.monotonic()+.5
            survivors = 0
            while time.monotonic() < descendant_deadline:
                remaining = processes()
                survivors = sum(owned.get(pid) == row[1] for pid, row in remaining.items())
                if not survivors:
                    break
                time.sleep(.01)
            try:
                report = json.loads((root/'progress.json').read_text())
            except (OSError, ValueError):
                pass
            report['stop_reason'] = reason or report['stop_reason']
            report['child_exit_code'] = process.returncode
            report['process_cleanup_error'] = process_cleanup_error
            report['owned_process_survivors_after_kill'] = survivors
            previous_handler = signal.getsignal(signal.SIGALRM)

            def cleanup_timeout(_signum, _frame):
                raise TimeoutError('bounded cleanup deadline')

            signal.signal(signal.SIGALRM, cleanup_timeout)
            signal.setitimer(signal.ITIMER_REAL, 5)
            try:
                report.update(cleanup_jobs(root))
            except Exception:  # noqa: BLE001 - sanitize deadline and database errors
                report['cleanup_error'] = 'ledger_cleanup_unavailable'
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)
            report['cleanup_elapsed_s'] = round(time.monotonic()-cleanup_started, 3)
    report.update(schema_version=1, fixture='analytic V4 synthetic hosted SQLite TestClient + real worker',
                  budgets=asdict(budgets), elapsed_s=round(time.monotonic()-started, 3), samples=samples,
                  processes_started=1,
                  disposable_directory_removed=not root.exists(),
                  qualification='Bounded local synthetic smoke; not 24-hour endurance, production SLO, or aircraft acceptance',
                  monitoring='50ms sampled owned child-tree RSS and file-byte stop thresholds, not hard quotas; '
                             'summed live process HWM is not simultaneous tree high-water memory',
                  process_wait_timeout_s=3, descendant_exit_observation_s=.5,
                  process_wait_retry_timeout_s=.5,
                  ledger_cleanup_deadline_s=5,
                  not_verified=['hosted network/provider', '24-hour soak', 'PostgreSQL', 'real aircraft sources',
                                'viewer access denial, session revocation and logout',
                                'sampling gaps and short-lived descendants', 'physical resource quotas'])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--requests', type=int, default=100)
    parser.add_argument('--journeys', type=int, default=2)
    parser.add_argument('--storage-bytes', type=int, default=64*1024**2)
    parser.add_argument('--memory-bytes', type=int, default=1024*1024**2)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--child', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--config', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.child:
        child(args.child, Budgets(**json.loads(args.config)))
        return 0
    if args.receipt is None or args.receipt.exists():
        parser.error('choose a new receipt path')
    budgets = Budgets(args.seconds, args.requests, args.journeys, args.storage_bytes, args.memory_bytes)
    try:
        budgets.validate()
    except ValueError:
        parser.error('invalid bounded smoke budgets')
    report = run(budgets)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: report[k] for k in ('stop_reason', 'completed_journeys', 'requests', 'failures')}))
    return 0 if (report['stop_reason'] == 'journey_budget' and not report['cleanup_error']
                 and not report.get('process_cleanup_error')
                 and report['completed_journeys'] == budgets.journeys
                 and report['child_exit_code'] == 0 and report['failures'] == 0
                 and report.get('owned_process_survivors_after_kill') == 0) else 1


if __name__ == '__main__':
    raise SystemExit(main())
