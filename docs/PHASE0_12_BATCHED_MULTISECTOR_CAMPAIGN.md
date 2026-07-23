# Phase 0.12 batched multi-sector blind campaign

**Status:** protocol implementation and synthetic validation  
**Real candidate disclosure:** forbidden outside the encrypted/private evidence route  
**Discovery claim:** none

## Why this phase exists

Phase 0.11 proved that the complete blind evidence chain works on twelve real targets, but twelve targets are still too small a denominator for the long-period, sparse-transit search that HOU-EARTH is trying to make scientifically interesting.

Phase 0.12 therefore changes the scale, not the thresholds:

- freeze a 96-object ranked pool before search;
- require multi-product, multi-sector TESS coverage;
- select exactly 64 targets;
- divide the locked sample into four deterministic batches of sixteen;
- run the same 64-surrogate calibration on every target;
- aggregate all machine events into one global candidate table and one global BH screen.

The total null workload is exactly 4,096 full-search surrogate trials.

## Frozen pool and strata

The pool contains four strata with 24 ranked objects each:

- solar analogs;
- radial-velocity hosts without a confirmed transiting planet;
- cool nearby dwarfs;
- active, young, debris-disk, or otherwise harder controls.

Exactly the first sixteen eligible objects in each stratum are selected. Later ranks are fallback objects only. A target may be skipped only because:

1. the frozen NASA Exoplanet Archive snapshot associates it with a confirmed transiting planet;
2. no usable TESS product can be acquired;
3. the fixed multi-sector data gates fail.

No target can be replaced because its search result looks uninteresting.

## Multi-sector gates

Every selected target must satisfy all of the following before any search begins:

- exactly four products requested at most;
- at least two downloaded products;
- at least two distinct TESS sectors;
- at least 1,000 cleaned cadences;
- at least 20 days of total baseline;
- median cadence no longer than 0.1 day.

All 64 targets must be acquired, fingerprinted, catalog-audited, and assigned to batches before the output directory is created or a transit search starts.

## Deterministic batch plan

Within each stratum, selected positions 1–4 enter batch 1, 5–8 batch 2, 9–12 batch 3, and 13–16 batch 4. Each batch therefore contains exactly four targets from each stratum and sixteen targets total.

Batching is only an execution boundary. It does not create four independent statistical campaigns. All 64 target calibrations are combined into one complete event package, one frozen candidate table, and one global BH correction.

## Statistical method

Phase 0.12 preserves the Phase 0.9–0.11 method unchanged:

- six frozen duration windows;
- minimum machine-search SNR 5;
- symmetric brightening control;
- 64 gap-aware unmasked surrogate searches per target;
- empirical target-familywise p-values with denominator 65;
- complete machine-event preservation;
- one winner per target in the frozen candidate table;
- global BH screening;
- independent table, event-package, and raw-to-machine validators.

The protocol must contain exactly 64 selected targets and 4,096 surrogate trials.

## Real command

```bash
HOU_PRIVATE_EVIDENCE_SINK=1 \
python examples/run_phase12_private_real_campaign.py \
  --pool data/phase12_batched_multisector_pool.csv \
  --private-evidence-sink /private/path/hou-earth-phase12 \
  --source-commit <40-character-public-source-commit>
```

Real compute may run publicly only through the encrypted-envelope route established in Phase 0.10. Candidate-level plaintext must remain in ephemeral storage and be deleted before artifact upload.

## Required private evidence

A complete run retains:

- the exact 96-row frozen pool;
- raw NASA Planetary Systems snapshot and transit audit;
- Phase 0.12 selection lock;
- deterministic four-batch plan;
- Phase 0.9-compatible campaign lock;
- 64 exact stitched campaign-input CSV files;
- all dimming and brightening machine events;
- all 4,096 surrogate trials;
- per-batch receipts;
- complete global candidate evidence and campaign evidence;
- three independent validation reports;
- candidate-safe aggregate receipt;
- file-level private evidence manifest.

No candidate is opened or astrophysically classified until the complete global package validates.
