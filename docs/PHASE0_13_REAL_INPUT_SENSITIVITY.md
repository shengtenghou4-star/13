# Phase 0.13 — Frozen-real-input sensitivity and decision-power audit

## Purpose

Phase 0.12 produced a valid pre-registered null campaign on 64 exact, multi-sector TESS light curves. Phase 0.13 asks what that null result can physically exclude and whether the final global decision rule had enough statistical resolution to detect one isolated signal.

This phase does **not** alter Phase 0.12 and does not reopen candidate rows. It reuses the exact locked CSV bytes, the exact 64-surrogate target calibrations, and the exact symmetric brightening controls.

## Frozen injection grid

Every one of the 64 targets receives the same paired grid:

- intrinsic midpoint depths: 200, 500, 1,000, and 2,000 ppm;
- total durations: 0.052, 0.08, 0.16, and 0.232 days;
- two deterministic phase seeds per depth-duration cell;
- 32 pre-registered slots per target and 2,048 slots in total.

Before any search, the plan lock computes and hashes whether each target-duration cell has at least one valid center. A geometrically unavailable slot is recorded as unavailable, is never injected, and is excluded from the recovery denominator rather than counted as a failure. No alternate center or relaxed coverage rule is introduced after seeing availability.

The same phase seed selects the same valid center across depths for a given target and duration, creating a paired depth experiment. Valid centers must retain at least 70% local cadence coverage, contain no large cadence gap, and avoid every frozen dimming and brightening-control event.

The injected model is a quadratic-limb-darkened, exposure-averaged small-planet transit with fixed impact parameter 0.5, limb coefficients 0.35/0.25, and supersampling factor 7. The fixed geometry is a calibration convention, not a claim about any particular planet.

## Unchanged search and calibration

Each injected light curve is searched with the exact Phase 0.9/0.12 settings:

- duration family: 0.052, 0.08, 0.104, 0.116, 0.16, and 0.232 days;
- flattening window: 1.5 days;
- machine threshold: SNR 5;
- maximum 200 dimming events;
- the original target's 64 gap-aware surrogate maxima;
- the original target's matched brightening controls.

No TESS data are downloaded and no surrogate, SNR, p-value, control, or FDR threshold is relaxed.

## Three recovery layers

1. **Locator recovery** — at least one machine event lies within the frozen timing tolerance of the injection.
2. **Target-gate recovery** — the injected event wins the target's deterministic candidate selection, has target-familywise p <= 0.05, and exceeds the matched brightening control.
3. **Campaign-screened recovery** — the injected target event stream replaces that target's original stream, all other 63 target streams remain unchanged, and the injected event is screened in after one global Benjamini-Hochberg correction at q <= 0.10.

Target-gate completeness is the primary physical sensitivity metric and is calculated over eligible physical injections only. Every public cell separately reports scheduled slots, eligible injections, and geometrically unavailable slots. Campaign-screened completeness is retained as a decision-power diagnostic.

## Structural global-power audit

With 64 surrogate trials, the smallest empirical familywise p-value is 1/65. The real Phase 0.12 table contains 62 candidates, including eight at that minimum. At FDR alpha 0.10, at least ten minimum-p candidates are required for the minimum p-value to pass BH. One isolated injection can produce at most a ninth minimum-p candidate. Therefore the frozen global rule has zero single-signal screening power at this p-value resolution.

The result does not invalidate the Phase 0.12 null under its frozen protocol. It means that `screened_in = 0` cannot by itself exclude one strong isolated planet. At the current family size, at least 629 surrogate trials per target are required even for an optimistic rank-one p-value to become BH-resolvable; 1,023 trials is the predeclared power-of-two upgrade target for a future protocol.

## Integrity and privacy

Each target becomes an atomic, self-hashed checkpoint only after all 32 pre-registered slots are accounted for as either executed or geometrically unavailable. A checkpoint binds the Phase 0.13 plan lock, exact input and calibration hashes, all trial identities, and all three recovery outcomes. Partial, foreign, duplicated, resealed, or grid-incomplete checkpoints are rejected.

Target-level centers, recoveries, SNRs, p-values, q-values, and identities remain private. A public receipt may contain only the frozen plan, aggregate global/stratum completeness cells, the decision-power audit, counts, and cryptographic commitments. This phase is a sensitivity calibration, not an astronomical discovery claim.
