import struct

import numpy as np
import pytest

# Unit cube, outward (counter-clockwise seen from outside) winding.
CUBE_V = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                   [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
CUBE_F = np.array([[0, 2, 1], [0, 3, 2],      # bottom  -z
                   [4, 5, 6], [4, 6, 7],      # top     +z
                   [0, 1, 5], [0, 5, 4],      # front   -y
                   [3, 7, 6], [3, 6, 2],      # back    +y
                   [0, 4, 7], [0, 7, 3],      # left    -x
                   [1, 2, 6], [1, 6, 5]])     # right   +x


@pytest.fixture
def cube_tris():
    return CUBE_V[CUBE_F].copy()


def binary_stl(tris, header=b"\0" * 80):
    header = header.ljust(80, b"\0")[:80]
    out = bytearray(header + struct.pack("<I", len(tris)))
    for t in tris:
        out += struct.pack("<3f", 0.0, 0.0, 0.0)
        for v in t:
            out += struct.pack("<3f", *v)
        out += struct.pack("<H", 0)
    return bytes(out)


def ascii_stl(tris, name="part"):
    lines = [f"solid {name}"]
    for t in tris:
        lines += ["  facet normal 0 0 0", "    outer loop"]
        lines += [f"      vertex {v[0]} {v[1]} {v[2]}" for v in t]
        lines += ["    endloop", "  endfacet"]
    lines.append(f"endsolid {name}")
    return "\n".join(lines).encode("ascii")
