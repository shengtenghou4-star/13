# Phase 0.13 real-input sensitivity calibration

## Candidate-safe result

Phase 0.13 converted the completed Phase 0.12 null campaign into a physical injection/recovery sensitivity map on the exact 64 frozen multi-sector TESS light curves.

- 2,048 pre-registered injection slots;
- 2,016 eligible physical injections executed;
- 32 geometrically unavailable slots, all recorded separately rather than counted as recovery failures;
- four deterministic batches of sixteen targets;
- zero TESS downloads during injection execution;
- no search, calibration, brightening-control, familywise-p, or FDR threshold was relaxed;
- 1,572 locator recoveries (77.98% of eligible injections);
- 457 target-gate recoveries (22.67% of eligible injections);
- zero campaign-screened recoveries, as predicted by the pre-run global decision-power audit.

The primary metric is target-gate completeness: an injection must be localized, win deterministic target selection, pass the original target-familywise p gate, and exceed its matched brightening control.

## Global target-gate completeness

| Depth | 0.052 d | 0.080 d | 0.160 d | 0.232 d |
|---:|---:|---:|---:|---:|
| 200 ppm | 0.0% | 0.0% | 0.0% | 0.0% |
| 500 ppm | 0.0% | 4.8% | 14.3% | 15.1% |
| 1,000 ppm | 17.5% | 20.6% | 35.7% | 45.2% |
| 2,000 ppm | 46.8% | 48.4% | 57.1% | 57.1% |

Locator completeness is substantially higher, reaching 92.9%–96.0% for 2,000 ppm injections. The main loss therefore occurs at the calibrated target-selection/control gate rather than basic event localization.

## Structural decision-power finding

The Phase 0.12 global screening rule had zero power for one isolated signal at its frozen empirical-p resolution:

- 64 surrogates imply a minimum familywise p-value of 1/65;
- the 62-row global candidate table contained eight candidates at that minimum;
- Benjamini–Hochberg at alpha 0.10 required ten minimum-p candidates;
- one isolated signal could create at most a ninth.

Therefore Phase 0.12 remains a valid frozen null campaign, but its zero globally screened rows cannot alone exclude one strong isolated planet. At least 629 surrogate trials per target are required for optimistic rank-one BH resolution at the observed family size; 1,023 is the recorded future power-of-two target.

## Integrity and privacy

All 64 target checkpoints were independently reloaded and validated against the frozen plan, exact input identity, original calibration identity, and pre-registered availability geometry. The final encrypted evidence envelope was independently decrypted and every private-manifest file was verified.

This public directory contains no target identity, injection center, event time, SNR, p-value, q-value, or target-level recovery result. It contains only aggregate sensitivity values and cryptographic commitments. No astronomical discovery claim is made.
