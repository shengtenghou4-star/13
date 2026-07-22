# HOU-EARTH research roadmap

## North-star claim

Build an open, auditable discovery engine that can surface long-period and sparse-transit candidates in public TESS observations, then move the strongest targets through professional-grade vetting and external follow-up.

## Phase 0 — Calibrated engine

**Evidence gate**

- deterministic synthetic injection-recovery tests;
- periodic baseline search;
- single-event search without a period assumption;
- machine-readable outputs and a reproducible report;
- continuous integration.

No novelty claim is allowed in this phase.

## Phase 1 — Known-planet and real-noise benchmark

- Freeze a benchmark of published planets, eclipsing binaries, stellar variables, and screened backgrounds.
- Reproduce at least three public TESS systems spanning short, medium, and long periods.
- Compare the dependency-light baseline with Astropy BoxLeastSquares.
- Measure completeness, precision, period error, event-time error, runtime, dimming background rates, and matched brightening-control rates.

**Evidence gate:** a public benchmark report with versioned target IDs, code commit, exact data products, and both raw and control-adjusted detection metrics.

## Phase 2 — Multi-sector sparse-transit search

- Stitch observations of the same TIC/Gaia source across years.
- Search for compatible pairs and triplets of isolated events.
- Infer admissible orbital-period families from event timing and stellar density.
- Rank nearby K/M dwarfs and bright follow-up targets first.

**Evidence gate:** a frozen candidate table produced before manual inspection.

## Phase 3 — False-positive court

Every serious candidate must pass:

- odd/even transit depth consistency;
- secondary-eclipse and ellipsoidal-variation checks;
- centroid and difference-image analysis;
- Gaia neighborhood contamination model;
- known TOI, EB, variable-star, asteroid, and spacecraft-event cross-matches;
- independent reviewer sign-off.

**Evidence gate:** one dossier per candidate with every rejection test visible.

## Phase 4 — External validation

- Submit appropriate candidates to community/professional vetting channels.
- Predict follow-up windows with uncertainty.
- Recruit photometric or radial-velocity partners.
- Publish null results and rejected candidates as carefully as surviving ones.

## Product track

The public observatory should eventually show:

- sky map and target pages;
- raw and detrended light curves;
- periodic and isolated-event evidence;
- every false-positive test;
- model/version provenance;
- next observation window;
- candidate status history.

## Anti-hype rule

Use the labels `signal`, `event`, `candidate`, `validated planet`, and `confirmed planet` precisely. The UI must never promote an automated score into a discovery claim.

## Phase 0.2 checkpoint — 2026-07-22

Completed:

- generalized known-planet benchmark registry;
- short-period benchmark: LHS 3844 b;
- medium-period benchmark: pi Mensae c;
- long-period benchmark definition: TOI-700 d using its eleven Year-1 sectors;
- deterministic 96-trial isolated-event completeness grid;
- frozen calibration manifest and machine-readable result table;
- separate cloud workflows for fast benchmarks, long-period recovery, and completeness.

## Phase 0.3 checkpoint — 2026-07-22

Completed:

- injection into observed TESS light curves while preserving timestamps, gaps, uncertainties, variability, and spacecraft systematics;
- coverage-aware injection windows that avoid pre-existing detections;
- product-level archive provenance;
- per-target and pooled completeness with Wilson intervals;
- a first three-target, 48-injection cloud batch definition;
- positive-only artifact clipping that preserves deep negative transit-like events.

## Phase 0.4 checkpoint — 2026-07-22

Completed:

- matched dimming and brightening searches with mirrored preprocessing;
- separate pre-injection dimming and brightening event catalogs;
- injection windows excluding both event populations;
- per-recovery SNR margin above the strongest same-light-curve brightening control;
- propagation of control-adjusted metrics into per-target, pooled, JSON, CSV, and HTML outputs;
- regression fixtures recovering a known downward event and a known upward event independently.

The next scientific bottleneck is no longer basic code-path realism. It is empirical calibration on downloaded TESS products: obtain the first cloud evidence package, inspect failure strata without changing frozen outputs, then expand across magnitude, cadence, crowding, and stellar-variability bins. The next algorithmic layer after that is segment-aware red-noise calibration and block-surrogate null experiments.
