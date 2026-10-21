#!/usr/bin/env python3
"""Time native sphere load integration/reconciliation in fresh processes, without solving."""
import argparse
import json
import resource
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--case', type=Path)
    parser.add_argument('--time')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.case:
        from physimesh.postpro.results import sphere_load_result
        record = json.loads((args.case/'run_record.json').read_text())
        before = resource.getrusage(resource.RUSAGE_SELF)
        started = time.perf_counter()
        result = sphere_load_result(args.case, args.time, rho=1., speed=1., diameter=1.)
        wall = time.perf_counter()-started
        after = resource.getrusage(resource.RUSAGE_SELF)
        for name, digest in result['source_sha256'].items():
            if record['outputs'].get(name, {}).get('sha256') != digest:
                raise ValueError('native source changed since baseline execution')
        print(json.dumps({'wall_s': wall, 'cpu_s': after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                          'peak_process_rss_bytes': after.ru_maxrss*1024, 'loads': result}, allow_nan=False))
        return
    output = args.directory/'postprocessing-results.json'
    if output.exists():
        raise ValueError('postprocessing receipt already exists; select a new baseline directory')
    pipelines = json.loads((args.directory/'simulation-results.json').read_text())
    runs = []
    for level in ('coarse', 'medium'):
        case = next(r for r in pipelines['runs'] if r['level'] == level and r['repeat'] == 1)
        for repeat in range(1, args.repeats+1):
            response = subprocess.run([sys.executable, __file__, str(args.directory), '--case', case['case_dir'],
                                       '--time', case['metrics']['final_time']],
                                      capture_output=True, text=True, check=True, timeout=120)
            measured = json.loads(response.stdout)
            runs.append({'level': level, 'repeat': repeat, **measured})
            output.write_text(json.dumps({'runs': runs, 'method': 'fresh process; integration timing excludes imports; '
                'VmHWM includes imports; literal native sources verified against original run record; '
                'explicit registered sphere rho/speed/diameter = 1 SI'}, indent=2, allow_nan=False)+'\n')
            print(f"{level} postprocess r{repeat}: {measured['wall_s']:.3f} s, "
                  f"CPU {measured['cpu_s']:.3f} s, peak RSS {measured['peak_process_rss_bytes']/2**20:.1f} MiB", flush=True)


if __name__ == '__main__':
    main()
