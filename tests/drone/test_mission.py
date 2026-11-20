import math

import pytest

from physimesh.drone.mission import electrical_power, size_battery

G0 = 9.80665
RHO = 101325.0 / (287.05 * 288.15)

def test_electrical_power_eq46():
    p = electrical_power([1000.0, 1000.0], [0.9, 0.9], [0.95, 0.95], [1.0, 1.0], 100.0)
    assert p == pytest.approx(2000 / (0.9 * 0.95) + 100.0)


def _hover_pelec(m, a_tot=8 * math.pi * 1.5 ** 2, fm=0.7, eta=0.85, p_aux=2000.0):
    t = m * G0
    return t ** 1.5 / math.sqrt(2 * RHO * a_tot) / fm / eta + p_aux


@pytest.mark.parametrize("e_pack,minutes,status,mass", [
    (250.0, 10.0, "converged", 1442.1503),
    (200.0, 20.0, "converged", 3066.9058),
    (200.0, 60.0, "diverged", None),
])
def test_coupled_mass_energy_toy_cases(e_pack, minutes, status, mass):
    r = size_battery(1200.0, _hover_pelec, duration_s=minutes * 60, e_pack_wh_per_kg=e_pack,
                     f_usable=0.8, reserve_fraction=0.2, rel_tol=1e-6, max_iterations=500,
                     divergence_mass_kg=1e6)
    assert r.status == status
    if mass is not None:
        assert r.total_mass_kg == pytest.approx(mass, rel=1e-6)


def test_null_energy_density_blocks():
    with pytest.raises(ValueError):
        size_battery(1200.0, _hover_pelec, duration_s=600, e_pack_wh_per_kg=None, f_usable=0.8,
                     reserve_fraction=0.2, rel_tol=1e-6, max_iterations=10, divergence_mass_kg=1e6)


def test_bad_efficiency_lengths_and_invalid_power_model_are_refused():
    with pytest.raises(ValueError):
        electrical_power([1000, 1000], [.9], [.95, .95], [1, 1], 0)
    with pytest.raises(ValueError):
        size_battery(100, lambda _: float('nan'), duration_s=600, e_pack_wh_per_kg=250,
                     f_usable=.8, reserve_fraction=.2, rel_tol=1e-6,
                     max_iterations=10, divergence_mass_kg=1e6)
