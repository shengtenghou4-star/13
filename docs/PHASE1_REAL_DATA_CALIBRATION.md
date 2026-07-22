# Phase 1 protocol: injection into real TESS light curves

## Scientific question

How does HOU-EARTH single-transit recovery degrade on real TESS flight data as a function of transit depth, duration, target brightness, cadence, crowding, and stellar variability?

## Frozen experiment design

1. Select quiet, planet-free-or-masked TESS targets in magnitude bins.
2. Retain real timestamps, gaps, uncertainties, spacecraft systematics, and stellar noise.
3. Inject isolated box and limb-darkened transit models at randomized valid times.
4. Run the detector blind to injection metadata.
5. Record recovery, timing error, recovered SNR, competing events, and runtime.
6. Run matched null curves with no injection to estimate false-alarm rates.
7. Freeze target IDs, product identifiers, sectors, random seeds, code commit, and output tables before interpreting results.

## Initial bins

- TESS magnitude: 8-10, 10-12, 12-14
- Variability: quiet, moderate, active
- Crowding: low and elevated contamination
- Cadence: 2-minute and 20/30-minute products when available
- Depth: 0.1%, 0.2%, 0.4%, 0.8%, 1.2%
- Duration: 1, 2, 4, 8 hours

## Evidence gates

- At least 30 null light curves per major bin.
- At least 30 injections per depth-duration cell before headline claims.
- Binomial uncertainty reported with every completeness estimate.
- No target inspected manually before the frozen candidate/output table exists.
- Real-data conclusions must remain separate from synthetic v0.2.0 results.

## Deliverables

- `data/target_manifest.csv` with archive product provenance
- `results/real-injection-v0.1/` with trial and summary tables
- completeness and false-alarm curves
- failure taxonomy with representative examples
- a benchmark report suitable for external review
