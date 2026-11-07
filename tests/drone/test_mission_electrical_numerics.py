import math
import struct
import sys
from decimal import Decimal, localcontext
from itertools import permutations

import pytest

from physimesh.drone.mission import electrical_power


@pytest.mark.parametrize("p,em,ei,ed", [
    (1e-300, 1e-200, 1e-200, 1.0),
    (1e-300, 1e-160, 1e-160, 1.0),
    (5e-324, 5e-324, 0.5, 0.5),
    (1e-320, 1e-10, 1e-150, 1e-160),
])
def test_rescued_products(p, em, ei, ed):
    assert em*ei*ed < sys.float_info.min
    references = []
    for precision in (90, 120):
        with localcontext() as ctx:
            ctx.prec = precision
            dp, dm, di, dd = map(Decimal.from_float, (p, em, ei, ed))
            references.append(float(dp / (dm * di * dd)))
    assert references[0].hex() == references[1].hex()
    actual = electrical_power([p], [em], [ei], [ed], 0.0)
    assert math.isfinite(actual) and actual > 0
    assert math.isclose(actual, references[0], rel_tol=1e-14, abs_tol=0.0)


@pytest.mark.parametrize("p", [0.0, -0.0])
@pytest.mark.parametrize("aux", [0.0, -0.0, 7.0, 1e-310])
def test_zero_preserves_auxiliary(p, aux):
    actual = electrical_power([p], [5e-324], [5e-324], [5e-324], aux)
    assert struct.pack("!d", actual) == struct.pack("!d", aux)


@pytest.mark.parametrize("bad", [0.0, -1.0, 1.01, math.inf, math.nan])
@pytest.mark.parametrize("slot", range(3))
def test_zero_still_validates_efficiencies(bad, slot):
    efficiencies = [[1e-200], [1e-200], [1.0]]
    efficiencies[slot] = [bad]
    with pytest.raises(ValueError, match="shaft power and efficiencies are invalid"):
        electrical_power([0.0], *efficiencies, 0.0)


@pytest.mark.parametrize("powers,em,ei,ed,aux", [
    ([1.0], [1e-200], [1e-200], [1.0], 0.0),
    ([1.0], [1e-160], [1e-160], [1.0], 0.0),
    ([sys.float_info.max], [0.5], [1.0], [1.0], 0.0),
    ([sys.float_info.max], [1.0], [1.0], [1.0], sys.float_info.max),
])
def test_overflow_is_value_error(powers, em, ei, ed, aux):
    with pytest.raises(ValueError, match="electrical power overflowed"):
        electrical_power(powers, em, ei, ed, aux)


@pytest.mark.parametrize("powers,etas,aux", [
    ([1e16, 1.0, 1.0], (1.0, 1.0, 1.0), 1.0),
    ([123.456, 1e-8, 987.654], (0.93, 0.97, 0.89), 7.25),
    ([1e-310], (1.0, 1.0, 1.0), 0.0),
])
def test_normal_product_byte_parity(powers, etas, aux):
    em, ei, ed = etas
    expected = aux
    for p in powers:
        expected += p/(em*ei*ed)
    actual = electrical_power(powers, *[[e]*len(powers) for e in etas], aux)
    assert struct.pack("!d", actual) == struct.pack("!d", expected)


@pytest.mark.parametrize("slot", range(4))
def test_strict_lengths_after_zero(slot):
    inputs = [[0.0], [1e-200], [1e-200], [1.0]]
    inputs[slot].append(inputs[slot][0])
    with pytest.raises(ValueError, match="zip"):
        electrical_power(*inputs, 0.0)


@pytest.mark.parametrize("aux", [math.inf, -math.inf, math.nan, -1.0])
def test_invalid_auxiliary(aux):
    with pytest.raises(ValueError, match="auxiliary power must be finite and nonnegative"):
        electrical_power([], [], [], [], aux)

def test_electrical_power_min_subnormal_efficiency_permutations():
    p = math.ulp(0.0)
    for efficiencies in (
        (0.9, 1e-200, 1e-200),
        (0.99, 1e-160, 1e-160),
        (1e-103, 1e-103, 1e-103),
    ):
        references = []
        for precision in (90, 120):
            with localcontext() as context:
                context.prec = precision
                denominator = (
                    Decimal.from_float(efficiencies[0])
                    * Decimal.from_float(efficiencies[1])
                    * Decimal.from_float(efficiencies[2])
                )
                references.append(float(Decimal.from_float(p) / denominator))
        assert references[0] == references[1]
        expected = references[1]
        for em, ei, ed in permutations(efficiencies):
            actual = electrical_power([p], [em], [ei], [ed], 0.0)
            assert math.isfinite(actual)
            assert math.isclose(actual, expected, rel_tol=1e-14, abs_tol=0.0)
