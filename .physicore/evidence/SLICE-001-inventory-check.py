"""Reproduce SLICE-001's static documentation/source inventory; runs no model/tests."""

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '5477f94a0c467f1a01e9691a1f9c53613eeffa67'
LEDGER = ROOT / 'docs/validation/drone-constants-ledger.md'
# Inclusive source-line spans manually reviewed against the ledger rows.
SPANS = {
    'atmosphere': {
        'A01': (9, 9), 'A02': (10, 10), 'A03': (11, 14),
        'A04': (17, 18), 'A05': (20, 20), 'A06': (50, 50),
        'A07': (52, 68), 'A08': (71, 80), 'A09': (83, 91),
        'A10': (94, 107),
    },
    'performance': {
        'P01': (13, 14), 'P02': (29, 29), 'P01-efficiency': (37, 37),
        'P02-counts': (39, 40), 'P03': (53, 53),
        'P04': (54, 57), 'P05': (58, 80), 'P07': (83, 90),
        'P04-query': (91, 92), 'P06': (98, 120),
        'P07-coefficients': (121, 124),
    },
    'trim': {
        'T01': (21, 23), 'T02': (26, 38), 'T03-default': (62, 62),
        'T03': (69, 113), 'T04': (114, 141), 'T05': (143, 155),
        'T06': (158, 165), 'T07': (169, 174), 'T08': (175, 193),
        'T09': (195, 204), 'T10': (212, 239), 'T11': (242, 296),
        'T12': (299, 315), 'T13': (316, 325), 'T14': (328, 356),
        'T15': (359, 391), 'T16': (392, 405), 'T17': (407, 413),
        'T18': (417, 430),
    },
    'capacity': {'C01': (21, 85), 'C02': (86, 164)},
    'mission_capacity': {
        'S01': (24, 76), 'S02': (79, 104), 'S03': (107, 124),
        'S04': (125, 139), 'S05': (140, 149),
    },
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    text = LEDGER.read_text()
    files = []
    total = 0
    structural = 0
    for name, spans in SPANS.items():
        path = ROOT / f'src/physimesh/drone/{name}.py'
        raw = path.read_bytes()
        rel = str(path.relative_to(ROOT))
        original = subprocess.run(
            ['git', 'show', f'{BASELINE}:{rel}'], cwd=ROOT,
            capture_output=True, check=True,
        ).stdout
        if raw != original:
            raise ValueError(f'Source changed from task baseline: {rel}')
        source = raw.decode()
        tree = ast.parse(source)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        occurrences = []
        for node in sorted(ast.walk(tree), key=lambda n: (getattr(n, 'lineno', 0), getattr(n, 'col_offset', 0))):
            if not isinstance(node, ast.Constant) or type(node.value) not in (int, float):
                continue
            matches = [key.split('-')[0] for key, (lo, hi) in spans.items() if lo <= node.lineno <= hi]
            if len(matches) != 1 or f'| {matches[0]} |' not in text:
                raise ValueError(f'Undisposed numeric literal: {rel}:{node.lineno}')
            parent = parents.get(node)
            expression = parent if isinstance(parent, ast.UnaryOp) else node
            # Literal array indices/slice bounds are structure; containing policy
            # row still provides context. Other coefficients retain their row ID.
            ancestor = expression
            while ancestor in parents and isinstance(parents[ancestor], (ast.Tuple, ast.Slice)):
                ancestor = parents[ancestor]
            is_index = isinstance(parents.get(ancestor), ast.Subscript) and parents[ancestor].slice is ancestor
            structural += int(is_index)
            occurrences.append({
                'line': node.lineno, 'column_0_based': node.col_offset,
                'source_expression': ast.get_source_segment(source, expression),
                'ledger_row': matches[0],
                'disposition': 'STRUCTURE: index/slice' if is_index else 'See ledger row: parameter, guard or algebraic/structural coefficient',
            })
        total += len(occurrences)
        files.append({'path': rel, 'sha256': digest(raw), 'unchanged_from_baseline': True,
                      'numeric_occurrences': occurrences})
    link_count = 0
    for target in re.findall(r'\]\(([^)]+)\)', text):
        if target.startswith(('https://', 'http://', '#')):
            continue
        filename, _, fragment = target.partition('#')
        path = (LEDGER.parent / filename).resolve()
        if not path.is_file():
            raise ValueError(f'Missing local link: {target}')
        if fragment.startswith('L') and not 1 <= int(fragment[1:]) <= len(path.read_text().splitlines()):
            raise ValueError(f'Invalid line anchor: {target}')
        link_count += 1
    record = {
        'kind': 'static_documentation_inventory', 'task_id': 'SLICE-001',
        'baseline_head': BASELINE, 'source_modules': len(files),
        'numeric_occurrences': total, 'index_or_slice_occurrences': structural,
        'undisposed_occurrences': 0, 'local_links_checked': link_count,
        'ledger_sha256': digest(LEDGER.read_bytes()),
        'reproduce': '.venv/bin/python .physicore/evidence/SLICE-001-inventory-check.py',
        'application_or_physics_tests_executed': False,
        'limits': 'Static source/link/hash checks only. Row classifications and nonnumeric guard coverage were authored by the primary agent, not independently validated.',
        'files': files,
    }
    dest = ROOT / '.physicore/evidence/SLICE-001-inventory.json'
    dest.write_text(json.dumps(record, indent=2) + '\n')
    print(f'5 unchanged modules; {total} numeric occurrences assigned; {link_count} local links valid; no model/tests executed')


if __name__ == '__main__':
    main()
