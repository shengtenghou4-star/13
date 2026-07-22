from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class LightCurve:
    """Minimal, archive-agnostic light-curve container.

    Time is measured in days. Flux should be near unity after normalization.
    """

    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray | None = None
    target: str = "unknown"
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        time = np.asarray(self.time, dtype=float)
        flux = np.asarray(self.flux, dtype=float)
        if time.ndim != 1 or flux.ndim != 1 or len(time) != len(flux):
            raise ValueError("time and flux must be one-dimensional arrays of equal length")
        if len(time) < 20:
            raise ValueError("a light curve needs at least 20 cadences")

        err = None if self.flux_err is None else np.asarray(self.flux_err, dtype=float)
        if err is not None and (err.ndim != 1 or len(err) != len(time)):
            raise ValueError("flux_err must match time and flux")

        finite = np.isfinite(time) & np.isfinite(flux)
        if err is not None:
            finite &= np.isfinite(err) & (err > 0)
        if finite.sum() < 20:
            raise ValueError("too few finite cadences")

        order = np.argsort(time[finite])
        object.__setattr__(self, "time", time[finite][order])
        object.__setattr__(self, "flux", flux[finite][order])
        if err is not None:
            object.__setattr__(self, "flux_err", err[finite][order])
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @property
    def baseline(self) -> float:
        return float(self.time[-1] - self.time[0])

    @property
    def cadence(self) -> float:
        return float(np.nanmedian(np.diff(self.time)))

    def normalized(self) -> "LightCurve":
        median = float(np.nanmedian(self.flux))
        if not np.isfinite(median) or median == 0:
            raise ValueError("cannot normalize a light curve with zero/invalid median flux")
        err = None if self.flux_err is None else self.flux_err / abs(median)
        return LightCurve(
            self.time,
            self.flux / median,
            err,
            target=self.target,
            metadata={**self.metadata, "normalized": True},
        )

    def sigma_clipped(
        self,
        sigma: float = 8.0,
        *,
        clip_negative: bool = False,
    ) -> "LightCurve":
        """Remove extreme positive artifacts while preserving transit-like dips.

        Transit searches must not discard deep negative excursions merely because a
        bright star has very low scatter. Set ``clip_negative=True`` only for
        non-transit workflows that explicitly want symmetric clipping.
        """
        if sigma <= 0:
            raise ValueError("sigma must be positive")
        med = np.nanmedian(self.flux)
        mad = np.nanmedian(np.abs(self.flux - med))
        robust_sigma = 1.4826 * mad
        if not np.isfinite(robust_sigma) or robust_sigma == 0:
            return self
        delta = self.flux - med
        keep = delta <= sigma * robust_sigma
        if clip_negative:
            keep &= delta >= -sigma * robust_sigma
        if keep.sum() < 20:
            return self
        err = None if self.flux_err is None else self.flux_err[keep]
        return LightCurve(
            self.time[keep],
            self.flux[keep],
            err,
            target=self.target,
            metadata={
                **self.metadata,
                "sigma_clip": sigma,
                "clip_negative": clip_negative,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "cadences": len(self.time),
            "baseline_days": self.baseline,
            "median_cadence_days": self.cadence,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class PeriodicCandidate:
    target: str
    period_days: float
    duration_days: float
    epoch_days: float
    depth: float
    snr: float
    score: float
    estimated_transits: int
    odd_even_depth_ratio: float | None
    secondary_snr: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SingleTransitEvent:
    target: str
    center_time_days: float
    duration_days: float
    depth: float
    snr: float
    local_points: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
