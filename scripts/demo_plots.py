#!/usr/bin/env python3
"""Render the verification gallery from retained native sphere outputs."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from physimesh.postpro.plots import render
from physimesh.postpro.recipes import PlotRecipe
from physimesh.postpro.results import _columns
from physimesh.postpro.slice_eligibility import evaluate_slice, registration_for_run
from physimesh.solver.foam_ascii import read_function_object_table, read_raw_samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-group', type=Path, required=True)
    args = parser.parse_args()
    group = json.loads(args.run_group.read_text())
    if group['Re'] != 100 or group['D_m'] != 1 or group['u_inf_m_s'] != [1., 0., 0.]:
        raise ValueError('demo plot profile metadata requires the recorded D=1, Re=100, +x sphere case')
    load_results = json.loads((args.run_group.parent/'load_results.json').read_text())
    if load_results['run_group_sha256'] != hashlib.sha256(args.run_group.read_bytes()).hexdigest():
        raise ValueError('load result belongs to a different run group')
    out = args.run_group.parent/'plots'; out.mkdir(exist_ok=True)
    records, native, shared = [], {}, {}
    for mesh in group['meshes']:
        case = Path(mesh['case_dir']); time = mesh['final_time']; level = mesh['level']
        run_record = json.loads((case/'run_record.json').read_text())
        if hashlib.sha256((case/'run_record.json').read_bytes()).hexdigest() != mesh['run_record_sha256']:
            raise ValueError('execution record changed')
        hashes = {}

        def verified(path, case=case, run_record=run_record, hashes=hashes):
            raw = path.read_bytes(); name = str(path.relative_to(case))
            digest = hashlib.sha256(raw).hexdigest()
            if run_record['outputs'].get(name, {}).get('sha256') != digest:
                raise ValueError(f'native plot evidence changed: {name}')
            hashes[name] = digest
            return path

        plane = case/'postProcessing/cuttingPlane'/time
        arrays = {}
        for field, filename in [('u', 'U_yNormal.raw'), ('p', 'p_yNormal.raw'), ('omega', 'vorticity_yNormal.raw')]:
            _, arrays[field] = read_raw_samples(verified(plane/filename))
        # Metadata is retained from the actual raw headers and generator sampling dictionaries.
        if not np.array_equal(arrays['u'][:, :3], arrays['p'][:, :3]) or not np.array_equal(arrays['u'][:, :3], arrays['omega'][:, :3]):
            raise ValueError('plane sample locations differ; no implicit association permitted')
        grids, eligibility = {}, {}
        for field, samples, values in (
            ('speed', arrays['u'][:, :3], arrays['u'][:, 3:6]),
            ('pressure', arrays['p'][:, :3], arrays['p'][:, 3]*group['rho_ref_kg_m3']),
            ('vorticity', arrays['omega'][:, :3], arrays['omega'][:, 4]),
        ):
            grids[field], eligibility[field] = evaluate_slice(samples, values, diameter_m=group['D_m'])
            filename = {'speed': 'U_yNormal.raw', 'pressure': 'p_yNormal.raw', 'vorticity': 'vorticity_yNormal.raw'}[field]
            name = str((plane/filename).relative_to(case))
            eligibility[field]['source_sha256'] = {name: hashes[name]}
            eligibility[field]['registration'] = registration_for_run(case, run_record)
        profile_path = verified(case/'postProcessing/sample1'/time/'centreLine_p_U.xy')
        _, profile = read_raw_samples(profile_path)
        if profile.shape[1] != 5:
            raise ValueError('recorded wake sample is x,p,Ux,Uy,Uz')
        coefficient = _columns(verified(case/'postProcessing/forceCoeffs1/0/coefficient.dat'))
        headers, residual_rows = read_function_object_table(verified(case/'postProcessing/solverInfo1/0/solverInfo.dat'))
        residuals = {name: np.asarray(residual_rows[:, headers.index(name)], float)
                     for name in ('Time', 'p_initial', 'Ux_initial', 'Uy_initial', 'Uz_initial')}
        native[level] = {'grids': grids, 'slice_eligibility': eligibility, 'profile': profile, 'coefficient': coefficient, 'residuals': residuals,
                             'source_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
                             'sources': hashes, 'job_id': mesh['job_id'], 'iteration': time, 'maximum_abs_sample_y_m': float(np.abs(arrays['u'][:, 1]).max())}
    for name in ('speed', 'pressure', 'vorticity'):
        candidates = [entry['grids'][name]['values'][~entry['grids'][name]['mask']].ravel()
                      for entry in native.values() if entry['grids'][name] is not None]
        if not candidates:
            continue
        vals = np.concatenate(candidates)
        vals = vals[np.isfinite(vals)]
        if name == 'speed':
            shared[name] = (0., float(vals.max()))
        else:
            extent = float(np.abs(vals).max()); shared[name] = (-extent, extent)

    def emit(plot_id, field_id, kind, level, data, limits, plane=None, note=''):
        entry = native.get(level, None)
        source = entry['source_sha256'] if entry else hashlib.sha256(json.dumps(
            {k: v['source_sha256'] for k, v in native.items()}, sort_keys=True).encode()).hexdigest()
        run_id = entry['job_id'] if entry else load_results['run_group_sha256']
        iteration = entry['iteration'] if entry else ', '.join(f"{key}={value['iteration']}" for key, value in native.items())
        caption = (f'VERIFICATION CASE: sphere Re=100; world frame; final steady iteration(s) {iteration}. '
                   'Native outputs; visual slice interpolation only; nominal y=0 with native |y| deviation below 1e-5 D; no aircraft result. '+note)
        recipe = PlotRecipe(plot_id, field_id, kind, run_id, source, plane,
                            {'pressure.static_gauge': 'Pa', 'vorticity.y': '1/s',
                             'velocity.magnitude': 'm/s', 'velocity.in_plane': 'm/s',
                             'profile.wake_axis_ux': 'm/s'}.get(field_id, 'dimensionless'),
                            'RdBu_r' if kind == 'contour' and field_id in ('pressure.static_gauge', 'vorticity.y') else 'viridis',
                            'shared_global', *limits, 'sphere interior and nonfinite; grey', caption)
        png, record = render(recipe, data)
        (out/f'{plot_id}.png').write_bytes(png)
        record['run_group_sha256'] = load_results['run_group_sha256']
        record['png_sha256'] = hashlib.sha256(png).hexdigest()
        record['maximum_abs_sample_y_m'] = entry['maximum_abs_sample_y_m'] if entry else None
        record['slice_eligibility'] = entry['slice_eligibility'] if entry and plane else None
        record['source_hashes'] = entry['sources'] if entry else {k: v['sources'] for k, v in native.items()}
        (out/f'{plot_id}.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
        records.append(record); print(plot_id, flush=True)

    for level, entry in native.items():
        for name, field in [('speed', 'velocity.magnitude'), ('pressure', 'pressure.static_gauge'), ('vorticity', 'vorticity.y')]:
            if entry['grids'][name] is None:
                continue
            emit(f'{level}_{name}', field, 'contour', level, entry['grids'][name], shared[name],
                 plane={'axis': 'y', 'position_m': 0, 'view_bounds_m': [-1.5, 4, -1.5, 1.5]},
                 note='y=0 slice. Bounds shared only across eligible views: '+', '.join(k for k, v in native.items() if v['grids'][name] is not None)+'.')
    for kind in ('vectors', 'streamlines') if native['fine']['grids']['speed'] is not None else ():
        emit(f'fine_{kind}', 'velocity.in_plane', kind, 'fine', native['fine']['grids']['speed'], shared['speed'],
             plane={'axis': 'y', 'position_m': 0},
             note='In-plane '+kind+' of the y=0 slice velocity; background |U|. These are not 3D particle paths.')
    levels = ['coarse', 'medium', 'fine']
    x = native['fine']['profile'][:, 0]
    if any(not np.array_equal(native[level]['profile'][:, 0], x) for level in levels):
        raise ValueError('wake sample axes differ; comparisons require explicit alignment')
    wake = np.vstack([native[level]['profile'][:, 2] for level in levels])
    emit('wake_axis', 'profile.wake_axis_ux', 'xy', 'all',
         {'x': x, 'values': wake, 'labels': levels, 'x_label': 'world x / D (D=1 m)'}, (float(wake.min()), float(wake.max())),
         note='Native centreLine x,p,Ux,Uy,Uz columns; y=z=0.')
    t = native['fine']['coefficient']['Time']
    if any(not np.array_equal(native[level]['coefficient']['Time'], t) for level in levels):
        raise ValueError('iteration axes differ; comparisons require explicit alignment')
    cds = np.vstack([native[level]['coefficient']['Cd'] for level in levels])
    emit('cd_history', 'load.cd_history', 'xy', 'all', {'x': t, 'values': cds, 'labels': levels, 'x_label': 'steady iteration'},
         (float(cds.min()), float(cds.max())), note='Steady iteration history, not physical time.')
    res = native['fine']['residuals']; labels = ['p_initial', 'Ux_initial', 'Uy_initial', 'Uz_initial']
    values = np.vstack([res[key] for key in labels]); mask = values <= 0
    emit('fine_residuals', 'residuals.history', 'xy', 'fine',
         {'x': res['Time'], 'values': values, 'mask': mask, 'labels': labels, 'log_y': True, 'x_label': 'steady iteration'},
         (float(values[~mask].min()), float(values.max())), note='Initial residuals; zero/unavailable values masked.')
    cd_values = np.array([r['cd'] for r in load_results['runs']])
    gci = load_results['mesh_study'].get('order_capped_gci_fine')
    emit('mesh_cd', 'mesh_study.cd_by_level', 'bar', 'all',
         {'values': cd_values, 'labels': levels, 'reference': 1.09173, 'gci_absolute': None if gci is None else gci*cd_values[-1]},
         (0., float(cd_values.max()*1.1)), note='Error bar uses order-capped GCI (nominal cap 2, safety factor 1.25); qualified mesh sensitivity, not total uncertainty or a proven error bound.')
    (out/'index.json').write_text(json.dumps(records, indent=2, allow_nan=False)+'\n')
    eligibility_path = args.run_group.parent/'slice_eligibility.json'
    eligibility_path.write_text(json.dumps({level: entry['slice_eligibility'] for level, entry in native.items()}, indent=2, allow_nan=False)+'\n')
    observations = {level: {'wake_ux_min': float(entry['profile'][:, 2].min()),
                            'slice_p_min': (float(entry['grids']['pressure']['values'][~entry['grids']['pressure']['mask']].min()) if entry['grids']['pressure'] is not None else None)}
                    for level, entry in native.items()}
    (out/'observations.json').write_text(json.dumps(observations, indent=2)+'\n')


if __name__ == '__main__':
    main()
