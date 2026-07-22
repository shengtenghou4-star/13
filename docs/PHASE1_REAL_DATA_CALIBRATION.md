# Phase 1 protocol: injection into real TESS light curves

## Scientific question

How does HOU-EARTH single-transit recovery degrade on real TESS flight data as a function of transit depth, duration, target brightness, cadence, crowding, and stellar variability?

## Frozen experiment design

1. Select TESS screening backgrounds across magnitude, variability, cadence, and crowding bins; do not describe them as signal-free unless independently established.
2. Retain real timestamps, gaps, uncertainties, spacecraft systematics, and stellar noise.
3. Run matched downward-event and upward-event searches before injection using the same duration grid, detrending, threshold, and mirrored clipping.
4. Exclude both pre-existing dimmings and brightenings from allowed injection windows.
5. Inject isolated box and limb-darkened transit models at randomized valid times.
6. Run the detector blind to injection metadata.
7. Record recovery, timing error, recovered SNR, SNR above the strongest same-curve brightening control, competing events, and runtime.
8. Run matched no-injection and surrogate controls to estimate background event rates without automatically labelling astrophysical variability as a false alarm.
9. Freeze target IDs, product identifiers, sectors, random seeds, code commit, and output tables before interpreting results.

## Initial bins

- TESS magnitude: 8-10, 10-12, 12-14
- Variability: quiet, moderate, active
- Crowding: low and elevated contamination
- Cadence: 2-minute and 20/30-minute products when available
- Depth: 0.1%, 0.2%, 0.4%, 0.8%, 1.2%
- Duration: 1, 2, 4, 8 hours

## Evidence gates

- At least 30 no-injection light curves per major bin.
- At least 30 injections per depth-duration cell before headline claims.
- Binomial uncertainty reported with every completeness estimate.
- Dimming and brightening event-rate distributions reported together.
- Control-adjusted SNR must be reported alongside raw recovered SNR.
- No target inspected manually before the frozen candidate/output table exists.
- Real-data conclusions must remain separate from synthetic v0.2.0 results.

## Deliverables

- `data/target_manifest.csv` with archive product provenance
- `results/real-injection-v0.1/` with trial and summary tables
- completeness, dimming-background, and brightening-control curves
- failure taxonomy with representative examples
- a benchmark report suitable for external review
