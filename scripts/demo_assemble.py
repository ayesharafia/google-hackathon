#!/usr/bin/env python3
"""Publish one immutable results package for the local API and export."""
import argparse
import hashlib
import json
from pathlib import Path

from physimesh.postpro.interpretation import interpret
from physimesh.postpro.publication import identity_bytes, publication_identity
from physimesh.postpro.refusals import sphere_refusals
from physimesh.postpro.result_contract import assemble_results
from physimesh.postpro.slice_eligibility import (
    LEGACY_POLICY_VERSION,
    registered_policy,
    registration_input,
    validate_native_reports,
)


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
    files = {'results.json': (json.dumps(result, indent=2, allow_nan=False)+'\n').encode(),
             'run_group.json': args.run_group.read_bytes()}
    eligibility_raw = (root/'slice_eligibility.json').read_bytes()
    eligibility = json.loads(eligibility_raw)
    policy_version = group.get('slice_policy', {}).get('policy_version', LEGACY_POLICY_VERSION)
    policy, policy_sha = registered_policy(policy_version)
    if 'slice_policy' in group and group['slice_policy'] != json.loads(registration_input(policy_version)):
        raise ValueError('run group slice policy differs from registered input')
    if set(eligibility) != {mesh['level'] for mesh in group['meshes']}:
        raise ValueError('slice eligibility must cover every mesh')
    for mesh in group['meshes']:
        validate_native_reports(mesh, eligibility[mesh['level']], rho=group['rho_ref_kg_m3'], diameter_m=group['D_m'])
        if 'slice_policy' in group and any(report['registration']['state'] != 'pre_execution_input'
                                          for report in eligibility[mesh['level']].values()):
            raise ValueError('run group cannot claim registration without retained job input')
    for level, fields in eligibility.items():
        for field, check in fields.items():
            if check['policy'] != policy or check['policy_sha256'] != policy_sha:
                raise ValueError('slice eligibility differs from the registered policy')
            if check['status'] == 'refused':
                result['limitations'].append(f'{level} {field} slice withheld: '+ '; '.join(check['reasons']))
    if any(report['registration']['state'] != 'pre_execution_input'
           for fields in eligibility.values() for report in fields.values()):
        result['limitations'].append('Slice eligibility is a retrospective replay of existing outputs under a fixed visual stability policy, not preregistration of the original CFD campaign.')
    files['slice_eligibility.json'] = eligibility_raw
    for record in plots:
        if record.get('run_group_sha256') != loads['run_group_sha256']:
            raise ValueError('plot belongs to a different run group')
        by_level = {mesh['level']: mesh for mesh in group['meshes']}
        run_id = record['recipe']['run_id']
        matching = [mesh for mesh in group['meshes'] if mesh['job_id'] == run_id]
        if matching:
            bindings = [(matching[0], record['source_hashes'])]
            if record['recipe']['plane'] is not None:
                level = matching[0]['level']
                field = {'pressure.static_gauge': 'pressure', 'vorticity.y': 'vorticity',
                         'velocity.magnitude': 'speed', 'velocity.in_plane': 'speed'}[record['recipe']['field_id']]
                check = eligibility[level][field]
                if check['status'] != 'eligible_visualization_only' or record.get('slice_eligibility') != eligibility[level]:
                    raise ValueError('unsupported or stale slice cannot be published')
        elif run_id == loads['run_group_sha256']:
            if set(record['source_hashes']) != set(by_level):
                raise ValueError('comparison plot mesh sources differ')
            bindings = [(by_level[level], sources) for level, sources in record['source_hashes'].items()]
        else:
            raise ValueError('plot run identifier differs from selected group')
        if matching:
            source_digest = hashlib.sha256(json.dumps(record['source_hashes'], sort_keys=True).encode()).hexdigest()
        else:
            per_level = {level: hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
                         for level, sources in record['source_hashes'].items()}
            source_digest = hashlib.sha256(json.dumps(per_level, sort_keys=True).encode()).hexdigest()
        if source_digest != record['recipe']['source_sha256']:
            raise ValueError('plot recipe aggregate source hash differs')
        for mesh, sources in bindings:
            raw = (Path(mesh['case_dir'])/'run_record.json').read_bytes()
            if hashlib.sha256(raw).hexdigest() != mesh['run_record_sha256']:
                raise ValueError('plot execution record changed')
            retained = json.loads(raw)
            if not sources or any(retained['outputs'].get(name, {}).get('sha256') != digest
                                  for name, digest in sources.items()):
                raise ValueError('plot native source hashes differ')
        plot_id = record['recipe']['plot_id']
        png = (root/'plots'/f'{plot_id}.png').read_bytes()
        if hashlib.sha256(png).hexdigest() != record['png_sha256']:
            raise ValueError('plot hash differs from recipe record')
        files[f'plots/{plot_id}.png'] = png
        files[f'recipes/{plot_id}.json'] = (json.dumps(record, indent=2, allow_nan=False)+'\n').encode()
    surface_path = root/'surface.json'
    if surface_path.exists():
        surface_raw = surface_path.read_bytes()
        surface = json.loads(surface_raw)
        fine = next(mesh for mesh in group['meshes'] if mesh['level'] == 'fine')
        if surface['job_id'] != fine['job_id'] or surface['final_iteration'] != fine['final_time']:
            raise ValueError('native surface belongs to another run')
        retained = json.loads((Path(fine['case_dir'])/'run_record.json').read_text())
        if any(retained['outputs'][name]['sha256'] != digest
               for name, digest in surface['source_hashes'].items()):
            raise ValueError('native surface source hashes differ from retained record')
        result['surfaces'] = [{key: surface[key] for key in ('label', 'association', 'job_id', 'final_iteration', 'faces', 'pressure_range_pa', 'shear_range_pa')} |
                              {'surface_id': 'fine_sphere', 'sha256': hashlib.sha256(surface_raw).hexdigest()}]
        files['surfaces/fine_sphere.json'] = surface_raw
        files['results.json'] = (json.dumps(result, indent=2, allow_nan=False)+'\n').encode()
    files['results.json'] = (json.dumps(result, indent=2, allow_nan=False)+'\n').encode()
    payload_hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    files['publication.json'] = identity_bytes(publication_identity(payload_hashes, loads['run_group_sha256']))
    files['hashes.json'] = (json.dumps({name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
                                     indent=2, sort_keys=True)+'\n').encode()
    # Check ALL existing members before writing anything. An archived package
    # cannot acquire new envelope files on a failed attempt to republish it.
    if package.exists():
        for name, raw in files.items():
            target = package/name
            if not target.is_file() or target.read_bytes() != raw:
                raise ValueError(f'published package is immutable: {name} differs')
        print(package)
        return
    package.mkdir(parents=True, exist_ok=False)
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
