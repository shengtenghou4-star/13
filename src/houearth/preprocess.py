from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter

from .core import LightCurve


def flatten_lightcurve(lc: LightCurve, window_days: float = 1.5) -> LightCurve:
    """Remove slow variability with a robust median filter.

    The window must be comfortably longer than the expected transit duration.
    """
    if window_days <= 5 * lc.cadence:
        raise ValueError("flattening window is too short for the cadence")
    size = max(5, int(round(window_days / lc.cadence)))
    if size % 2 == 0:
        size += 1
    trend = median_filter(lc.flux, size=size, mode="nearest")
    safe = np.where(np.abs(trend) > 1e-12, trend, np.nanmedian(trend))
    flattened = lc.flux / safe
    err = None if lc.flux_err is None else lc.flux_err / np.abs(safe)
    return LightCurve(
        lc.time,
        flattened,
        err,
        target=lc.target,
        metadata={**lc.metadata, "flatten_window_days": window_days},
    ).normalized()
