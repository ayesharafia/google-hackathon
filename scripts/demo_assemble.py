#!/usr/bin/env python3
"""Publish one immutable results package for the local API and export."""
import argparse
import hashlib
import json
from pathlib import Path

from physimesh.postpro.interpretation import interpret
from physimesh.postpro.refusals import sphere_refusals
from physimesh.postpro.result_contract import assemble_results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-group', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.run_group.parent
    group = json.loads(args.run_group.read_text())
    loads = json.loads((root/'load_results.json').read_text())
    if hashlib.sha256(args.run_group.read_bytes()).hexdigest() != loads['run_group_sha256']:
        raise ValueError('load result has stale run-group provenance')
    plots = json.loads((root/'plots/index.json').read_text())
    result = assemble_results(group, loads, plots, refusals=sphere_refusals())
    result['interpretation'] = interpret(result)
    package = args.data_root/'results'/result['run_group_id']
    package.mkdir(parents=True, exist_ok=True)
    files = {'results.json': (json.dumps(result, indent=2, allow_nan=False)+'\n').encode(),
             'run_group.json': args.run_group.read_bytes()}
    for record in plots:
        plot_id = record['recipe']['plot_id']
        png = (root/'plots'/f'{plot_id}.png').read_bytes()
        if hashlib.sha256(png).hexdigest() != record['png_sha256']:
            raise ValueError('plot hash differs from recipe record')
        files[f'plots/{plot_id}.png'] = png
        files[f'recipes/{plot_id}.json'] = (json.dumps(record, indent=2, allow_nan=False)+'\n').encode()
    files['hashes.json'] = (json.dumps({name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
                                     indent=2, sort_keys=True)+'\n').encode()
    for name, raw in files.items():
        target = package/name
        target.parent.mkdir(exist_ok=True, parents=True)
        if target.exists():
            if target.read_bytes() != raw:
                raise ValueError(f'published package is immutable: {name} differs')
        else:
            # Exclusive create prevents an existing package from being overwritten.
            with target.open('xb') as stream:
                stream.write(raw)
    print(package)


if __name__ == '__main__':
    main()
