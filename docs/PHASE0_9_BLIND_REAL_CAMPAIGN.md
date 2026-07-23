# Phase 0.9 blind real-campaign protocol

**Status:** implementation and synthetic validation  
**Real candidate state:** prohibited from public artifacts  
**Discovery claim:** none

## Scope

Phase 0.9 connects the Phase 0.7 real-TESS calibration engine to the Phase 0.8 complete-event freeze. It is a three-target blind dry run, not a survey-wide search.

The predeclared null-eligible targets are HD 10700, HD 20794, and HD 69830. AU Mic, TOI-700, and LHS 3844 remain injection-calibration targets only because they are known transiting systems; they cannot supply an unmasked no-event null distribution.

## Two-stage lock

Every eligible light curve must be downloaded, cleaned, and fingerprinted before any event search. The campaign lock freezes the complete target manifest and its SHA-256, source commit, UTC freeze time, exact cleaned-array SHA-256, query/product provenance, common search-duration family, flattening window, machine threshold, exact 64 surrogate seeds, block length, gap factor, method, and all predeclared exclusions.

If any predeclared target fails to download or fingerprint, the entire lock aborts. A partial target set must never proceed to search.

Only after the complete lock exists may the pipeline search dimming events and symmetric brightening controls, generate 64 gap-aware unmasked full-search surrogates per target, derive target-familywise empirical p-values, retain the complete machine event stream, apply the Phase 0.8 winner/BH/control gates, and freeze the candidate evidence.

The Phase 0.9 package binds the campaign lock, raw dimming and brightening events, all surrogate trials, calibration receipts, and Phase 0.8 evidence. An independent validator recomputes every event p-value, matched control, source index, and machine row from the raw package.

## Familywise calibration

Each real event is compared with all 64 surrogate full-search dimming maxima:

`p = (1 + number(null maximum >= event SNR)) / 65`.

A surrogate trial with no dimming maximum remains in the denominator as a non-exceedance. It is never deleted to improve apparent resolution. The minimum resolvable p-value is `1/65`.

Null trials must use seeds exactly 0 through 63, method `gap-aware-circular-moving-block-bootstrap`, block length 0.5 days, gap factor 3.5, no neutralized events or points, matching target/sector, and at least one retained contiguous segment.

## Brightening control and identity

For each dimming event, the control duration is the available brightening duration nearest to the event duration; deterministic ties choose the shorter duration. The statistic is the maximum brightening SNR at that duration. Missing controls remain explicit and cause a Phase 0.8 exclusion rather than imputation.

Dimming events are canonically ordered by center time, duration, descending SNR, descending depth, local point count, and direction. Source indices are assigned only after this ordering, so input order cannot alter any row, winner, rank, or hash.

## Privacy boundary

The method repository is public. The real command therefore must require an explicit private evidence sink, must not have a public automatic real-data workflow, and must print only aggregate counts and cryptographic commitments. Event identities, times, depths, SNRs, ranks, raw surrogate trials, and candidate rows belong only in an access-controlled evidence location.

Public CI runs synthetic fixtures only. Synthetic artifacts contain no astronomical candidates.

## Required private evidence

A valid private run retains exact campaign-input CSV arrays, `campaign_lock.json`, raw dimming/brightening events, all 64 surrogate trials and summaries, calibration receipts, complete Phase 0.8 evidence, the Phase 0.9 campaign package, all independent validation reports, source commit, and SHA-256 commitments.

## Prohibited claims

Phase 0.9 does not establish a new planet, astrophysical validation, survey-wide completeness, occurrence rates, a clean null for known transiting systems, independence among targets/systematics, or permission to inspect/publish real candidate rows before the private freeze is complete and independently verified.
