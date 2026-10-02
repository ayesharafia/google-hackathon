"""Independent hand calculations for the mission payload screening contract."""

import pytest

from physimesh.drone.atmosphere import G0
from physimesh.drone.mass import CATEGORIES, MassItem, summarize
from physimesh.drone.models import AircraftStatus
from physimesh.drone.screening import CapacityCaseInput, RotorLimitPoint, capacity_from_cases


def _mass(empty_kg=100.0):
    return summarize([
        MassItem(category, category, empty_kg if category == "structure" else 0.0, (0, 0, 0))
        for category in CATEGORIES
    ])


def _case(case_id, thrust_n, *, body_n=-100.0, power_w=500.0, available_w=3000.0):
    rotors = tuple(RotorLimitPoint(
        f"r{i}", (0.0, 0.0, thrust_n), power_w, 600.0,
        "a" * 64, "b" * 64,
    ) for i in range(4))
    return CapacityCaseInput(case_id, rotors, (0.0, 0.0, body_n), "c" * 64,
                             0.0, 60.0, available_w)


def test_lowest_case_governs_capacity():
    hover = _case("hover", 400.0)
    hot = _case("hot_high", 350.0)
    report = capacity_from_cases(_mass(), ["hover", "hot_high"], [hover, hot],
                                 usable_energy_j=200_000.0)
    assert report.status is AircraftStatus.SCREENING_ONLY
    assert report.limiting_case_id == "hot_high"
    assert report.max_payload_kg == pytest.approx(1300.0 / G0 - 100.0)
    assert report.cases[0].max_payload_kg == pytest.approx(1500.0 / G0 - 100.0)
    assert report.cases[1].electrical_power_w == 2000.0
    assert report.cases[1].energy_required_j == 120_000.0


def test_missing_mission_case_blocks_headline():
    report = capacity_from_cases(_mass(), ["hover", "hot_high"], [_case("hover", 400)],
                                 usable_energy_j=200_000.0)
    assert report.status is AircraftStatus.INPUTS_INCOMPLETE
    assert report.max_payload_kg is None
    assert any("hot_high" in message for message in report.blocking)


@pytest.mark.parametrize("case,energy", [
    (_case("hover", 400, available_w=1000), 200_000.0),
    (_case("hover", 400, power_w=700), 200_000.0),
    (_case("hover", 400), 100_000.0),
    (_case("hover", 400), float("nan")),
])
def test_power_or_energy_limit_blocks_headline(case, energy):
    report = capacity_from_cases(_mass(), ["hover"], [case], usable_energy_j=energy)
    assert report.max_payload_kg is None
    assert report.blocking


def test_no_false_positive_when_empty_aircraft_cannot_be_supported():
    report = capacity_from_cases(_mass(200), ["hover"], [_case("hover", 400)],
                                 usable_energy_j=200_000.0)
    assert report.status is AircraftStatus.REQUIREMENT_NOT_MET
    assert report.max_payload_kg == 0
    assert report.cases[0].raw_payload_margin_kg < 0


def test_invalid_force_provenance_blocks_capacity():
    case = _case("hover", 400)
    case = CapacityCaseInput(case.case_id, case.rotors, case.body_force_world_n,
                             "not-a-sha", case.vertical_acceleration_m_s2,
                             case.duration_s, case.available_electrical_power_w)
    report = capacity_from_cases(_mass(), ["hover"], [case], usable_energy_j=200_000.0)
    assert report.max_payload_kg is None
    assert any("body_force_source_sha256" in item for item in report.blocking)
