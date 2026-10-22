"""Reproduce a source-only documentation check; imports no application modules."""

import ast
import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '5477f94a0c467f1a01e9691a1f9c53613eeffa67'
DOCUMENT = ROOT / 'docs/validation/fixed-pack-energy-provenance.md'
OUTPUT = ROOT / '.physicore/evidence/DOC-002-static.json'
SOURCES = (
    'src/physimesh/drone/screening_scope.py',
    'src/physimesh/drone/authoring.py',
    'src/physimesh/drone/mass.py',
    'src/physimesh/drone/models.py',
    'src/physimesh/drone/schema/drone_manifest_v1.yaml',
    'src/physimesh/drone/trim.py',
    'src/physimesh/drone/mission_capacity.py',
    'src/physimesh/drone/local_results.py',
    'src/physimesh/drone/demo_screening.py',
    'src/physimesh/projects/contracts.py',
    'tests/drone/test_screening_scope.py',
    'tests/drone/test_hover_pilot.py',
    'docs/contracts/mission-capacity.md',
    'docs/contracts/production-data.md',
    'docs/decisions/ADR-0003-static-hover-profile.md',
    'docs/validation/local-hover-and-energy.md',
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, check=True).stdout


def main():
    text = DOCUMENT.read_text()
    sources = []
    for name in SOURCES:
        raw = (ROOT / name).read_bytes()
        if raw != git('show', f'{BASELINE}:{name}'):
            raise ValueError(f'Read source changed: {name}')
        sources.append({'path': name, 'sha256': sha(raw), 'unchanged_from_baseline': True})
    source = (ROOT / SOURCES[0]).read_text()
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'pack_consistency')
    # Row dispositions for the complete function, including its exact guards.
    spans = ((16, 17, 'E01'), (18, 25, 'E02'), (26, 26, 'E04/E05/E07'),
             (27, 31, 'E06'), (32, 36, 'E04/E05/E06/E07'),
             (37, 39, 'E08'), (40, 41, 'E10'), (42, 45, 'E09/E10'),
             (46, 48, 'E08/E10'))
    numerics, guards = [], []
    for n in sorted(ast.walk(function), key=lambda n: (getattr(n, 'lineno', 0), getattr(n, 'col_offset', 0))):
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            row = next((row for lo, hi, row in spans if lo <= n.lineno <= hi), None)
            if row is None or any(f'| {key} |' not in text for key in row.split('/')):
                raise ValueError(f'Numeric occurrence lacks ledger disposition: {n.lineno}')
            numerics.append({'line': n.lineno, 'source': ast.get_source_segment(source, n), 'rows': row})
        if isinstance(n, ast.If):
            guards.append({'line': n.lineno, 'condition': ast.get_source_segment(source, n.test)})
    links = []
    for target in re.findall(r'\]\(([^)]+)\)', text):
        if target.startswith(('https://', 'http://', '#')):
            continue
        name, _, fragment = target.partition('#')
        path = (DOCUMENT.parent / name).resolve()
        if path != OUTPUT and not path.is_file():
            raise ValueError(f'Missing local link: {target}')
        if fragment.startswith('L') and not 1 <= int(fragment[1:]) <= len(path.read_text().splitlines()):
            raise ValueError(f'Bad source line anchor: {target}')
        links.append(target)
    git('diff', '--check')
    protected = git('diff', BASELINE, '--name-only', '--', 'src', 'tests', 'web',
                    'validation', 'specs', 'pyproject.toml', '.github',
                    'requirements-runtime.lock', 'requirements-test.lock').decode().strip()
    if protected:
        raise ValueError(f'Protected source paths changed: {protected}')
    record = {
        'task': 'DOC-002', 'kind': 'static_documentation_check',
        'captured_at': dt.datetime.now(dt.UTC).isoformat(), 'baseline_head': BASELINE,
        'document_sha256': sha(DOCUMENT.read_bytes()), 'sources': sources,
        'function_numeric_occurrences': numerics, 'function_guards': guards,
        'local_links': links, 'protected_source_diff': [], 'whitespace_check': 'passed',
        'application_tests_or_model_runs_executed': False,
        'reproduce': '.venv/bin/python .physicore/evidence/DOC-002-static-check.py',
        'limitations': 'Only static source/hash/link checks. Guard meaning and documentation authored by one primary agent, not independently validated.',
    }
    OUTPUT.write_text(json.dumps(record, indent=2) + '\n')
    print(f'{len(sources)} unchanged sources; {len(numerics)} pack-function numeric occurrences assigned; '
          f'{len(guards)} conditional guards retained; {len(links)} local links resolve. No application/tests executed.')


if __name__ == '__main__':
    main()
