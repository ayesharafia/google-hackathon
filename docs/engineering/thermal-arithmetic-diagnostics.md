# Thermal arithmetic diagnostics

The prior independent review reproduced 750 audit cases using Decimal precision 90 and seed 20261107: 500 thermal and 250 beam cases. Twelve additional thermal candidates with x = H dt / C > 500 were excluded. That exclusion biases coverage toward moderate exponents; the reviewed audit does not establish extended-range behavior or physical validation.

The pinned cancellation witness has a reported storage relative error of approximately 1.194746e-6. The test records the measured error without pinning its last bits. Independent exact-float-input Decimal calculations at precisions 90 and 120 check oracle agreement. Cancellation is not an established implementation bug: storage uses the returned binary64 temperature, and the nonzero arithmetic residual remains visible.

Rounding the returned temperature near T contributes roughly C times half an ulp to storage error. The witness-specific envelope 8 C ulp(T) conservatively allows preceding arithmetic too. It is a floating-point diagnostic, not a general error bound, approved tolerance, or physics acceptance criterion.

Explicit cases include x > 500. For these inputs, x <= 708 computes; x >= 709 refuses a subnormal or underflowed exponential intermediate despite a positive mathematical final temperature. These directly sampled binary64 boundaries establish neither a general computed range nor scientific accuracy. Evidence remains unverified, with aircraft status and feasibility unset.
