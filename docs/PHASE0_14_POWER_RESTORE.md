# Phase 0.14 — Restore single-signal decision power

## Why this phase exists

Phase 0.13 proved that the Phase 0.12 global decision gate had structural zero power for one isolated signal. With 64 null surrogates per target, the smallest empirical target-familywise p-value was 1/65. At the observed optimistic 63-row candidate family, a rank-one event needed at least 629 null trials before its Benjamini–Hochberg q-value could fall at or below 0.10.

Phase 0.14 raises the calibration to 1,023 surrogates per target. The minimum p-value becomes 1/1,024 and the conservative 63-row rank-one q-value becomes 63/1,024, approximately 0.0615. A single isolated event can therefore pass both the unchanged target-familywise alpha of 0.05 and the unchanged global FDR alpha of 0.10.

This phase restores statistical resolution. It does not claim that any real Phase 0.12 event will pass after recalibration.

## Frozen experiment

- use the same 64 locked multi-sector TESS CSV byte streams;
- reuse the exact Phase 0.9 seeds 0–63 and their accepted unmasked-null trials;
- add fixed seeds 64–1,022, for 959 new trials per target;
- execute 61,376 new surrogate trials in total;
- retain the same gap-aware circular moving-block bootstrap, 0.5-day blocks, 3.5 gap factor, six-duration search family, 1.5-day flattening window and SNR 5 operational threshold;
- perform no TESS download and no threshold relaxation;
- freeze no revised candidate table until all 64 targets contain all 1,023 maxima.

## Safe compute partition

The 959 extension seeds are divided into 120 deterministic chunks per target: 119 chunks of eight seeds and one final chunk of seven. Each trial and each chunk is canonically hashed and binds the target identity, sector label and exact campaign-input array hash.

Chunks are compute checkpoints only. They cannot create local candidate tables, local BH corrections or interim scientific claims. The final p-values are recomputed once from the complete 1,023-maximum distribution for every target, followed by one global candidate-table freeze and one global BH correction.

## Dimming-only extension

The existing Phase 0.9 runner searched each surrogate in both dimming and brightening directions. Only the maximum dimming statistic entered the empirical p-value. The matched brightening control used by candidate screening comes from the frozen real light curve, not surrogate brightening maxima.

For extension seeds 64–1,022, Phase 0.14 therefore generates the identical surrogate and runs the identical full dimming search, but omits the unused surrogate brightening search. It stores only the maximum dimming SNR and structural provenance needed for validation.

A real-input pilot sampled one frozen input from each deterministic batch and seeds 64 and 65. All eight maximum dimming SNR values matched the old dual-direction runner exactly. Aggregate measured time fell from 23.3338 seconds to 13.9677 seconds, a 1.6706-fold speedup. This is an exact removal of unused computation, not an approximation to the null statistic.

## Validation boundary

The protocol rejects:

- a seed outside 64–1,022;
- a missing, duplicated or reordered seed;
- a chunk not belonging to the frozen partition;
- a resealed trial or chunk with a foreign target, sector or input hash;
- a Phase 0.9 trial that is not an accepted unmasked null;
- a target calibration missing any of the 1,023 maxima;
- a plan whose empirical p grid does not restore rank-one BH power;
- any candidate-table freeze before all target calibrations are complete.

Candidate identities, event statistics, surrogate maxima and recalibrated p-values remain private. Public outputs may contain aggregate compute counts, cryptographic commitments, the power audit and candidate-safe final counts only.
