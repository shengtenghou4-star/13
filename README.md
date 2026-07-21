# HOU-EARTH / 侯星计划

**An open AI observatory for finding overlooked transiting worlds in NASA TESS data.**

HOU-EARTH is a reproducible research system for:

1. downloading and stitching public TESS light curves;
2. recovering known periodic transits as a calibration baseline;
3. detecting isolated and sparse transit-like events that ordinary periodic searches can miss;
4. ranking candidates with transparent diagnostics rather than a black-box probability alone;
5. exporting machine-readable candidate records and human-readable reports.

> Current status: **Phase 0 — calibrated discovery engine**. The code is research scaffolding, not a claim of a new planet.

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

The real-data command uses Lightkurve to query public products at MAST. It prefers SPOC products by default and can combine observations from multiple sectors.

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
examples/           runnable examples
tests/              injection-recovery tests
docs/ROADMAP.md     research phases and evidence gates
.github/workflows/  continuous integration
```

## Near-term success criteria

- Recover injected periodic signals with <2% period error in controlled tests.
- Recover isolated injected transit events within one cadence-scale tolerance.
- Reproduce at least three published TESS planets from public light curves.
- Produce a frozen, auditable candidate table before any novelty claim.

## License

MIT. Scientific data products retain the terms and attribution requirements of their original archives.
