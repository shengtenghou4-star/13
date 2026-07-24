from __future__ import annotations

import math

import numpy as np

from .candidate_campaign import (
    PHASE09_FLATTEN_WINDOW_DAYS,
    PHASE09_MINIMUM_SEARCH_SNR,
    PHASE09_SEARCH_DURATION_FAMILY_DAYS,
    PHASE09_SURROGATE_BLOCK_DAYS,
)
from .core import LightCurve
from .phase14_power_restore import (
    PHASE14_EXTENSION_SEEDS,
    PHASE14_PROBE_SNR,
    PHASE14_SEARCH_DIRECTION,
    PHASE14_TRIAL_SCHEMA,
    Phase14PowerError,
    Phase14SurrogateMaximum,
)
from .preprocess import flatten_lightcurve
from .provenance import canonical_json_sha256
from .search import _robust_sigma
from .surrogates import (
    DEFAULT_GAP_FACTOR,
    GAP_AWARE_METHOD,
    block_permuted_surrogate,
)


def maximum_single_transit_snr(
    lightcurve: LightCurve,
    *,
    durations: tuple[float, ...],
    flatten_window_days: float,
    min_snr: float,
    direction: str = "dimming",
) -> float | None:
    """Return the exact winning SNR without materializing losing event objects.

    For one duration, ``search_single_transits(..., max_events=1)`` sorts every
    qualifying local maximum by descending SNR and retains the first one. This
    function performs the same SNR arithmetic and local-maximum test, but scans
    candidate indices in descending SNR order and stops at the first qualifying
    index. Deduplication cannot alter the first event, so the returned maximum is
    identical while non-winning ``SingleTransitEvent`` objects are never created.
    """

    if direction not in {"dimming", "brightening"}:
        raise ValueError("direction must be 'dimming' or 'brightening'")
    if min_snr <= 0:
        raise ValueError("min_snr must be positive")
    if any(duration <= 0 for duration in durations):
        raise ValueError("durations must be positive")

    normalized = lightcurve.normalized()
    if direction == "dimming":
        clipped = normalized.sigma_clipped(
            clip_positive=True, clip_negative=False
        )
    else:
        clipped = normalized.sigma_clipped(
            clip_positive=False, clip_negative=True
        )
    clean = flatten_lightcurve(clipped, flatten_window_days)
    flux = clean.flux
    baseline = float(np.nanmedian(flux))
    noise = _robust_sigma(flux)
    cadence = clean.cadence
    best: float | None = None

    for duration in durations:
        width = max(3, int(round(duration / cadence)))
        kernel = np.ones(width, dtype=float) / width
        local_mean = np.convolve(flux, kernel, mode="same")
        if direction == "dimming":
            amplitude = baseline - local_mean
        else:
            amplitude = local_mean - baseline
        snr = amplitude / noise * math.sqrt(width)
        half = width // 2

        # Stable sorting is not required for the returned value because tied
        # candidates have the same SNR, but mergesort fixes traversal anyway.
        for index in np.argsort(snr, kind="mergesort")[::-1]:
            idx = int(index)
            value = float(snr[idx])
            if not math.isfinite(value):
                continue
            if value < min_snr:
                break
            if idx < half or idx >= len(snr) - half:
                continue
            neighborhood = snr[
                max(0, idx - width) : min(len(snr), idx + width + 1)
            ]
            if value < float(np.nanmax(neighborhood)):
                continue
            if best is None or value > best:
                best = value
            break

    return best


def run_phase14_dimming_surrogate_trial_maximum_only(
    lightcurve: LightCurve,
    *,
    target_id: str,
    campaign_input_combined_sha256: str,
    seed: int,
) -> Phase14SurrogateMaximum:
    if not isinstance(target_id, str) or not target_id.strip():
        raise Phase14PowerError("target_id must be non-empty")
    recorded = lightcurve.metadata.get("campaign_input_array_hashes", {}).get(
        "combined_sha256"
    )
    if recorded != campaign_input_combined_sha256:
        raise Phase14PowerError(
            "light curve does not match the frozen campaign-input hash"
        )
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed not in PHASE14_EXTENSION_SEEDS
    ):
        raise Phase14PowerError(
            "seed must belong to the frozen Phase 0.14 extension range"
        )

    surrogate = block_permuted_surrogate(
        lightcurve,
        block_days=PHASE09_SURROGATE_BLOCK_DAYS,
        seed=seed,
        excluded_events=(),
        gap_factor=DEFAULT_GAP_FACTOR,
    )
    maximum = maximum_single_transit_snr(
        surrogate,
        durations=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        flatten_window_days=PHASE09_FLATTEN_WINDOW_DAYS,
        min_snr=PHASE14_PROBE_SNR,
        direction=PHASE14_SEARCH_DIRECTION,
    )
    body = {
        "schema": PHASE14_TRIAL_SCHEMA,
        "target_id": target_id,
        "target_name": lightcurve.target,
        "sector_label": ";".join(
            str(int(value)) for value in lightcurve.metadata.get("sectors", [])
        )
        or "unknown",
        "campaign_input_combined_sha256": campaign_input_combined_sha256,
        "seed": seed,
        "method": GAP_AWARE_METHOD,
        "block_days": PHASE09_SURROGATE_BLOCK_DAYS,
        "gap_factor": DEFAULT_GAP_FACTOR,
        "contiguous_segments": int(
            surrogate.metadata["surrogate_contiguous_segments"]
        ),
        "maximum_dimming_snr": maximum,
        "exceeded_dimming_threshold": (
            maximum is not None and maximum >= PHASE09_MINIMUM_SEARCH_SNR
        ),
        "search_direction": PHASE14_SEARCH_DIRECTION,
        "search_duration_family_days": PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        "flatten_window_days": PHASE09_FLATTEN_WINDOW_DAYS,
        "minimum_search_snr": PHASE09_MINIMUM_SEARCH_SNR,
    }
    return Phase14SurrogateMaximum(
        **body, trial_sha256=canonical_json_sha256(body)
    )
