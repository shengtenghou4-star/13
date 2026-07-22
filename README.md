# HOU-EARTH / 侯星计划

**An open, auditable observatory for overlooked transiting worlds in NASA TESS data.**

HOU-EARTH is a reproducible research system for:

1. downloading and preserving provenance for public TESS light curves;
2. recovering known periodic transits as calibration baselines;
3. detecting isolated and sparse transit-like events that periodic searches can miss;
4. measuring injection/recovery completeness on genuine flight-data backgrounds;
5. calibrating raw detections against same-light-curve and red-noise controls;
6. exporting machine-readable evidence and human-readable reports.

> **Current status:** the frozen v0.6 evidence contains 696 blind injections into genuine TESS light curves and a first 50–200 ppm sensitivity boundary. Phase 0.7 is an open validation PR that adds stratified targets, exposure-averaged physical transit shapes, moving-block null curves, and empirical familywise p-values. Its six-target flight-data campaign has **not yet completed** and is not presented as a result.

## Why this project exists

Most transit pipelines are strongest when a signal repeats several times. HOU-EARTH preserves that reliable baseline while extending the search toward long-period, single-transit, and sparse-transit candidates across TESS sectors.

The project treats a detected dip as an event, not a planet. Its purpose is to make sensitivity, background extremes, provenance, and failure modes auditable before any novelty claim.

## Quick start

```bash
python -m pip install -e .
houearth synthetic --output outputs/synthetic-demo
```

The synthetic command writes:

- `lightcurve.csv`
- `periodic_candidate.json`
- `single_events.json`
- `report.html`
- `diagnostic.png` when matplotlib is installed

## Run on real TESS data

Install the optional astronomy dependencies:

```bash
python -m pip install -e '.[tess]'
houearth tess "TOI 700" --min-period 1 --max-period 100 --output outputs/toi-700
```

The real-data path uses Lightkurve to query public MAST products. It prefers SPOC by default and retains product-level provenance when available, including sector, TIC, camera, CCD, TESS magnitude, crowding metrics, exposure, and archive filename.

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

A dip is not a planet. Candidate promotion requires, at minimum:

- repeatability or a constrained future transit window;
- odd/even and secondary-eclipse checks;
- pixel-centroid and nearby-star contamination analysis;
- cross-matching against known TOIs, eclipsing binaries, variables, and instrumental events;
- independent human review and, for serious candidates, follow-up observations.

## Repository map

```text
src/houearth/       core library, calibration, statistics, and CLI
data/               frozen target manifests and target-eligibility audits
examples/           runnable experiments and evidence validators
tests/              injection/recovery, statistics, and protocol safeguards
results/             frozen, versioned evidence
.github/workflows/   CI and cloud experiments
docs/                protocols, reports, and roadmap
```

## Completed calibration evidence

### Phase 0.2 — controlled synthetic limits

`results/single-transit-v0.2.0/` contains 96 deterministic injection/recovery trials over a depth-duration grid. These results validate software behavior under the stated synthetic noise model; they do not estimate TESS survey completeness.

### Phase 0.3–0.4 — real backgrounds and symmetric controls

The real-data engine retains observed timestamps, gaps, uncertainties, stellar variability, and spacecraft systematics. Blind events are injected only into adequately sampled windows that avoid pre-existing dimming and brightening detections.

Every real-data screen runs matched searches for:

- downward transit-like dimmings;
- upward brightenings with mirrored preprocessing.

Brightenings are an empirical control population, not automatically false alarms. Deep negative events are preserved during clipping instead of being silently deleted as outliers.

### Phase 0.4–0.6 — 696 real TESS injection trials

Three reproducible campaigns used two-minute TESS products for HD 10700, HD 20794, and HD 69830:

- 48 trials at 4,000–8,000 ppm;
- 216 trials at 500–2,000 ppm;
- 432 trials at 50–200 ppm.

The pooled 50–200 ppm grid measured the first duration-dependent boundary:

| Depth | 0.96 h | 1.92 h | 3.84 h |
|---:|---:|---:|---:|
| 50 ppm | 16.7% | 37.5% | 68.8% |
| 100 ppm | 70.8% | 85.4% | 95.8% |
| 200 ppm | 97.9% | 100% | 100% |

This is a three-target calibration result, not a survey-wide TESS completeness claim. See `docs/REAL_TESS_SENSITIVITY_REPORT_2026-07-22.md` and the frozen `results/real-tess-*` directories.

## Phase 0.7 — stratified physical-transit pilot

The development protocol is frozen in `docs/PHASE0_7_STRATIFIED_PHYSICAL_PROTOCOL.md` before inspecting flight-data outcomes.

The planned pilot contains:

- six TESS targets spanning bright references, an active star, and M-dwarf backgrounds;
- 192 physical injections at 100 and 200 ppm;
- exact circle-overlap geometry with quadratic limb darkening under a documented small-planet approximation;
- finite-exposure integration with seven sub-exposure samples and exposure provenance;
- separate whole-curve variability, point-to-point noise, six-hour scatter, and lag-1 correlation strata;
- 192 unmasked moving-block null curves across three targets without a confirmed transiting system in the pilot qualification;
- known transit hosts retained for physical injections but excluded from no-event null inference;
- add-one empirical p-values against per-target full-search surrogate maxima;
- an independent evidence validator that separates raw recovery from empirically significant recovery.

With 64 null curves per eligible target, the minimum resolvable empirical probability is `1/65 ≈ 0.0154`. The pilot can support a 5% screen, not a 1% claim.

Targeted deterministic validation is frozen in:

- `results/real-engine-fixture-v0.7.0/surrogate-validation.json`
- `results/real-engine-fixture-v0.7.0/physical-exposure-validation.json`

Those fixtures are synthetic or deterministic engineering evidence. They are not substitutes for the pending six-target TESS execution.

## Known-planet benchmarks

```bash
houearth benchmark lhs3844b
houearth benchmark pimenc
houearth benchmark toi700d
```

The fast Actions matrix covers LHS 3844 b and π Mensae c. The heavier TOI-700 d multi-sector benchmark is manual so ordinary commits do not repeatedly download many sectors.

## License

MIT. Scientific data products retain the terms and attribution requirements of their original archives.
