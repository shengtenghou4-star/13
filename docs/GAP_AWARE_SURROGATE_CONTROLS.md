# Gap-aware moving-block surrogate controls

## Problem

TESS light curves are not uniformly continuous arrays. Downlinks, momentum dumps, quality cuts, and stitched observing products create large gaps. A moving-block bootstrap that samples solely by array index can accidentally treat cadences on opposite sides of a gap as adjacent, or move one sector's residual and uncertainty structure into another sector.

Preserving timestamps is not sufficient: if the resampled residual sequence crosses a gap, the null curve contains a covariance pattern that was never observed continuously.

## Phase 0.7 rule

HOU-EARTH splits every campaign-input light curve at time separations greater than:

```text
3.5 × median cadence
```

Every resulting contiguous segment is processed independently:

1. estimate a segment-specific median baseline;
2. form residuals within that segment;
3. optionally neutralize explicitly supplied events using only points from the same segment;
4. draw circular moving blocks only from that segment;
5. move residuals and `flux_err` with identical block indices;
6. write the resampled values back to the original timestamps of that segment.

Residuals, uncertainty values, and neutralization interpolation never cross a detected observing gap.

## Evidence fields

Every surrogate trial records:

- method: `gap-aware-circular-moving-block-bootstrap`;
- `block_days`;
- `gap_factor`;
- number of contiguous segments;
- neutralized event and point counts;
- full-search dimming and brightening maxima.

Every target summary records minimum and maximum segment counts across trials. Since timestamps are fixed, these values should agree for all trials on a target.

## Why the null targets remain unmasked

For HD 10700, HD 20794, and HD 69830, Phase 0.7 does not blanket-remove detected excursions before bootstrapping. Real stellar and instrumental extremes remain available to the null distribution. The gap-aware rule prevents cross-gap fabrication without optimistically cleaning the background.

Known transiting systems are excluded from no-event surrogate inference entirely rather than moving known transits to artificial phases.

## Acceptance rule

A completed Phase 0.7 null target is valid only when:

- the declared method matches the frozen gap-aware method;
- `gap_factor` equals 3.5;
- segment counts are positive and internally consistent;
- exactly 64 surrogate trials are retained;
- the surrogate search duration family matches the physical recovery family.

## Limitations

- A 3.5-cadence threshold is a transparent engineering rule, not a universal astrophysical constant.
- Independent segment bootstrapping does not model correlations spanning a real observational gap; those correlations are not directly observed.
- A fixed 0.5-day block length is still a pilot choice. Survey-scale work should compare several block lengths selected without inspecting candidate outcomes.
- The bootstrap estimates an empirical pipeline background, not the probability that a particular event is planetary.
