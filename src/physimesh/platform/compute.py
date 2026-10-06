"""Isolated study/report subprocess. Produces attempt files, never publishes results."""
import ctypes
import json
import os
import resource
import signal
import sys
from pathlib import Path


def main():
    if not sys.platform.startswith('linux'):
        raise ValueError('isolated worker requires Linux process controls')
    # Killing the supervisor also kills its child, including the startup race.
    if ctypes.CDLL(None).prctl(1, signal.SIGKILL) != 0:
        raise ValueError('cannot establish supervisor-death fencing')
    if os.getppid() != int(os.environ['PHYSIMESH_SUPERVISOR_PID']):
        raise ValueError('supervisor exited before computation started')
    # Hard process limits supplement the worker's RSS/disk/wall monitoring.
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_AS, (2*1024**3, 2*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (5_000_000, 5_000_000))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    from physimesh.api.app import create_app
    from physimesh.api.settings import load_settings
    from physimesh.platform.scoped_artifacts import artifact_scope
    from physimesh.projects.reports import render_pdf, report_identity
    claim = json.loads(Path(sys.argv[1]).read_text())
    destination = Path(sys.argv[2])
    app = create_app(load_settings(os.environ))
    spec = claim['spec']
    if spec.get('application_build') != app.state.build.get('build_sha256'):
        raise ValueError('job application build differs from worker build')
    with artifact_scope(claim['project_id']):
        if claim['kind'] == 'study':
            if spec['model'] != app.state.studies.model_identity:
                raise ValueError('job model differs from worker build; resubmit under the intended release')
            result = app.state.studies.evaluate(claim['project_id'], spec['revision_sha256'])
            from physimesh.drone.provenance import canonical_json
            destination.write_text(canonical_json(result))
        else:
            raw, snapshot = app.state.studies.report_inputs(claim['project_id'], spec['study_sha256'])
            receipt = report_identity(raw, snapshot)
            if receipt != spec['report_identity']:
                raise ValueError('job renderer differs from worker build; resubmit under the intended release')
            pdf = render_pdf(raw, snapshot)
            destination.with_suffix('.pdf').write_bytes(pdf)
            destination.write_text(json.dumps(receipt, sort_keys=True))
    app.state.metadata.close()


if __name__ == '__main__':
    main()
