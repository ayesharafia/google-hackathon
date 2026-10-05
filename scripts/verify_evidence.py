#!/usr/bin/env python3
"""Separate retained evidence from exact historical-source byte verification."""
import argparse
import json
from pathlib import Path

from physimesh.postpro.baseline import load_inventory
from physimesh.postpro.evidence_verification import verify_evidence, verify_source_commit

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scope', choices=['evidence', 'source-commit', 'both'])
    parser.add_argument('--inventory', type=Path, default=ROOT/'docs/qa/production-baseline.json')
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--native', action='store_true', help='Check retained native bytes; never run OpenFOAM')
    parser.add_argument('--vendor', action='store_true', help='Check retained vendor archive bytes')
    args = parser.parse_args(argv)
    if args.scope == 'source-commit' and (args.data_root or args.native or args.vendor):
        parser.error('evidence options require evidence or both scope')
    try:
        inventory = load_inventory(args.inventory)
        result = {}
        if args.scope in ('evidence', 'both'):
            result['evidence'] = verify_evidence(ROOT, inventory, data_root=args.data_root,
                                                 native=args.native, vendor=args.vendor)
        if args.scope in ('source-commit', 'both'):
            result['historical_source'] = verify_source_commit(ROOT, inventory)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, 'Verification refused: '+str(exc)+'\n')


if __name__ == '__main__':
    raise SystemExit(main())
