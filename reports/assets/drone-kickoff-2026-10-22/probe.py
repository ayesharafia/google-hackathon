"""Diagnostic plot of an existing synthetic fixture, without new acceptance gates.

Run from the repository root with the project Python interpreter. This reuses
only the existing test's input constructor, never its expected-answer functions.
The closed-form comparator is calculated with decimal arithmetic and explicit
fixture values. No physical or numerical acceptance tolerance is introduced.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import platform
import subprocess
from decimal import Decimal, getcontext
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import scipy

from physimesh.drone.capacity import capacity_from_snapshot


def main():
    getcontext().prec = 28
    root = Path(__file__).resolve().parents[3]
    output = Path(__file__).resolve().parent
    fixture_path = root/'tests/drone/test_hover_pilot.py'
    specification = importlib.util.spec_from_file_location('retained_hover_fixture', fixture_path)
    fixture_module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(fixture_module)
    baseline, _, sources = fixture_module.fixture()
    # Artificial fixture declarations, not client aircraft measurements.
    gravity = Decimal('9.80665')
    empty_mass = Decimal(12)
    thrust_ceiling = Decimal(400)
    usable_energy = Decimal(460800)
    power_per_thrust = Decimal(10)
    durations = [10, 60, 90, 115.2, 120, 150, 180, 210, 240, 270, 300, 330, 360, 390, 400]
    rows = []
    for duration in durations:
        snapshot = copy.deepcopy(baseline)
        snapshot['mission']['cases'][0]['duration_s'] = duration
        observed = capacity_from_snapshot(snapshot, sources)
        required_thrust_limit = min(thrust_ceiling, usable_energy/(power_per_thrust*Decimal(str(duration))))
        expected = required_thrust_limit/gravity-empty_mass
        if expected < 0:
            reference_payload = None
            reference_state = 'no nonnegative payload in this fixture'
        else:
            reference_payload = float(expected)
            reference_state = 'feasible under the artificial fixture assumptions'
        actual = observed.get('payload_lower_bound_kg')
        candidates = [record['candidate'] for record in observed.get('headline_candidate_checks', [])
                      if record.get('outcome') == 'feasible']
        if not candidates:
            candidates = [record['candidate'] for record in observed.get('cases', [])
                          if record.get('outcome') == 'feasible']
        rows.append({
            'duration_s': duration,
            'closed_form_payload_kg': reference_payload,
            'closed_form_state': reference_state,
            'solver_outcome': observed['outcome'],
            'solver_payload_kg': actual,
            'absolute_payload_difference_kg': (abs(actual-reference_payload)
                if actual is not None and reference_payload is not None else None),
            'max_force_residual_n': (max(abs(v) for c in candidates for v in c['force_residual_n'])
                                     if candidates else None),
            'max_moment_residual_nm': (max(abs(v) for c in candidates for v in c['moment_residual_cg_nm'])
                                      if candidates else None),
            'reasons': observed.get('reasons', []),
        })
    with (output/'hover-duration.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, 'reasons': json.dumps(row['reasons'])})
    comparable = [row for row in rows if row['absolute_payload_difference_kg'] is not None]
    observed_counts = {state: sum(row['solver_outcome'] == state for row in rows)
                       for state in sorted({row['solver_outcome'] for row in rows})}
    tracked_paths = [
        'tests/drone/test_hover_pilot.py', 'tests/projects/fixtures/incomplete_draft.json',
        'src/physimesh/drone/capacity.py', 'src/physimesh/drone/trim.py',
        'src/physimesh/drone/mission_capacity.py', 'src/physimesh/drone/performance.py',
        'src/physimesh/drone/authoring.py', 'src/physimesh/drone/atmosphere.py',
        'src/physimesh/projects/performance.py',
    ]
    summary = {
        'kind': 'existing_synthetic_fixture_diagnostic',
        'qualification': 'Not a scientist-approved validation campaign or aircraft accuracy claim.',
        'tested_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'runtime': {'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__,
                    'matplotlib': matplotlib.__version__},
        'command': 'MPLCONFIGDIR=.backend/drone-kickoff-2026-10-22/matplotlib .venv/bin/python '
                   'reports/assets/drone-kickoff-2026-10-22/probe.py',
        'comparison': 'm_payload=min(400 N,460800 J/(10 W/N * duration_s))/9.80665 m/s^2 - 12 kg',
        'reference_arithmetic': 'Decimal precision 28, then rounded to float for comparison and plotting',
        'sources': {path: hashlib.sha256((root/path).read_bytes()).hexdigest() for path in tracked_paths},
        'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'new_acceptance_tolerance': None,
        'observation_count': len(rows), 'outcomes': observed_counts,
        'max_absolute_payload_difference_kg': max(row['absolute_payload_difference_kg'] for row in comparable),
        'max_force_residual_n': max(row['max_force_residual_n'] for row in comparable),
        'max_moment_residual_nm': max(row['max_moment_residual_nm'] for row in comparable),
        'observations': rows,
    }
    (output/'hover-duration.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    fig, (axis, errors) = plt.subplots(2, 1, figsize=(9, 6), sharex=True,
                                      gridspec_kw={'height_ratios': [3, 1]}, layout='constrained')
    reference_rows = [row for row in rows if row['closed_form_payload_kg'] is not None]
    axis.plot([r['duration_s'] for r in reference_rows],
              [r['closed_form_payload_kg'] for r in reference_rows], color='#244936',
              label='Closed-form synthetic reference')
    axis.scatter([r['duration_s'] for r in comparable], [r['solver_payload_kg'] for r in comparable],
                 marker='x', color='#2649a0', label='Existing solver')
    axis.set_ylabel('Payload bound (kg)')
    axis.set_title('Synthetic hover fixture: solver versus closed-form reference\n'
                   'Diagnostic only; no measured aircraft performance')
    axis.legend(frameon=False)
    errors.plot([r['duration_s'] for r in comparable],
                [r['absolute_payload_difference_kg'] for r in comparable], color='#2649a0', marker='.')
    errors.set_ylabel('Difference (kg)')
    errors.set_xlabel('Declared constant hover duration (s)')
    errors.ticklabel_format(axis='y', style='sci', scilimits=(0, 0))
    for row in rows:
        if row['solver_payload_kg'] is None:
            axis.annotate(row['solver_outcome'], (row['duration_s'], 0), xytext=(-3, 18),
                          textcoords='offset points', ha='right', fontsize=9)
    fig.savefig(output/'hover-duration.png', dpi=180)
    plt.close(fig)
    print(json.dumps({key: summary[key] for key in ('observation_count', 'outcomes',
        'max_absolute_payload_difference_kg', 'max_force_residual_n', 'max_moment_residual_nm')}))


if __name__ == '__main__':
    main()
