"""Bounded route-template metrics; no project IDs, tokens or emails become labels."""
import os
import threading
import time
from collections import defaultdict
from pathlib import Path


class Metrics:
    buckets = (.005, .01, .025, .05, .1, .25, .5, 1, 2, 5, 10, 30)

    def __init__(self):
        self.started = time.time()
        self.lock = threading.Lock()
        self.rows = defaultdict(lambda: [0, 0., [0]*len(self.buckets)])

    def record(self, method, route, status, elapsed):
        method = method if method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS') else 'OTHER'
        with self.lock:
            row = self.rows[(method, route, status)]
            row[0] += 1
            row[1] += elapsed
            for n, upper in enumerate(self.buckets):
                row[2][n] += elapsed <= upper

    def render(self):
        lines = ['# HELP physimesh_handler_seconds Time to response headers; full-body latency is measured by load clients.',
                 '# TYPE physimesh_handler_seconds histogram']
        with self.lock:
            for (method, route, status), (count, total, buckets) in sorted(self.rows.items()):
                labels = f'method="{method}",route="{route}",status="{status}"'
                for upper, value in zip(self.buckets, buckets, strict=True):
                    lines.append(f'physimesh_handler_seconds_bucket{{{labels},le="{upper}"}} {value}')
                lines.extend([f'physimesh_handler_seconds_bucket{{{labels},le="+Inf"}} {count}',
                              f'physimesh_handler_seconds_count{{{labels}}} {count}',
                              f'physimesh_handler_seconds_sum{{{labels}}} {total}'])
        status_file = Path(f'/proc/{os.getpid()}/status')
        if status_file.exists():
            status = status_file.read_text()
            for field, metric in (('VmRSS:', 'rss'), ('VmHWM:', 'peak_rss')):
                value = int(next(line.split()[1] for line in status.splitlines() if line.startswith(field)))*1024
                lines.append(f'physimesh_process_{metric}_bytes {value}')
        cpu = time.process_time()
        lines.extend([f'physimesh_process_cpu_seconds_total {cpu}', f'physimesh_process_start_time_seconds {self.started}'])
        return '\n'.join(lines)+'\n'
