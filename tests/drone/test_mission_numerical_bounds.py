import sys

import pytest

from physimesh.drone import mission

MIN = sys.float_info.min
MAX = sys.float_info.max


def run_size(p=1.0, calls=None, **changes):
    options = {
        "mass_without_battery_kg": 0.0,
        "duration_s": 1.0,
        "e_pack_wh_per_kg": 1.0,
        "f_usable": 1.0,
        "reserve_fraction": 0.0,
        "rel_tol": 1e-12,
        "max_iterations": 10,
        "divergence_mass_kg": MAX,
    }
    options.update(changes)

    def power(mass):
        if calls is not None:
            calls.append(mass)
        return p(mass) if callable(p) else p

    return mission.size_battery(p_elec_of_mass=power, **options)


def test_constant_power_hand_calculation():
    calls = []
    result = run_size(
        720.0, calls, mass_without_battery_kg=10.0, duration_s=1800.0,
        e_pack_wh_per_kg=250.0, f_usable=0.8, reserve_fraction=0.25,
    )
    assert (result.status, result.iterations) == ("converged", 2)
    assert result.electrical_power_w == 720.0
    assert result.mission_energy_wh == 360.0
    assert result.battery_mass_kg == 2.25
    assert result.total_mass_kg == 12.25
    assert result.history_kg == [12.25, 12.25]
    assert calls == [10.0, 12.25]


@pytest.mark.parametrize("base", [0.0, 10.0])
def test_zero_power(base):
    calls = []
    result = run_size(0.0, calls, mass_without_battery_kg=base)
    assert (result.status, result.iterations) == ("converged", 1)
    assert result.electrical_power_w == result.mission_energy_wh == 0.0
    assert result.battery_mass_kg == 0.0
    assert result.total_mass_kg == base
    assert result.history_kg == calls == [base]


@pytest.mark.parametrize("p,changes,message,count", [
    (1.0, {"e_pack_wh_per_kg": 1e308}, "converted pack capacity", 0),
    (1.0, {"e_pack_wh_per_kg": MIN / 7200}, "converted pack capacity", 0),
    (1.0, {"f_usable": 1e-320}, "usable capacity", 0),
    (1e-200, {"duration_s": 1e-200}, "mission joules", 1),
    (MIN, {"duration_s": 0.5}, "mission joules", 1),
    (1e308, {"duration_s": 2.0}, "mission joules", 1),
    (1e308, {"reserve_fraction": 1.0}, "reserved joules", 1),
    (1e-200, {"e_pack_wh_per_kg": 1e200}, "battery mass", 1),
    (MIN, {"e_pack_wh_per_kg": 1.0}, "battery mass", 1),
    (1e308, {"e_pack_wh_per_kg": 1e-100}, "battery mass", 1),
    (MIN * 2, {"e_pack_wh_per_kg": 1 / 3600}, "mission Wh", 1),
    (1.0, {"mass_without_battery_kg": 1e308}, "total mass", 1),
    (1e308, {"mass_without_battery_kg": 1e308,
             "e_pack_wh_per_kg": 1 / 3600}, "total mass", 1),
    (0.0, {"mass_without_battery_kg": MIN / 2}, "total mass", 1),
    (float("inf"), {}, "power model", 1),
    (float("nan"), {}, "power model", 1),
    (-1.0, {}, "power model", 1),
])
def test_numeric_refusals(p, changes, message, count):
    calls = []
    with pytest.raises(ValueError, match=message):
        run_size(p, calls, **changes)
    assert len(calls) == count


@pytest.mark.parametrize("limit,steps,status,history", [
    (10.0, 3, "max_iterations", [2.0, 3.0, 4.0]),
    (2.5, 10, "diverged", [2.0, 3.0]),
])
def test_callback_once_per_iteration_without_extra_call(limit, steps, status, history):
    calls = []
    result = run_size(
        lambda mass: 3600.0 * mass, calls, mass_without_battery_kg=1.0,
        divergence_mass_kg=limit, max_iterations=steps,
    )
    assert result.status == status
    assert result.history_kg == history
    assert result.iterations == len(calls) == len(history)
    assert calls == [1.0] + history[:-1]


def test_tiny_usable_fraction_supported_when_outputs_are_normal():
    result = run_size(MIN * 3600.0, f_usable=MIN)
    assert result.status == "converged"
    assert result.mission_energy_wh == MIN
    assert result.battery_mass_kg == result.total_mass_kg == 1.0
