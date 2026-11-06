# Mission battery arithmetic support
- Constant-power mission energy is `E = P × dt`, in joules for watts and seconds.
- Pack specific energy converts as `q = pack_Wh_per_kg × 3600`, in J/kg.
- Reserve energy is `E_reserved = E × (1 + r)`.
- With usable fraction `f`, required nominal energy is `E_battery = E_reserved / f`.
- Battery mass is `battery_mass = E_reserved / (q * f)` kg; energy output is `MissionResult.mission_energy_wh = E / 3600` Wh and excludes reserve/usable adjustment.
- This patch rejects nonfinite or subnormal derived results within `size_battery`, positive underflow, and positive battery mass lost when added to base mass.
- These are numerical support boundaries, not physical thresholds; some mathematically finite answers could exist with rescaling that is not implemented.
- Legitimate zero-power cases remain supported with normal or zero total mass.
- Convergence parameters and status are unchanged; no validation or qualification is claimed.
- Separately, the tiny/subnormal efficiency-product crash in `electrical_power` is now addressed: shaft power is divided by the smallest positive efficiency first, then by the remaining efficiencies in ascending order. Zero shaft power still validates all efficiencies and enforces strict zipping; overflow is still refused. The normal-product branch is unchanged.
- Support for a future coupled mission full model is not claimed.

The ascending division order avoids amplifying rounding from a subnormal first-division result by applying the smallest efficiency divisor first, before the remaining divisors.
