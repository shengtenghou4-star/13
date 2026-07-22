# HOU-EARTH / 侯星计划

**An open AI observatory for finding overlooked transiting worlds in NASA TESS data.**

HOU-EARTH is a reproducible research system for:

1. downloading and stitching public TESS light curves;
2. recovering known periodic transits as a calibration baseline;
3. detecting isolated and sparse transit-like events that ordinary periodic searches can miss;
4. ranking candidates with transparent diagnostics rather than a black-box probability alone;
5. exporting machine-readable candidate records and human-readable reports.

> Current status: **Phase 0.4 — symmetric real-flight-data calibration engine**. The code is research scaffolding, not a claim of a new planet.

## Why this project exists

Most transit pipelines are strongest when a signal repeats several times. HOU-EARTH is designed to preserve that reliable baseline while extending the search toward long-period, single-transit, and sparse-transit candidates across multiple TESS sectors.

## Quick start

```bash
python -m pip install -e .
houearth synthetic --output outputs/synthetic-demo
```

The command creates a synthetic TESS-like light curve, injects a planet transit, runs both the periodic and single-event search, and writes:

- `lightcurve.csv`
- `periodic_candidate.json`
- `single_events.json`
- `report.html`
- `diagnostic.png` (when matplotlib is available)

## Run on real TESS data

Install the optional astronomy dependencies:

```bash
python -m pip install -e '.[tess]'
houearth tess "TOI 700" --min-period 1 --max-period 100 --output outputs/toi-700
```

The real-data command uses Lightkurve to query public products at MAST. It prefers SPOC products by default and can combine observations from multiple sectors. Product-level provenance is retained when available, including sector, TIC, camera, CCD, TESS magnitude, crowding metrics, and archive filename.

## Python API

```python
from houearth.synthetic import make_synthetic_lightcurve
from houearth.search import search_periodic_transits, search_single_transits

lc = make_synthetic_lightcurve(period=7.25, duration=0.22, depth=0.012)
periodic = search_periodic_transits(lc, min_period=2, max_period=15)
events = search_single_transits(lc)

print(periodic)
print(events[:3])
```

## Scientific guardrails

A dip is not a planet. HOU-EARTH records evidence and failure modes explicitly. Candidate promotion will require, at minimum:

- repeatability or a constrained future transit window;
- odd/even and secondary-eclipse checks;
- pixel-centroid and nearby-star contamination analysis;
- cross-matching against known TOIs, eclipsing binaries, variables, and instrumental events;
- independent human review and, for serious candidates, follow-up observations.

## Repository map

```text
src/houearth/       core library and CLI
data/                frozen target manifests
examples/            runnable experiments
tests/               injection-recovery and safeguard tests
results/             frozen, versioned calibration evidence
docs/ROADMAP.md      research phases and evidence gates
.github/workflows/   continuous integration and cloud experiments
```

## Near-term success criteria

- Recover injected periodic signals with <2% period error in controlled tests.
- Recover isolated injected transit events within one cadence-scale tolerance.
- Reproduce at least three published TESS planets from public light curves.
- Produce a frozen, auditable candidate table before any novelty claim.

## Phase 0.2: measured synthetic limits

HOU-EARTH includes a deterministic single-transit injection/recovery campaign rather than relying on one successful demo:

```bash
houearth calibrate-single
```

The first frozen calibration (`results/single-transit-v0.2.0/`) uses 96 trials over a depth-duration grid. Under its stated synthetic noise model, 0.4% events lasting 0.16 days were recovered in 6/8 trials, while every tested 0.8% event was recovered. These are software calibration results, not claims about completeness on real TESS flight data.

## Phase 0.3: injection into real TESS observations

The real-data engine retains the observed timestamps, gaps, uncertainties, stellar variability, and spacecraft systematics, then injects blind single events only into sufficiently sampled windows that do not overlap pre-existing detections:

```bash
houearth calibrate-real "HD 10700" --max-products 1
```

For every target it exports:

- archive and product provenance;
- the pre-injection event screen;
- every injection seed, center, depth, duration, and recovery decision;
- timing error and recovered SNR;
- novel competing detections separated from pre-existing events;
- 95% Wilson intervals for each completeness estimate.

The search preprocessing removes strong positive artifacts while preserving deep negative transit-like signals, including dips that would be many standard deviations deep on a very bright star.

The first cloud batch is defined by `data/real_calibration_targets.csv`. It runs 48 blind injections across three independently downloaded TESS background curves. These targets are screening backgrounds, not certified signal-free stars; all pre-injection events remain visible in the evidence package.

## Phase 0.4: same-light-curve brightening controls

Every real-data screen now runs two matched searches:

- a downward-event search for transit-like dimmings;
- an upward-event search for brightenings using the same duration grid, detrending, threshold, and mirrored artifact clipping.

The brightening population is an empirical control for flares and instrumental excursions in that exact light curve. Each target records the dimming-to-brightening event ratio, the difference between their maximum SNR values, and each recovered injection's SNR margin above the strongest brightening control. A brightening is not automatically a false alarm; this control is a conservative background reference, not a substitute for astrophysical vetting.

The v0.4 regression suite verifies that a single curve can independently recover a known dip and a known brightening, while the real-injection path carries the control-adjusted SNR through per-target and pooled reports.

## Known-planet benchmarks

```bash
houearth benchmark lhs3844b
houearth benchmark pimenc
houearth benchmark toi700d
```

The fast GitHub Actions matrix covers LHS 3844 b and pi Mensae c. The heavier TOI-700 d multi-sector benchmark is manual so ordinary commits do not repeatedly download eleven sectors.

## License

MIT. Scientific data products retain the terms and attribution requirements of their original archives.
