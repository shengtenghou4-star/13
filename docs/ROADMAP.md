# HOU-EARTH research roadmap

## North-star claim

Build an open, auditable discovery engine that can surface long-period and sparse-transit candidates in public TESS observations, then move the strongest targets through professional-grade vetting and external follow-up.

## Phase 0 — Calibrated engine (current)

**Evidence gate**

- deterministic synthetic injection-recovery tests;
- periodic baseline search;
- single-event search without a period assumption;
- machine-readable outputs and a reproducible report;
- continuous integration.

No novelty claim is allowed in this phase.

## Phase 1 — Known-planet benchmark

- Freeze a benchmark of published planets, eclipsing binaries, stellar variables, and clean negatives.
- Reproduce at least three public TESS systems spanning short, medium, and long periods.
- Compare the dependency-light baseline with Astropy BoxLeastSquares.
- Measure completeness, precision, period error, event-time error, and runtime.

**Evidence gate:** a public benchmark report with versioned target IDs, code commit, and exact data products.

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
