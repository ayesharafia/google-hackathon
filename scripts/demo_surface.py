#!/usr/bin/env python3
"""Triangulate native fine-sphere faces for display only; retain face-constant fields."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from physimesh.postpro.loads3d import to_physical_pressure, to_physical_stress
from physimesh.solver.foam_ascii import (
    face_centres_and_areas,
    read_boundary,
    read_faces,
    read_patch_field,
    read_points,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-group', type=Path, required=True)
    args = parser.parse_args()
    group = json.loads(args.run_group.read_text()); mesh = group['meshes'][-1]
    if mesh['level'] != 'fine' or mesh['state'] != 'completed':
        raise ValueError('completed fine sphere required')
    case = Path(mesh['case_dir']); record = json.loads((case/'run_record.json').read_text())
    if hashlib.sha256((case/'run_record.json').read_bytes()).hexdigest() != mesh['run_record_sha256']:
        raise ValueError('execution record changed')
    paths = ['constant/polyMesh/points', 'constant/polyMesh/faces', 'constant/polyMesh/boundary',
             'constant/polyMesh/owner', f"{mesh['final_time']}/p", f"{mesh['final_time']}/wallShearStress"]
    sources = {}
    for name in paths:
        digest = hashlib.sha256((case/name).read_bytes()).hexdigest()
        if record['outputs'][name]['sha256'] != digest:
            raise ValueError('native surface source has changed')
        sources[name] = digest
    points = read_points(case/'constant/polyMesh/points')
    patch = read_boundary(case/'constant/polyMesh/boundary')['sphere']
    faces = read_faces(case/'constant/polyMesh/faces')[patch['startFace']:patch['startFace']+patch['nFaces']]
    centres, _ = face_centres_and_areas(points, faces)
    p, dims = read_patch_field(case/mesh['final_time']/'p', 'sphere')
    stress, stress_dims = read_patch_field(case/mesh['final_time']/'wallShearStress', 'sphere')
    p = to_physical_pressure(p, dims, field_name='p', rho=group['rho_ref_kg_m3'])
    shear = np.linalg.norm(to_physical_stress(stress, stress_dims, rho=group['rho_ref_kg_m3']), axis=1)
    positions, pressures, shears = [], [], []
    for index, face in enumerate(faces):
        vertices = points[face]
        for k in range(len(vertices)):
            positions.extend([centres[index].tolist(), vertices[(k+1)%len(face)].tolist(), vertices[k].tolist()])
            pressures.extend([float(p[index])]*3); shears.extend([float(shear[index])]*3)
    surface = {'label': 'VERIFICATION CASE: native fine sphere; display triangulation only.',
               'positions': np.asarray(positions).ravel().tolist(), 'pressure_pa': pressures, 'wall_shear_pa': shears,
               'association': 'native boundary face; constant over display triangles', 'source_hashes': sources,
               'job_id': mesh['job_id'], 'final_iteration': mesh['final_time'], 'faces': len(faces),
               'pressure_range_pa': [float(p.min()), float(p.max())], 'shear_range_pa': [float(shear.min()), float(shear.max())]}
    path = args.run_group.parent/'surface.json'; path.write_text(json.dumps(surface, separators=(',', ':'), allow_nan=False))
    print(path, len(pressures)//3, 'display triangles')


if __name__ == '__main__':
    main()
