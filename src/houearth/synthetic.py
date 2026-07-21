from __future__ import annotations

import numpy as np

from .core import LightCurve


def inject_box_transit(
    time: np.ndarray,
    flux: np.ndarray,
    *,
    period: float,
    duration: float,
    depth: float,
    epoch: float,
) -> np.ndarray:
    if period <= 0 or duration <= 0 or depth <= 0:
        raise ValueError("period, duration, and depth must be positive")
    phase_distance = np.abs(((time - epoch + 0.5 * period) % period) - 0.5 * period)
    injected = np.array(flux, dtype=float, copy=True)
    injected[phase_distance <= duration / 2] -= depth
    return injected


def inject_single_transit(
    time: np.ndarray,
    flux: np.ndarray,
    *,
    center: float,
    duration: float,
    depth: float,
) -> np.ndarray:
    injected = np.array(flux, dtype=float, copy=True)
    injected[np.abs(time - center) <= duration / 2] -= depth
    return injected


def make_synthetic_lightcurve(
    *,
    period: float = 7.25,
    duration: float = 0.22,
    depth: float = 0.012,
    epoch: float = 1.15,
    baseline: float = 54.0,
    cadence_minutes: float = 20.0,
    noise: float = 0.0018,
    seed: int = 42,
    add_single_event: bool = True,
) -> LightCurve:
    rng = np.random.default_rng(seed)
    cadence = cadence_minutes / (24 * 60)
    time = np.arange(0, baseline, cadence)

    # Mild stellar variability and white noise imitate a simple TESS-like baseline.
    stellar = 0.0012 * np.sin(2 * np.pi * time / 11.3) + 0.0006 * np.sin(2 * np.pi * time / 3.7)
    flux = 1.0 + stellar + rng.normal(0, noise, size=len(time))
    flux = inject_box_transit(
        time,
        flux,
        period=period,
        duration=duration,
        depth=depth,
        epoch=epoch,
    )

    if add_single_event:
        flux = inject_single_transit(
            time,
            flux,
            center=baseline * 0.83,
            duration=duration * 1.45,
            depth=depth * 0.72,
        )

    return LightCurve(
        time,
        flux,
        np.full_like(time, noise),
        target="synthetic-HOU-0001",
        metadata={
            "injected_period_days": period,
            "injected_duration_days": duration,
            "injected_depth": depth,
            "injected_epoch_days": epoch,
            "single_event_center_days": baseline * 0.83 if add_single_event else None,
        },
    )
