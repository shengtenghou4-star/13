# Phase 0.3 — Real TESS injection engine

## What changed

HOU-EARTH can now measure single-transit recovery on observed TESS light curves rather than only on synthetic Gaussian-noise fixtures.

The engine:

1. downloads a bounded number of public light-curve products;
2. records archive provenance and observing metadata;
3. runs the detector before injection;
4. finds well-sampled injection windows away from pre-existing events and data gaps;
5. injects a hidden event at a deterministic random location;
6. reruns the detector without using injection metadata;
7. separates the recovered event, pre-existing events, and novel competing detections;
8. reports per-target and pooled completeness with 95% Wilson intervals.

## Anti-leakage design

The injection center is never selected from the detector output after injection. Candidate windows are prepared from the original curve and must:

- meet a minimum local cadence-coverage threshold;
- contain no gap larger than 3.5 median cadences;
- remain separated from every pre-injection event by a duration-scaled exclusion zone.

This prevents a large fraction of artificial easy wins caused by injecting into already anomalous or poorly sampled regions.

## Deep-dip preservation fix

The original preprocessing used symmetric sigma clipping. On bright stars, a genuine deep transit may be tens of standard deviations below the median and can therefore be deleted before the search begins.

Phase 0.3 clips positive artifacts by default while preserving negative excursions. Symmetric clipping remains available only when explicitly requested for a non-transit workflow.

## Evidence outputs

Every target produces:

- `manifest.json` — experiment configuration, git commit, and light-curve provenance;
- `null_screen.json` — pre-injection event count and maximum SNR;
- `background_events.json` — all retained pre-injection detections;
- `trials.csv/json` — one row per seed, depth, and duration;
- `completeness.csv/json` — per-target recovery estimates and intervals;
- `report.html` — compact human-readable evidence table.

The batch root additionally produces:

- `batch_summary.json` — success/failure status and failure stage for every target;
- `pooled_completeness.csv` — depth-duration aggregation across completed targets.

## First cloud experiment

The first manifest contains three independent screening backgrounds:

- HD 10700;
- HD 20794;
- HD 69830.

The experiment uses one downloaded product per target, two depths, two durations, and four seeds: 16 blind injections per target and 48 planned trials if all three archive queries complete.

These targets are not declared signal-free. Any pre-injection event remains in the evidence package and is treated as an unresolved observational signal or systematic until separately vetted.

## Local regression validation

The engine code path was exercised on a deterministic 12-day fixture:

- 2/2 strong injected events recovered;
- median timing error: 0.0104167 days;
- median recovered SNR: 15.48;
- no novel competing events;
- positive outlier removed while a 3% negative dip was retained.

The frozen record is `results/real-engine-fixture-v0.3.0/manifest.json`. This is a software regression result, not real TESS completeness evidence.

## Next evidence gate

Phase 0.3 is complete only when at least one public TESS target batch produces downloadable, versioned artifacts. Phase 1 then expands the sample by brightness, variability, crowding, cadence, and target type, with at least 30 injections per reported depth-duration cell.
