"""Numerical cancellation regressions; these tests assert no physical envelope."""

import itertools
import math
import unittest

from physimesh.drone.hover_bemt import solve_hover


class HoverCancellationTests(unittest.TestCase):
    def solve(self, **overrides):
        parameters = {
            "radius_m": 1.0,
            "angular_speed_rad_s": 100.0,
            "density_kg_m3": 1.0,
            "blade_count": 2,
            "chord_m": 1e6,
            "lift_curve_slope_per_rad": 6.0,
            "profile_drag_coefficient": 0.01,
            "pitch_tip_rad": 0.1,
            "root_cutout_fraction": 0.5515456857425071,
            "annuli": 1,
        }
        parameters.update(overrides)
        return solve_hover(**parameters)

    def test_negative_attack_and_blade_regression_rejected(self):
        # Previously returned attack=-1.50e-36 and blade CT=-6.44e-31.
        with self.assertRaises(ValueError):
            self.solve(pitch_tip_rad=9.720576438286966e-21)

    def test_severe_cancellation_rejected_for_both_twist_laws(self):
        for law, pitch, annuli in itertools.product(
            ("constant", "hyperbolic"),
            (9.720576438286966e-21, 1e-16, 1e-8),
            (1, 32),
        ):
            with self.subTest(law=law, pitch=pitch, annuli=annuli), self.assertRaises(ValueError):
                self.solve(twist_law=law, pitch_tip_rad=pitch, annuli=annuli)

    def test_positive_but_inaccurate_blade_diagnostics_rejected(self):
        # Before the guard, positive blade CT at this pitch differed from an
        # independent momentum balance because subtraction loses significance.
        for law in ("constant", "hyperbolic"):
            with self.subTest(law=law), self.assertRaisesRegex(ValueError, "[Cc]ancellation"):
                self.solve(twist_law=law, pitch_tip_rad=1e-8)

    def test_zero_pitch_branch_preserved(self):
        for law, chord, annuli, drag in itertools.product(
            ("constant", "hyperbolic"), (0.005, 0.2, 1e6), (1, 32), (0.0, 0.01)
        ):
            with self.subTest(law=law, chord=chord, annuli=annuli, drag=drag):
                result = self.solve(
                    twist_law=law, chord_m=chord, annuli=annuli,
                    profile_drag_coefficient=drag, pitch_tip_rad=0.0,
                )
                for values in (
                    result.inflow_ratio, result.pitch_rad,
                    result.approx_inflow_angle_rad, result.approx_angle_of_attack_rad,
                ):
                    self.assertEqual(values, (0.0,) * annuli)
                for value in (
                    result.thrust_coefficient, result.blade_thrust_coefficient,
                    result.induced_power_coefficient, result.thrust_n,
                    result.thrust_balance_coefficient, result.max_local_balance_coefficient,
                ):
                    self.assertEqual(value, 0.0)
                self.assertEqual(result.shaft_power_coefficient, result.profile_power_coefficient)
                if drag == 0.0:
                    self.assertEqual(result.shaft_power_w, 0.0)
                    self.assertEqual(result.shaft_torque_nm, 0.0)
                else:
                    self.assertGreater(result.shaft_power_w, 0.0)
                    self.assertGreater(result.shaft_torque_nm, 0.0)

    def test_ordinary_conservative_domain_passes(self):
        for law, pitch, chord, cutout, annuli in itertools.product(
            ("constant", "hyperbolic"),
            (0.0001, 0.001, 0.01, 0.1, 0.3),
            (0.005, 0.01, 0.05, 0.1, 0.2),
            (0.1, 0.5515456857425071, 0.9),
            (1, 32),
        ):
            with self.subTest(law=law, pitch=pitch, chord=chord,
                              cutout=cutout, annuli=annuli):
                result = self.solve(
                    twist_law=law, pitch_tip_rad=pitch, chord_m=chord,
                    root_cutout_fraction=cutout, annuli=annuli,
                )
                self.assertTrue(all(a > 0.0 for a in result.approx_angle_of_attack_rad))
                self.assertGreater(result.blade_thrust_coefficient, 0.0)
                self.assertTrue(math.isclose(
                    result.blade_thrust_coefficient, result.thrust_coefficient,
                    rel_tol=1e-9, abs_tol=0.0,
                ))

    def test_precision_limit_is_relative_not_a_pitch_or_chord_cutoff(self):
        # Tiny pitch remains supported with resolved subtractions; large chord
        # remains supported when pitch gives sufficient numerical separation.
        for law in ("constant", "hyperbolic"):
            for pitch, chord in ((1e-8, 0.005), (0.1, 1e6)):
                with self.subTest(law=law, pitch=pitch, chord=chord):
                    result = self.solve(twist_law=law, pitch_tip_rad=pitch, chord_m=chord)
                    self.assertGreater(result.blade_thrust_coefficient, 0.0)
                    self.assertTrue(all(a > 0.0 for a in result.approx_angle_of_attack_rad))


if __name__ == "__main__":
    unittest.main()
