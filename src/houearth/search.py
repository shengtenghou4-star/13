from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .core import LightCurve, PeriodicCandidate, SingleTransitEvent
from .preprocess import flatten_lightcurve


@dataclass(frozen=True)
class _PeriodTrial:
    period: float
    duration: float
    epoch: float
    depth: float
    snr: float


def _robust_sigma(values: np.ndarray) -> float:
    med = np.nanmedian(values)
    mad = np.nanmedian(np.abs(values - med))
    sigma = 1.4826 * mad
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = float(np.nanstd(values))
    return max(float(sigma), 1e-10)


def _best_window_for_period(
    time: np.ndarray,
    flux: np.ndarray,
    period: float,
    duration: float,
    noise_sigma: float,
) -> _PeriodTrial | None:
    phase = np.mod(time, period)
    order = np.argsort(phase)
    p = phase[order]
    f = flux[order]
    n = len(f)

    # Duplicate one cycle so windows crossing phase zero are handled naturally.
    p2 = np.concatenate([p, p + period])
    f2 = np.concatenate([f, f])
    csum = np.concatenate([[0.0], np.cumsum(f2)])

    best_mean = math.inf
    best_left = 0
    best_right = 0
    right = 0
    min_points = max(3, int(0.25 * duration / max(np.nanmedian(np.diff(time)), 1e-8)))

    for left in range(n):
        right = max(right, left + 1)
        while right < left + n and p2[right] - p2[left] <= duration:
            right += 1
        count = right - left
        if count < min_points:
            continue
        mean_flux = (csum[right] - csum[left]) / count
        if mean_flux < best_mean:
            best_mean = float(mean_flux)
            best_left = left
            best_right = right

    count = best_right - best_left
    if count < min_points or not np.isfinite(best_mean):
        return None

    baseline = float(np.nanmedian(flux))
    depth = max(0.0, baseline - best_mean)
    snr = depth / noise_sigma * math.sqrt(count)
    center_phase = (p2[best_left] + p2[best_right - 1]) / 2
    center_phase %= period
    epoch = float(time[0] + ((center_phase - time[0]) % period))
    return _PeriodTrial(period, duration, epoch, depth, snr)


def _depth_near_phase(
    lc: LightCurve,
    period: float,
    epoch: float,
    duration: float,
    phase_offset: float = 0.0,
) -> tuple[float, float, int]:
    center = epoch + phase_offset * period
    distance = np.abs(((lc.time - center + 0.5 * period) % period) - 0.5 * period)
    inside = distance <= duration / 2
    outside = distance >= duration
    if inside.sum() < 2 or outside.sum() < 5:
        return 0.0, 0.0, int(inside.sum())
    depth = float(np.nanmedian(lc.flux[outside]) - np.nanmean(lc.flux[inside]))
    sigma = _robust_sigma(lc.flux[outside])
    snr = depth / sigma * math.sqrt(int(inside.sum()))
    return depth, snr, int(inside.sum())


def _odd_even_ratio(lc: LightCurve, trial: _PeriodTrial) -> float | None:
    transit_number = np.rint((lc.time - trial.epoch) / trial.period).astype(int)
    distance = np.abs(
        lc.time - (trial.epoch + transit_number * trial.period)
    )
    inside = distance <= trial.duration / 2
    odd = inside & (np.abs(transit_number) % 2 == 1)
    even = inside & (np.abs(transit_number) % 2 == 0)
    if odd.sum() < 2 or even.sum() < 2:
        return None
    baseline = float(np.nanmedian(lc.flux[~inside])) if (~inside).sum() else 1.0
    odd_depth = baseline - float(np.nanmean(lc.flux[odd]))
    even_depth = baseline - float(np.nanmean(lc.flux[even]))
    if odd_depth <= 0 or even_depth <= 0:
        return None
    return float(max(odd_depth, even_depth) / min(odd_depth, even_depth))


def search_periodic_transits(
    lc: LightCurve,
    *,
    min_period: float = 1.0,
    max_period: float | None = None,
    durations: tuple[float, ...] = (0.08, 0.12, 0.18, 0.25, 0.35),
    period_steps: int = 700,
    flatten_window_days: float = 1.5,
) -> PeriodicCandidate:
    """Search for periodic box-like dimming signals.

    This dependency-light implementation is intended as an auditable baseline.
    Later research phases can compare it against Astropy BLS and neural models.
    """
    if max_period is None:
        max_period = min(30.0, max(2.0, lc.baseline / 2))
    if not (0 < min_period < max_period):
        raise ValueError("require 0 < min_period < max_period")
    if period_steps < 50:
        raise ValueError("period_steps must be at least 50")

    clean = flatten_lightcurve(lc.normalized().sigma_clipped(), flatten_window_days)
    noise = _robust_sigma(clean.flux)
    periods = np.geomspace(min_period, max_period, period_steps)

    best: _PeriodTrial | None = None
    for period in periods:
        for duration in durations:
            if duration >= 0.25 * period:
                continue
            trial = _best_window_for_period(
                clean.time, clean.flux, float(period), float(duration), noise
            )
            if trial is not None and (best is None or trial.snr > best.snr):
                best = trial

    if best is None:
        raise RuntimeError("no valid transit trial could be evaluated")

    odd_even = _odd_even_ratio(clean, best)
    _, secondary_snr, _ = _depth_near_phase(
        clean, best.period, best.epoch, best.duration, phase_offset=0.5
    )
    estimated_transits = max(1, int(math.floor(clean.baseline / best.period)) + 1)

    # The score is intentionally transparent and conservative.
    odd_penalty = 1.0 if odd_even is None else max(0.2, 1.0 / odd_even)
    secondary_penalty = 1.0 / (1.0 + max(0.0, secondary_snr - 3.0))
    score = float(best.snr * odd_penalty * secondary_penalty)

    return PeriodicCandidate(
        target=lc.target,
        period_days=float(best.period),
        duration_days=float(best.duration),
        epoch_days=float(best.epoch),
        depth=float(best.depth),
        snr=float(best.snr),
        score=score,
        estimated_transits=estimated_transits,
        odd_even_depth_ratio=odd_even,
        secondary_snr=float(secondary_snr),
    )


def search_single_transits(
    lc: LightCurve,
    *,
    durations: tuple[float, ...] = (0.12, 0.18, 0.25, 0.35, 0.5),
    flatten_window_days: float = 1.5,
    min_snr: float = 5.0,
    max_events: int = 20,
) -> list[SingleTransitEvent]:
    """Find isolated box-like dimming events without assuming a period."""
    clean = flatten_lightcurve(lc.normalized().sigma_clipped(), flatten_window_days)
    flux = clean.flux
    baseline = float(np.nanmedian(flux))
    noise = _robust_sigma(flux)
    cadence = clean.cadence
    candidates: list[SingleTransitEvent] = []

    for duration in durations:
        width = max(3, int(round(duration / cadence)))
        kernel = np.ones(width, dtype=float) / width
        local_mean = np.convolve(flux, kernel, mode="same")
        depth = baseline - local_mean
        snr = depth / noise * math.sqrt(width)

        half = width // 2
        for idx in range(half, len(flux) - half):
            if snr[idx] < min_snr:
                continue
            neighborhood = snr[max(0, idx - width) : min(len(snr), idx + width + 1)]
            if snr[idx] < np.nanmax(neighborhood):
                continue
            candidates.append(
                SingleTransitEvent(
                    target=lc.target,
                    center_time_days=float(clean.time[idx]),
                    duration_days=float(duration),
                    depth=float(depth[idx]),
                    snr=float(snr[idx]),
                    local_points=width,
                )
            )

    candidates.sort(key=lambda event: event.snr, reverse=True)
    deduplicated: list[SingleTransitEvent] = []
    for event in candidates:
        if any(
            abs(event.center_time_days - kept.center_time_days)
            <= 0.5 * max(event.duration_days, kept.duration_days)
            for kept in deduplicated
        ):
            continue
        deduplicated.append(event)
        if len(deduplicated) >= max_events:
            break
    return deduplicated
