#!/usr/bin/env python3
"""Build an offline, hash-verified Linux/CPython 3.11 runtime wheelhouse."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
destination = root/'dist/wheelhouse'
destination.mkdir(parents=True, exist_ok=True)
command = [sys.executable, '-m', 'pip', 'download', '--require-hashes', '--only-binary=:all:',
           '--python-version', '3.11', '--implementation', 'cp', '--abi', 'cp311', '--abi', 'abi3',
           '--abi', 'none', '--dest', str(destination), '-r', str(root/'requirements-runtime.lock')]
for platform in ('manylinux_2_34_x86_64', 'manylinux_2_28_x86_64', 'manylinux_2_27_x86_64',
                 'manylinux_2_17_x86_64', 'manylinux2014_x86_64'):
    command.extend(('--platform', platform))
result = subprocess.run(command, capture_output=True, text=True, check=False)
if result.returncode:
    raise RuntimeError('hash-verified runtime wheel download failed; no image was built')
print(f'Verified offline runtime wheelhouse: {len(list(destination.glob("*.whl")))} wheels.')
