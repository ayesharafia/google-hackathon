"""I01 registered exact-image sampling probe; preserves every historical source.

Use only a just-created 20-iteration sphere smoke case. A successful probe is
capability evidence, not an interpolation/physics acceptance or slice-policy update.
"""
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import numpy as np

from physimesh.core.container import docker_run_args
from physimesh.core.jobs import Budgets

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb'
source = max((ROOT/'.backend/sphere-smoke/runs').glob('*/run_record.json'), key=lambda p: p.stat().st_mtime).parent
record = json.loads((source/'run_record.json').read_text())
assert record['image_digest'] == IMAGE and '20/vorticity' in record['outputs']
for group in ['inputs', 'outputs']:
    for name, retained in record[group].items():
        digest = retained if isinstance(retained, str) else retained['sha256']
        assert hashlib.sha256((source/name).read_bytes()).hexdigest() == digest, name
assert sum(p.stat().st_size for p in source.rglob('*') if p.is_file()) < 1_000_000_000
case = ROOT/'.backend/investigations/i01'/uuid.uuid4().hex
shutil.copytree(source, case)
coordinates = [[.6+.5*i, 0., -.5+.25*j] for i in range(5) for j in range(5)]
dictionary = '''gridCapabilityProbe
{
    type sets;
    libs (sampling);
    writeControl writeTime;
    setFormat raw;
    interpolationScheme cellPoint;
    fields (p U vorticity);
    sets
    {
        labelled_grid
        {
            type cloud;
            axis xyz;
            points (
'''+''.join('                ('+' '.join(format(x,'.17g') for x in p)+')\n' for p in coordinates)+'''            );
        }
    }
}
'''
(case/'system/gridCapabilityProbe').write_text(dictionary)
inputs = {str(p.relative_to(case)): hashlib.sha256(p.read_bytes()).hexdigest()
          for folder in ['20', 'constant/polyMesh'] for p in (case/folder).rglob('*') if p.is_file()}
command = ['bash','-lc',"cd /case && postProcess -time 20 -fields '(p U vorticity)' -func gridCapabilityProbe"]
recipe = {'command':command, 'protocol':'native_declared_regular_grid_probe_v1', 'image':IMAGE,
          'source_case':str(source.relative_to(ROOT)), 'source_fields_and_mesh':inputs,
          'dictionary_sha256':hashlib.sha256(dictionary.encode()).hexdigest(),
          'coordinates':coordinates, 'coordinate_sha256':hashlib.sha256(json.dumps(coordinates).encode()).hexdigest(),
          'registration_commit':'1e58cd8', 'qualification':'20 iterations; no converged field or sampling-accuracy claim'}
(case/'probe_recipe.json').write_text(json.dumps(recipe, indent=2)+'\n')
started = time.perf_counter()
result = subprocess.run(docker_run_args(IMAGE, case, command, Budgets(2,4,1,120,512)), capture_output=True, text=True, timeout=120, check=False)
(case/'grid_probe.log').write_text(result.stdout+result.stderr)
assert result.returncode == 0, f'Probe refused; inspect {case}/grid_probe.log'
outputs = list((case/'postProcessing/gridCapabilityProbe/20').glob('*.xy'))
assert {p.name for p in outputs} in ({'labelled_grid_p_U.xy','labelled_grid_vorticity.xy'}, {'labelled_grid_p_U_vorticity.xy'}), 'Native sampler did not emit every requested field group'
records = []
for path in outputs:
    values = np.loadtxt(path, comments='#', ndmin=2)
    expected_columns = {'labelled_grid_p_U.xy':7, 'labelled_grid_vorticity.xy':6, 'labelled_grid_p_U_vorticity.xy':10}
    assert path.name in expected_columns and values.shape == (25,expected_columns[path.name]), (path, values.shape)
    assert np.isfinite(values).all()
    assert np.allclose(values[:,:3], coordinates, rtol=0, atol=1e-12)
    records.append({'path':str(path.relative_to(case)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'shape':list(values.shape), 'scalar_and_vector_column_min':values[:,3:].min(axis=0).tolist(),
                    'scalar_and_vector_column_max':values[:,3:].max(axis=0).tolist()})
assert sum(p.stat().st_size for p in case.rglob('*') if p.is_file()) < 1_000_000_000
receipt = {'status':'capability_only', 'recipe_sha256':hashlib.sha256((case/'probe_recipe.json').read_bytes()).hexdigest(),
           'wall_time_s':time.perf_counter()-started, 'outputs':records, 'runtime_evidence':str(case.relative_to(ROOT)),
           'log_sha256':hashlib.sha256((case/'grid_probe.log').read_bytes()).hexdigest(), 'recipe':recipe,
           'remaining':'Independent interpolation/direction/refinement validation; historical four slices remain refused.'}
(case/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
(ROOT/'docs/qa/native-grid-probe-2026-10-05.json').write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k != 'recipe'}, indent=2))
