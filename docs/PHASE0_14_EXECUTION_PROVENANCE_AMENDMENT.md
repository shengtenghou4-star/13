# Phase 0.14 execution-provenance amendment

## Scope

This amendment corrects an execution-identity field before any revised candidate table, manual candidate review, or astronomical claim.

The frozen Phase 0.14 scientific method remains unchanged: the same 64 Phase 0.12 inputs, unmasked gap-aware surrogate, seeds 0 through 1,022, duration family, flattening window, target-familywise alpha, and table FDR alpha remain binding.

## Detected discrepancy

The first private execution identity recorded a module SHA-256 that did not equal the SHA-256 of `src/houearth/phase14_power_restore.py` at the frozen scientific source commit. The exact public module is still bound by its Git blob and source commit, and every completed trial and chunk remains separately hash-bound. Nevertheless, the mismatched provenance field must not be silently inherited by later work.

## Correction

Subsequent execution uses a corrected run identity that verifies the exact public module bytes at process startup. Legacy chunks are retained only as numerical evidence with their original wrapper identities. Their inner trial and chunk receipts must validate under the frozen schemas.

Before a revised candidate table may be frozen, every legacy chunk must additionally be recomputed and each resulting trial SHA-256 must exactly match the archived trial SHA-256. Any mismatch keeps the candidate-table gate closed.

## Exact maximum-only optimization

The Phase 0.14 empirical p-value consumes only the maximum dimming SNR from each surrogate. The original implementation obtained that number by constructing and sorting all qualifying `SingleTransitEvent` objects before retaining the first event. A maximum-only execution path may omit construction of non-winning event objects only after exact trial-hash equivalence is demonstrated against the frozen implementation.

The optimization does not alter the surrogate, detrending, duration family, cadence windows, local-maximum rule, SNR arithmetic, threshold, empirical-p denominator, or global BH procedure.

## Disclosure boundary

This amendment contains no target identity, event time, SNR, empirical p-value, candidate rank, or astrophysical interpretation. It is an execution-integrity correction only.
