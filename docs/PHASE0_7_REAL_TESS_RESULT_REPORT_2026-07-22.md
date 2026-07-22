# HOU-EARTH Phase 0.7 real TESS calibration result

**Date:** 2026-07-22  
**Validated source head:** `e2c15cfb780aaf8f9cd4c2808f186d75be8e2c67`  
**Merged commit:** `3d66eda06f3c8ea93531c339b1410f7a05f5a0da`  
**Claim level:** target-stratified calibration methodology  
**Discovery claim:** none

## Executive result

HOU-EARTH completed a six-target genuine-TESS pilot containing:

- 192 exposure-averaged, quadratic-limb-darkened single-transit injections;
- 192 gap-aware moving-block no-injection surrogate curves;
- three targets eligible for empirical null inference;
- three known transiting systems retained only as physical-injection backgrounds;
- one shared six-duration search family for both injections and null maxima;
- target-level add-one empirical familywise p-values;
- two independent machine-readable evidence validators.

All six targets completed, no target failed, and both protocol validators accepted the
evidence package.

The central scientific result is that **raw event recovery and calibrated statistical
significance are materially different quantities**. Of 192 injected events, 92 were
recovered by location and duration, but only 39 also exceeded the target-specific
full-search null distribution at empirical `p <= 0.05`.

## Fixed experiment

| Axis | Values |
|---|---|
| Intrinsic midpoint depth | 100, 200 ppm |
| First-to-fourth contact duration | 0.08, 0.16 days |
| Impact parameter | 0.0, 0.6 |
| Seeds | 0, 1, 2, 3 |
| Physical trials per target | 32 |
| Null trials per eligible target | 64 |
| Search durations | 0.052, 0.08, 0.104, 0.116, 0.16, 0.232 days |
| Empirical significance resolution | 1/65 = 0.0153846 |

The injected model uses quadratic limb darkening, the small-planet local-intensity
approximation, and seven-point finite-exposure integration. The requested depth is the
instantaneous intrinsic midpoint depth; the flux placed into the TESS light curve is
exposure averaged.

## Target-level outcome

| Target | TESS mag | Point-to-point scatter | Lag-1 correlation | Raw recovery | Empirical p <= 0.05 |
|---|---:|---:|---:|---:|---:|
| HD 10700 | 2.746 | 54.4 ppm | 0.409 | 32/32 | 8/32 |
| HD 20794 | 3.584 | 55.5 ppm | 0.239 | 32/32 | 23/32 |
| HD 69830 | 5.266 | 147.0 ppm | 0.062 | 28/32 | 8/32 |
| AU Mic | 6.755 | 311.7 ppm | 0.999 | 0/32 | not null-calibrated |
| TOI-700 | 10.910 | 1,621.7 ppm | 0.020 | 0/32 | not null-calibrated |
| LHS 3844 | 11.924 | 3,210.6 ppm | 0.079 | 0/32 | not null-calibrated |

The zero recoveries for the fainter targets are consistent with their cadence-scale
scatter being many times larger than the injected 100–200 ppm depths. AU Mic has lower
point-to-point scatter than those targets but extreme temporal correlation and strong
stellar variability; treating it as white noise would be invalid.

## Gap-aware null distributions

Only HD 10700, HD 20794, and HD 69830 entered the no-event surrogate sample. Residuals
and flux uncertainties were resampled together within contiguous observing segments;
blocks could not cross downlink or quality gaps.

| Target | Segments | Median maximum dimming SNR | p95 maximum dimming SNR | Maximum dimming SNR | Fraction above nominal 5 SNR |
|---|---:|---:|---:|---:|---:|
| HD 10700 | 11 | 17.17 | 24.31 | 26.52 | 100% |
| HD 20794 | 12 | 9.58 | 11.38 | 11.85 | 100% |
| HD 69830 | 8 | 6.79 | 10.64 | 11.26 | 84.4% |

This invalidates the interpretation of nominal white-noise `5 sigma` as a calibrated
false-alarm threshold for the full single-event search. Every null statistic is a
maximum over all searched times and all six durations, so the empirical comparison
incorporates the within-light-curve look-elsewhere effect.

## Bright-target calibrated completeness

Aggregating the three null-eligible bright targets:

| Depth | Duration | Impact | Raw recovery | Empirically significant |
|---:|---:|---:|---:|---:|
| 100 ppm | 0.08 d | 0.0 | 10/12 | 0/12 |
| 100 ppm | 0.08 d | 0.6 | 10/12 | 0/12 |
| 100 ppm | 0.16 d | 0.0 | 12/12 | 4/12 |
| 100 ppm | 0.16 d | 0.6 | 12/12 | 3/12 |
| 200 ppm | 0.08 d | 0.0 | 12/12 | 4/12 |
| 200 ppm | 0.08 d | 0.6 | 12/12 | 4/12 |
| 200 ppm | 0.16 d | 0.0 | 12/12 | 12/12 |
| 200 ppm | 0.16 d | 0.6 | 12/12 | 12/12 |

Thus, on this pilot sample, 200 ppm events lasting 0.16 days are the only cell with
100% calibrated recovery across all three bright null targets. A 100 ppm event may be
located successfully yet remain statistically ordinary relative to the target's own
full-search red-noise extrema.

## Compatibility with earlier calibration

The same source head also passed the previously frozen genuine-TESS workflows:

- 48 trials at 4,000–8,000 ppm;
- 216 trials at 500–2,000 ppm;
- 432 trials at 50–200 ppm.

The 432-trial pooled completeness curve and duration-matched brightening-control results
were reproduced cell by cell. The Phase 0.7 provenance changes did not alter the
published v0.6 sensitivity boundary.

## Evidence identity

- workflow run: `29909416379`
- artifact ID: `8525598300`
- artifact name: `stratified-physical-tess-v0.7`
- artifact SHA-256: `b19fe9db4a356608b374f8e49d7d224062e61a3f218fb2d4b60568aea72f4b0a`
- completed targets: 6
- physical trials: 192
- surrogate trials: 192
- main protocol validation: accepted
- gap-aware protocol validation: accepted

The artifact was downloaded, its ZIP digest independently recomputed, and its summaries,
per-target trials, fingerprints, null extrema, and validation reports inspected before
merge.

## Limitations

1. Six targets are insufficient for survey-wide TESS completeness.
2. The generic limb-darkening coefficients are a shape stress test, not target-specific
   atmosphere modeling.
3. The pilot uses only one selected product per target.
4. Empirical p-values from 64 null curves support a 5% screen but not a 1% claim.
5. The known transit hosts were not null-calibrated, because resampling their known
   transits would contaminate the no-event distribution.
6. A recovered injected event is not an astrophysically validated planet signal.
7. The current target strata are engineering descriptors, not a population model.

## Next gate

Before any manual candidate inspection, Phase 0.8 must freeze a complete machine-ranked
candidate table with target-level empirical p-values, table-wide multiplicity control,
input-array fingerprints, deterministic ordering, and an immutable table hash.
