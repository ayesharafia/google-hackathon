"""Independent rounded-table fixtures plus domain/metamorphic tests.

Table: https://www.pdas.com/atmosTable1SI.html . Table altitude is geometric
(the 11 km tropopause occurs slightly above geometric 11 km). Tolerances here
cover source display rounding, not model-form uncertainty or aircraft error.
"""
import math
import unittest

from physimesh.drone.standard_atmosphere import (
    EARTH_RADIUS_M,
    MODEL_ID,
    standard_atmosphere,
)


class StandardAtmosphereTests(unittest.TestCase):
    def test_legacy_troposphere_still_refuses_high_altitude(self):
        from physimesh.drone.atmosphere import isa_troposphere
        self.assertEqual(isa_troposphere(0.0), (101325.0, 288.15))
        with self.assertRaises(ValueError):
            isa_troposphere(20000.0)

    def test_independent_geometric_table(self):
        fixtures = [
            (0.0, 101300.0, 288.1, 1.225),
            (10000.0, 26500.0, 223.3, 0.4135),
            (20000.0, 5529.0, 216.6, 0.08891),
            (22000.0, 4047.0, 218.6, 0.06451),
            (30000.0, 1197.0, 226.5, 0.01841),
        ]
        for z, p, t, rho in fixtures:
            with self.subTest(z=z):
                a = standard_atmosphere(z, altitude_kind="geometric")
                self.assertAlmostEqual(a.pressure_pa / p, 1.0, delta=0.0006)
                self.assertAlmostEqual(a.temperature_k, t, delta=0.11)
                self.assertAlmostEqual(a.density_kg_m3 / rho, 1.0, delta=0.0006)

    def test_geopotential_boundaries_and_continuity(self):
        for h, expected_t in [(11000.0, 216.65), (20000.0, 216.65)]:
            a = standard_atmosphere(h, altitude_kind="geopotential")
            self.assertAlmostEqual(a.temperature_k, expected_t, places=9)
            below = standard_atmosphere(h - 0.001, altitude_kind="geopotential")
            above = standard_atmosphere(h + 0.001, altitude_kind="geopotential")
            self.assertLess(abs(above.pressure_pa - below.pressure_pa) / a.pressure_pa,
                            1e-6)

    def test_altitude_conventions_are_not_interchangeable(self):
        h = 20000.0
        z = EARTH_RADIUS_M * h / (EARTH_RADIUS_M - h)
        g = standard_atmosphere(z, altitude_kind="geometric")
        p = standard_atmosphere(h, altitude_kind="geopotential")
        self.assertAlmostEqual(g.pressure_pa, p.pressure_pa, places=7)
        wrong = standard_atmosphere(h, altitude_kind="geometric")
        self.assertGreater(wrong.pressure_pa, p.pressure_pa)

    def test_refuses_nonfinite_out_of_range_and_wrong_types(self):
        for altitude in [-0.001, 30000.001, math.nan, math.inf, -math.inf, True,
                         None, "20000"]:
            with self.subTest(altitude=altitude), self.assertRaises((ValueError, TypeError)):
                standard_atmosphere(altitude, altitude_kind="geometric")
        for kind in ["pressure", "MSL", "", None]:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                standard_atmosphere(20000, altitude_kind=kind)
        with self.assertRaises(TypeError):
            standard_atmosphere(20000)

    def test_positive_properties_monotone_pressure_and_provenance(self):
        previous = math.inf
        for z in range(0, 30001, 100):
            a = standard_atmosphere(z, altitude_kind="geometric")
            self.assertLess(a.pressure_pa, previous)
            previous = a.pressure_pa
            self.assertGreater(a.temperature_k, 0)
            self.assertGreater(a.density_kg_m3, 0)
            self.assertEqual(a.model_id, MODEL_ID)
            self.assertNotIn("VALIDATED_FOR_REGIME", a.evidence_status)


if __name__ == "__main__":
    unittest.main()
