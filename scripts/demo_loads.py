#!/usr/bin/env python3
"""Replay sphere native-load checks without rerunning or modifying solver cases."""
import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from physimesh.postpro import statistics
from physimesh.postpro.results import sphere_load_result
from physimesh.postpro.statistics import grid_convergence_unequal, order_capped_gci


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-group', type=Path, required=True)
    args = parser.parse_args()
    group_raw = args.run_group.read_bytes()
    group = json.loads(group_raw)
    runs = []
    if [mesh['level'] for mesh in group['meshes']] != ['coarse', 'medium', 'fine']:
        raise ValueError('three ordered sphere meshes required')
    speed = math.sqrt(sum(value**2 for value in group['u_inf_m_s']))
    for mesh in group['meshes']:
        if mesh['state'] != 'completed' or not mesh['checkmesh']['ok']:
            raise ValueError('completed, checkMesh-passing native evidence required')
        case = Path(mesh['case_dir'])
        record_raw = (case / 'run_record.json').read_bytes()
        if hashlib.sha256(record_raw).hexdigest() != mesh['run_record_sha256']:
            raise ValueError('retained execution record hash mismatch')
        result = sphere_load_result(case, mesh['final_time'], rho=group['rho_ref_kg_m3'],
                                    speed=speed, diameter=group['D_m'])
        record = json.loads(record_raw)
        for name, digest in result['source_sha256'].items():
            if record['outputs'].get(name, {}).get('sha256') != digest:
                raise ValueError(f'native evidence changed since execution: {name}')
        result.update(level=mesh['level'], cells=mesh['cells'], job_id=mesh['job_id'],
                      wall_time_s=mesh['wall_time_s'], peak_memory_bytes=mesh['peak_memory_bytes'],
                      checkmesh=mesh['checkmesh'], final_residuals=mesh['final_residuals'])
        runs.append(result)
        print(f"{mesh['level']}: Cd={result['cd']:.9f}; {result['reconciliation']['status']}", flush=True)
    r21 = (runs[2]['cells']/runs[1]['cells'])**(1/3)
    r32 = (runs[1]['cells']/runs[0]['cells'])**(1/3)
    estimate = asdict(grid_convergence_unequal(runs[2]['cd'], runs[1]['cd'], runs[0]['cd'], r21, r32))
    # JSON never emits NaN: unavailable estimates have an explicit null and reason.
    estimate = {key: None if isinstance(value, float) and not math.isfinite(value) else value
                for key, value in estimate.items()}
    estimate.update(r21=r21, r32=r32, basis='effective global h proportional to N^(-1/3)',
                    qualification='fixed surface refinement levels; not proven asymptotic or total uncertainty')
    # [review F1] Nominal second-order cap from the retained sphere fvSchemes;
    # local limiters and fixed surface levels do not establish that actual order.
    nominal_order_cap, safety_factor = 2., 1.25  # ASME three-grid Eq 7 safety factor
    estimate.update(nominal_order_cap=nominal_order_cap, gci_safety_factor=safety_factor,
                    nominal_order_cap_source='retained sphere fvSchemes; independent review F1',
                    gci_order_used=None, order_capped_gci_fine=None,
                    estimator_code_sha256=hashlib.sha256(Path(statistics.__file__).read_bytes()).hexdigest())
    if estimate['behaviour'] == 'monotonic':
        estimate['gci_order_used'] = min(estimate['observed_order'], nominal_order_cap)
        estimate['order_capped_gci_fine'] = order_capped_gci(
            runs[2]['cd'], runs[1]['cd'], r21, estimate['observed_order'], nominal_order_cap, safety_factor)
    result = {'label': group['label'], 'evidence': 'unverified', 'runs': runs,
              'mesh_study': estimate, 'run_group_sha256': hashlib.sha256(group_raw).hexdigest()}
    output = args.run_group.parent / 'load_results.json'
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(estimate, indent=2))


if __name__ == '__main__':
    main()
