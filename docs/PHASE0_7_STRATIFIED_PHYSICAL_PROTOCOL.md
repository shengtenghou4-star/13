# Phase 0.7 stratified physical-transit protocol

**Status:** frozen development protocol; flight-data execution pending  
**Scientific claim level:** calibration methodology only  
**Discovery claim:** none

## 1. Purpose

Phase 0.4–0.6 established that HOU-EARTH can run blind single-event injection/recovery on genuine TESS products and measured a first 50–200 ppm sensitivity boundary on three bright stars. Phase 0.7 asks a harder question:

> Does the measured sensitivity survive changes in target brightness, short-timescale noise, long-timescale variability, crowding, red correlation, transit geometry, and finite exposure time?

The experiment is frozen before inspecting its flight-data outcomes.

## 2. Target manifest

The six-target pilot is defined in `data/stratified_targets_v0.7.csv`.

| Target | Physical injection | No-event surrogate | Intended role |
|---|---:|---:|---|
| HD 10700 / Tau Ceti | yes | yes, unmasked | bright low-scatter reference |
| HD 20794 | yes | yes, unmasked | bright reference with revised RV architecture |
| HD 69830 | yes | yes, unmasked | harder bright-star background |
| AU Mic | yes | no | active known transiting system |
| TOI-700 | yes | no | mid-magnitude M-dwarf known transiting system |
| LHS 3844 | yes | no | fainter M-dwarf known transiting system |

`data/null_target_audit_v0.7.csv` freezes the external archive review used for this policy. “No-event surrogate” means no confirmed transiting system was used in the pilot qualification; it does **not** mean planet-free, signal-free, or certified quiet.

Known transit hosts remain valid physical-injection backgrounds because the injection windows avoid pre-existing detected events. They are excluded from no-event surrogate inference so known transits are not moved to artificial phases and counted as false alarms.

## 3. Fixed physical-injection grid

For every successfully downloaded target:

- intrinsic midpoint depths: 100 and 200 ppm;
- first-to-fourth contact durations: 0.08 and 0.16 days;
- impact parameters: 0.0 and 0.6;
- deterministic seeds: 0, 1, 2, and 3.

This gives `2 × 2 × 2 × 4 = 32` physical trials per target and **192 planned trials** across six targets.

### Transit shape

The injector uses:

- exact overlap area for a unit stellar disk and circular planet disk;
- quadratic limb darkening;
- a controlled small-planet approximation for local occulted intensity;
- generic pilot coefficients `u1 = 0.35`, `u2 = 0.25`;
- finite-exposure midpoint supersampling, default 7 samples;
- the median observed cadence as the pilot exposure duration.

The requested depth is the **intrinsic instantaneous midpoint decrement**. The flux written to the light curve is exposure averaged. Each trial records radius ratio, limb coefficients, exposure duration, and supersample count.

Generic limb coefficients are a shape-stress test, not target-specific atmosphere modeling. Target-specific coefficients are a later gate.

## 4. Observed target strata

Each downloaded light curve records:

- TESS magnitude and magnitude bin;
- CROWDSAP and crowding bin;
- whole-light-curve robust variability amplitude;
- adjacent-cadence point-to-point scatter;
- six-hour binned scatter proxy;
- lag-1 autocorrelation and correlation bin;
- variability-to-point-scatter ratio;
- cadence, sectors, cameras, and CCDs.

Whole-light-curve scatter is not labelled as pure measurement noise. The scale-separated metrics distinguish smooth stellar activity from cadence-scale noise and red correlation.

## 5. No-event surrogate design

Only HD 10700, HD 20794, and HD 69830 enter the pilot null sample.

For each eligible target:

- 64 deterministic circular moving-block bootstrap curves;
- block duration 0.5 days;
- timestamps, gaps, uncertainties, and local covariance retained;
- no default residual sign flipping;
- no blanket removal of detected stellar or instrumental excursions;
- duration search grid: 0.04, 0.08, and 0.16 days.

The unmasked design is intentionally conservative: real excursions can be resampled and raise the empirical false-alarm threshold. Optional explicit event neutralization exists for later catalogue-masked experiments, but is not used for these three pilot null targets.

The planned null sample is `3 × 64 = 192` curves.

## 6. Empirical significance

Every surrogate is searched with a near-zero probe threshold. Its maximum dimming SNR over all searched times and durations enters the null distribution, including trials whose maximum is below the operational 5-SNR screen.

For a recovered injected signal with statistic `s` and `N` surrogate maxima `m_i`, HOU-EARTH reports

```text
p_emp = (1 + count(m_i >= s)) / (N + 1)
```

This add-one estimate:

- never reports zero probability;
- is corrected for the searched time and duration family because every `m_i` is a full-search maximum;
- has minimum resolution `1 / 65 = 0.0153846` for 64 null curves.

Phase 0.7 therefore supports a pilot `p <= 0.05` screen, but not a `p <= 0.01` claim.

The evidence separates:

1. raw recovery completeness;
2. recovery above same-light-curve brightening controls;
3. recovery significant against full-search surrogate maxima.

## 7. Frozen outputs

Each successful target must retain:

- product provenance and target stratum;
- pre-injection dimming and brightening events;
- every physical injection trial and completeness cell;
- every surrogate trial and null summary when eligible;
- every surrogate-calibrated physical trial;
- significant-completeness cells at empirical alpha 0.05;
- explicit skip evidence for known transit hosts.

The batch root must retain target failures with exact failure stage rather than silently dropping them.

## 8. Execution gates

The pilot is accepted only if:

1. the full repository test suite passes;
2. the synthetic CLI smoke test passes;
3. at least four of six physical-injection targets complete;
4. at least two of three null-eligible targets complete their 64-curve surrogate campaign;
5. every evidence artifact is uploaded and frozen with its source commit;
6. raw recovery and empirically significant recovery remain separately reported.

Failure of a target is evidence, not permission to change the grid after seeing results.

## 9. Prohibited interpretations

Phase 0.7 does not establish:

- discovery of a new planet;
- survey-wide TESS completeness;
- a universal SNR threshold;
- a calibrated 1% false-alarm probability;
- target-specific stellar-atmosphere realism;
- astrophysical validation of any detected event.

It is a stratified engineering and statistical calibration pilot designed to support the next survey-scale phase.
