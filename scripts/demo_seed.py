#!/usr/bin/env python3
"""Seed labelled synthetic screening records and analytical battery fixtures."""
import argparse
import json
from pathlib import Path

import yaml

from physimesh.core.artifacts import ArtifactStore
from physimesh.drone.demo_screening import LABEL, example_battery_loops, example_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--write-doc-fixture', action='store_true')
    args = parser.parse_args()
    body = example_request(ArtifactStore(args.data_root/'artifacts'))
    record = {'label': LABEL, 'screening_request': body, 'battery_loops': example_battery_loops()}
    directory = args.data_root/'examples'; directory.mkdir(parents=True, exist_ok=True)
    (directory/'screening.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    if args.write_doc_fixture:
        target = Path(__file__).resolve().parents[1]/'docs/demo/example_multirotor.yaml'
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = yaml.safe_dump(record, sort_keys=False, width=1000).splitlines()
        target.write_text('# Illustrative example inputs, not client data.\n'+
                          '\n'.join(line+' # EXAMPLE VALUE - not client data' for line in lines)+'\n')
    print(directory/'screening.json')


if __name__ == '__main__':
    main()
