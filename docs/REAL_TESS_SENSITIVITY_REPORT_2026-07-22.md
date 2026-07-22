# HOU-EARTH real TESS single-transit sensitivity report

**Date:** 2026-07-22  
**Status:** calibration result; not an exoplanet discovery claim

## Executive result

HOU-EARTH completed three reproducible injection/recovery campaigns on genuine two-minute TESS light-curve products for HD 10700, HD 20794, and HD 69830.

The campaigns contain **696 real-data injection trials** in total:

- 48 trials at 4,000–8,000 ppm;
- 216 trials at 500–2,000 ppm;
- 432 trials at 50–200 ppm.

All targets downloaded successfully, all workflows passed the full repository test suite, and every campaign produced a versioned evidence artifact. The first two grids saturated at 100% recovery. The 50–200 ppm grid produced the first measured detection boundary.

## Observed products

| Target | TESS sector | Cadences | Baseline | Median cadence |
|---|---:|---:|---:|---:|
| HD 10700 (Tau Ceti) | 3 | 12,915 | 20.28 d | 2.00 min |
| HD 20794 | 3 | 13,536 | 20.28 d | 2.00 min |
| HD 69830 | 7 | 16,341 | 24.45 d | 2.00 min |

These are bright-star engineering backgrounds, not certified signal-free stars. All pre-injection events are retained rather than silently labelled as false alarms.

## Matched background screen

Before injecting any signal, the same light curve is searched in two directions with mirrored preprocessing:

- downward, transit-like dimmings;
- upward brightenings, used as an empirical control population.

| Target | Dimming events | Brightening controls | Maximum dimming SNR | Maximum brightening SNR |
|---|---:|---:|---:|---:|
| HD 10700 | 16 | 17 | 15.39 | 27.66 |
| HD 20794 | 8 | 9 | 12.75 | 16.60 |
| HD 69830 | 4 | 1 | 9.07 | 6.00 |

The opposite asymmetries across targets show why one universal SNR threshold is inadequate.

## Pooled 50–200 ppm completeness

Each cell contains 48 blind injections: 16 random valid positions on each of three targets.

| Depth | Duration | Recovered | Completeness | 95% Wilson interval |
|---:|---:|---:|---:|---:|
| 50 ppm | 0.96 h | 8/48 | 16.7% | 8.7–29.6% |
| 50 ppm | 1.92 h | 18/48 | 37.5% | 25.2–51.6% |
| 50 ppm | 3.84 h | 33/48 | 68.8% | 54.7–80.1% |
| 100 ppm | 0.96 h | 34/48 | 70.8% | 56.8–81.8% |
| 100 ppm | 1.92 h | 41/48 | 85.4% | 72.8–92.8% |
| 100 ppm | 3.84 h | 46/48 | 95.8% | 86.0–98.8% |
| 200 ppm | 0.96 h | 47/48 | 97.9% | 89.1–99.6% |
| 200 ppm | 1.92 h | 48/48 | 100% | 92.6–100% |
| 200 ppm | 3.84 h | 48/48 | 100% | 92.6–100% |

This establishes a clear duration-dependent transition:

- 50 ppm is generally below reliable single-event sensitivity on this sample;
- 100 ppm is a high-completeness but target-dependent regime;
- 200 ppm is near saturation for events lasting at least about two hours.

## Target heterogeneity

The pooled curve hides a major scientific result: sensitivity differs sharply by target.

At 100 ppm:

| Target | 0.96 h | 1.92 h | 3.84 h |
|---|---:|---:|---:|
| HD 10700 | 16/16 | 16/16 | 16/16 |
| HD 20794 | 16/16 | 16/16 | 16/16 |
| HD 69830 | 2/16 | 9/16 | 14/16 |

Therefore candidate ranking must incorporate target-specific noise and variability rather than report depth alone.

## Duration-matched brightening controls

A single maximum brightening across all durations was found to be too conservative and duration-mismatched. HOU-EARTH now performs a non-destructive post-processing comparison against brightenings at the same duration, falling back to the nearest duration bin only when necessary.

Among recovered 100 ppm injections, the fractions stronger than the matched brightening control were:

| Duration | Recovered signals above matched control |
|---:|---:|
| 0.96 h | 31/34 = 91.2% |
| 1.92 h | 35/41 = 85.4% |
| 3.84 h | 37/46 = 80.4% |

For 50 ppm, those fractions fall to 62.5%, 50.0%, and 33.3%. Many 50 ppm recoveries therefore sit close to the empirical background extreme even when they pass the nominal detection threshold.

The empirical tail probabilities are coarse because each light curve contains few detected brightening controls. This metric is useful as a diagnostic, not yet a calibrated false-alarm probability.

## Reproducibility

The repository preserves:

- product and sector provenance;
- original dimming and brightening event lists;
- every injection seed and center;
- per-trial recovery, timing error, SNR, and competing-event count;
- per-target and pooled completeness;
- Wilson confidence intervals;
- duration-matched control post-processing;
- GitHub Actions workflow and artifact digests.

Relevant result directories:

- `results/real-tess-batch-v0.4.0/`
- `results/real-tess-threshold-v0.5.0/`
- `results/real-tess-ppm-v0.6.0/`

## Limitations

1. The sample contains only three bright stars and one product per target.
2. Injected signals are box-shaped rather than limb-darkened physical transit models.
3. The experiment measures detection near a known injected time; it does not validate astrophysical origin.
4. Brightening controls are not guaranteed to share the same generative process as dimming artifacts.
5. Survey-wide claims require magnitude, crowding, cadence, activity, and detector-position strata.

## Next scientific gate

The next phase should not merely extend the same three-star grid. It should:

1. add a stratified target manifest across TESS magnitude, variability, crowding, cadence, camera, and CCD;
2. inject limb-darkened transit models;
3. estimate red-noise-aware local significance with block or phase-scrambled surrogate curves;
4. measure false-discovery behavior on no-injection controls;
5. freeze the candidate table before manual inspection.

The present result is sufficient to demonstrate a functioning and quantitatively calibrated real-data single-transit engine. It is not yet sufficient for a survey completeness claim or a new-planet claim.
