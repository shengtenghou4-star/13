# Phase 0.12 locked-input search resume

## Purpose

The real Phase 0.12 selection stage froze 64 exact multi-sector TESS input CSV files before any transit search began. The search stage must consume those exact bytes. Re-downloading TESS products is forbidden because archive contents, product ordering, calibration versions, or availability can change after selection.

The locked-input resume protocol converts the authenticated selection package into the only permitted input source for the 4,096-surrogate blind campaign.

## Mandatory pre-search verification

Before the output directory is created or a search function is called, the resume executor must verify:

1. the complete private selection manifest and every listed file size and SHA-256;
2. the closed Phase 0.12 selection lock and its canonical SHA-256;
3. the original Phase 0.9-compatible campaign lock and its canonical SHA-256;
4. the binding from the campaign lock to the selection-lock SHA-256;
5. the exact 64 selected identities and their agreement across decisions and campaign targets;
6. four batches of exactly sixteen targets;
7. four targets from every stratum in every batch;
8. the exact expected CSV path for every selected identity;
9. the absence of missing or additional campaign-input files;
10. each CSV byte hash from the private manifest;
11. each reconstructed time, flux, and flux-error array hash against the frozen campaign-input commitment;
12. cadence count, baseline, median cadence, product count, sector label, and provenance hashes against the selection locks;
13. the candidate-safe selection receipt stating that no search or surrogate trial previously ran.

Any failure aborts before output creation and before the first search invocation.

## No-network rule

The resume executor has no downloader argument and performs no archive query. Its input mode is permanently recorded as:

`phase12-frozen-selection-csv-no-network`

A network re-download is not a fallback. Missing, corrupted, or inconsistent frozen inputs invalidate the campaign.

## Search and statistical boundary

The 64 locked inputs retain their four deterministic execution batches, but batching is only operational. Every target uses the unchanged Phase 0.9 search grid and exactly 64 gap-aware unmasked surrogate searches.

After all batches finish:

- every dimming machine event enters one complete event stream;
- every target calibration enters one campaign package;
- one candidate winner per target enters one candidate table;
- one global Benjamini-Hochberg correction is applied across all 64 candidates;
- no batch-level candidate table or batch-level discovery decision is permitted.

The expected null workload is exactly 4,096 surrogate trials.

## Private command

```bash
HOU_PRIVATE_EVIDENCE_SINK=1 \
python examples/run_phase12_locked_campaign.py \
  --selection-directory /private/path/phase12-selection-lock \
  --private-evidence-sink /private/path/phase12-search-output \
  --source-commit <40-character-search-source-commit>
```

## Evidence retained

The private search package includes:

- the original selection lock, original campaign lock, public selection receipt, and private selection manifest;
- a target-level locked-input receipt with CSV and array commitments;
- a new search campaign lock bound to the original selection-lock hash and the exact search source commit;
- four private batch receipts;
- all raw dimming and brightening machine events;
- all 4,096 surrogate trials;
- one global candidate table;
- complete event and campaign evidence;
- three independent validation reports;
- a candidate-safe aggregate receipt;
- a file-level private evidence manifest.

Candidate-level evidence remains private and unopened until the complete global package validates.
