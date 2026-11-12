# V149 v2: First provenance-bound real-polar source artifact (source/data qualification only)
Supersedes v1 memo (88a9b4ab...) with reviewer corrections applied. Status unchanged:
source qualification artifact. NO import, NO numerical comparison, NO joint cl/cd
mapping, NO actual-blade fit claim, NO extrapolation-readiness claim, NO model/API/
production change, NO signup, NO spend. Primary-source existence does not validate the
rotor and does NOT upgrade UNVERIFIED_CALLER_ASSERTION labels.

## 1. Requirement envelope (DERIVED from the current request fixture - labeled derived)
Fixture (tests/drone/test_polar_rotor.py): tip_radius 0.6 m, hub 0.2 m, chord 0.1 m,
angular_speed 50 rad/s, imposed axial 5 m/s.
Assumptions (stated): geometric relative speed only - induced velocities EXCLUDED
(induction would raise the axial component; these are geometric no-induction ESTIMATES, not rigorous induced-flow bounds);
nu = 1.47e-5 m^2/s (ISA sea-level ~15 C, DERIVED constant); a = 343 m/s (DERIVED).
Hub (r=0.2): V = sqrt(5^2 + (50*0.2)^2) = sqrt(125) = 11.18 m/s -> Re ~ 7.6e4.
Tip (r=0.6): V = sqrt(5^2 + (50*0.6)^2) = sqrt(925) = 30.41 m/s -> Re ~ 2.07e5.
Mach ~0.033-0.089. Requirement: measured cl AND cd over alpha at Reynolds bracketing
~7.6e4-2.07e5, low Mach, reusable-data rights.

## 2. Selected source (MEASURED, primary)
UIUC Low-Speed Airfoil Tests (LSAT), Volume 1 distribution, "Test Series 1 Version
Q01.00D 12-05-97" (re-reduced March 1998 per readme history; supersedes obsolete
Version 1.01). Book: Selig, Guglielmo, Broeren, Giguere, "Summary of Low-Speed Airfoil
Data, Vol. 1", SoarTech Publications, 1995, ISBN 0-9646747-1-8 (book body NOT hosted;
see gap in section 3). Files retrieved 2026-11-12 from
m-selig.web.engr.illinois.edu/pd/pub/lsat/ (verbatim bytes; SHA256SUMS.txt covers EVERY
archive member, including inspected alternatives).
Section: Eppler 387 (cambered). Source annotation (FORMAT01.TXT example): "clean; used
to validate against LTPT data" - the source program's own cross-check statement against
NASA Langley LTPT; not our validation.

>>> MATERIAL MODEL-QUALITY CAVEAT (book section 2.5, cross-facility comparison): the
UIUC E387 wind-tunnel MODEL was, per the book, "slightly decambered and warped at the
trailing edge, which has an effect on the results" (comparison against NASA Langley
LTPT, Delft and Stuttgart E387 data). E387A polar values are the measured data for
THAT model as published; this source-stated caveat MUST accompany any future use. <<<

## 3. Measured vs digitized vs derived (kept distinct)
- MEASURED: all cl/cd values - UIUC low-speed low-turbulence wind tunnel
  (MANIFEST.TXT). E387A.LFT: 8 Reynolds blocks (30100, 40500, 50800, 61300, 101900,
  152600, 203100, 304400) with angle counts 97, 97, 97, 33, 33, 33, 33, 33 (verified
  from file). Full extended multi-loop stall-hysteresis sweeps only in the first three
  low-Re blocks; blocks 4-8 carry a single 33-angle up/down loop through stall
  (reviewer characterization; loop presence verified). Do not deduplicate sweep rows.
  E387A.DRG: 5 blocks (61000, 101000, 151600, 202300, 303000), ~10 angles each, columns
  alpha / Cl / Cd(average) / 4 spanwise wake-rake Cd's forming the average.
- DIGITIZED-BY-SOURCE: ASCII files are the source's re-reduced digital distribution.
  Vol 1 drag is book-tabulated; Vol 1 lift is NOT book-tabulated (digital-only).
- DERIVED (this agent, labeled): envelope above; interpolation fitness; cambered
  classification (cl(0) > 0, Cm ~ -0.085 constant in Vol 1 lift files).
- BOOK CONTEXT RESOLVED 2026-11-12 (free primary): the complete Vol 1 book is
  freely hosted by the author at
  https://m-selig.ae.illinois.edu/uiuc_lsat/Low-Speed-Airfoil-Data-V1.pdf
  (6,758,420 bytes, sha256 da6e1b71723a20c66ef6450011e42f3af26fc99147203daf2b2233ce14089de8).
  Its front matter states "Copyright (C) 1995 ... All rights reserved": the DATA
  license (section 4) does NOT cover the book body, so the PDF is retained INTERNAL
  only; this archive records exact URL, hash and attributed findings instead.
  Companion primary context retained internal-only on the same basis:
  AIAA 96-0062 experiments paper (sha256 082e1a9d4476a104de1365d956f91a9226eec3fada7ed25557ec32d88c5f7711)
  and JofAC spanwise-drag methodology paper (sha256 9fa52cdee6aa66fc47dbb3ba85724104fc554852b16a6d88639b8dd7a05c14dc),
  both at m-selig.ae.illinois.edu/pubs/.
- SOURCE-STATED UNCERTAINTY (book section 2.4, Coleman & Steele method; the source's
  own facility estimates, quoted for context - NOT transferred error bars for any
  PhysiCore prediction; no model-prediction-uncertainty upgrade): freestream velocity
  within 0.5% (<0.3% excluding probe errors); cl overall 1.5% (lift-balance
  calibration dominant); cd: instruments <1%, repeatability <1.5%, spanwise-rake
  selection 3% at Re=100,000 reducing to ~1.5% at Re>=200,000; angle of attack
  +/-0.08 deg (6-point calibration); tunnel turbulence intensity <0.1%; wall/wake
  blockage corrections per book ch. 2. EXPLICIT LOW-Re CAVEAT (verbatim): "At
  Re = 60,000 and below, the flow is dominated by laminar separation bubbles that
  produce large variations in profile drag that make it difficult to confidently
  assign a measure of accuracy."
- Mach: low-speed tunnel class; per-run Mach not stated per polar. Any future
  declared_mach_interval must carry this provenance, not an invented number.

## 4. License / reusable-data rights (verbatim, readme.TXT)
"The airfoil performance data is copyrighted, and restrictions are placed on its use.
The data may be freely copied and used in any way, e.g., for personal use, in magazine
articles or with a commercial product. If the data is used in a magazine article or
book, the author must reference the appropriate volume of Summary of Low-Speed Airfoil
Data and give the address of where it can be obtained. If the data is used in a
commercial product, there must be no extra charges for providing it - other than the
cost of reproduction and distribution. All products that make use of this data must
conspicuously state that it was produced under the UIUC Low-Speed Airfoil Test program,
and no restrictions can be placed on the recipient with respect to their use of the
source data. Furthermore, they must be allowed to copy the original data and freely
distribute it as well." GPL.TXT referenced for details; license, copyright notice and
MANIFEST.TXT must accompany each distribution - all three are included here.

## 5. Applicability (fit; limits honest)
- Model consumes cl (stable_section_residual.py:257) and cd (section_load.py:306);
  Cm unused. Vol 1 Cm column is fixed placeholder (E387A: -0.085 constant; N0009:
  0.0000) - Cm NOT USABLE from this distribution.
- Envelope fit: needed 7.6e4-2.07e5 lies INSIDE measured drag range 61,000-303,000;
  every required Re interpolates between adjacent measured blocks. This is a coverage
  statement only - NOT an extrapolation-readiness or accuracy claim.
- LFT and DRG Reynolds blocks DIFFER (e.g. 61,300 lift vs 61,000 drag): any future
  import must not merge blocks as if co-located; mapping is a separately reviewed
  build decision, not made here.
- Section choice: E387 cambered, chosen for measured coverage and provenance; not
  asserted to match any actual PhysiCore blade. Alternatives inspected and rejected on
  evidence: NACA 0009 (no drag file; lift tops at Re 100,700, below the envelope);
  GEMINI (starts at Re 101,600 - misses the low end; fixed Cm); BW-3 (expected
  symmetric, but measured behavior is cambered: cl(0) ~ +0.2, Cm extrema across the
  file -0.2039 to +0.0208). Alternative files retained and hashed for the record.

## 6. Explicit non-claims
No physical validation, no rotor accuracy claim, no synthetic-equivalence claim, no
upgrade of caller-assertion labels, no production readiness. Any future flat-vs-real
comparison is a separate reviewed spec cycle.
