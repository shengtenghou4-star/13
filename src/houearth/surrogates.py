from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .core import LightCurve, SingleTransitEvent
from .search import search_single_transits


@dataclass(frozen=True)
class SurrogateTrial:
    target: str
    sector_label: str
    seed: int
    method: str
    block_days: float
    neutralized_events: int
    neutralized_points: int
    dimming_events: int
    brightening_events: int
    maximum_dimming_snr: float | None
    maximum_brightening_snr: float | None
    exceeded_dimming_threshold: bool
    exceeded_brightening_threshold: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SurrogateSummary:
    target: str
    sector_label: str
    trials: int
    detection_threshold: float
    neutralized_events: int
    neutralized_points: int
    trials_with_dimming_events: int
    trials_with_brightening_events: int
    dimming_false_alarm_rate: float
    brightening_false_alarm_rate: float
    median_maximum_dimming_snr: float | None
    p90_maximum_dimming_snr: float | None
    p95_maximum_dimming_snr: float | None
    maximum_dimming_snr: float | None
    median_maximum_brightening_snr: float | None
    p95_maximum_brightening_snr: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sector_label(lc: LightCurve) -> str:
    sectors = lc.metadata.get("sectors", [])
    if isinstance(sectors, (list, tuple)) and sectors:
        return ";".join(str(int(value)) for value in sectors)
    return "unknown"


def _contiguous_segments(
    time: np.ndarray,
    cadence: float,
    gap_factor: float = 3.5,
) -> list[slice]:
    breaks = np.flatnonzero(np.diff(time) > gap_factor * cadence) + 1
    starts = np.concatenate([[0], breaks])
    stops = np.concatenate([breaks, [len(time)]])
    return [
        slice(int(start), int(stop))
        for start, stop in zip(starts, stops)
        if stop - start >= 4
    ]


def _neutralize_event_windows(
    time: np.ndarray,
    residual: np.ndarray,
    events: Sequence[SingleTransitEvent],
    *,
    cadence: float,
    padding: float = 1.5,
) -> tuple[np.ndarray, int]:
    """Interpolate over detected excursions before constructing null surrogates.

    Known or pre-detected dimming and brightening events are not valid samples of the
    no-event background.  They are removed non-destructively with interpolation over
    the surrounding observed residuals.  The number of replaced cadences is retained
    in the evidence record.
    """
    if padding <= 0:
        raise ValueError("padding must be positive")
    cleaned = np.array(residual, dtype=float, copy=True)
    mask = np.zeros(len(cleaned), dtype=bool)
    for event in events:
        duration = max(float(event.duration_days), 2.0 * cadence)
        half_width = 0.5 * padding * duration
        mask |= np.abs(time - float(event.center_time_days)) <= half_width
    if not np.any(mask):
        return cleaned, 0

    valid = (~mask) & np.isfinite(cleaned) & np.isfinite(time)
    if np.count_nonzero(valid) < 2:
        raise RuntimeError("Too few unmasked cadences to neutralize detected events")
    cleaned[mask] = np.interp(time[mask], time[valid], cleaned[valid])
    return cleaned, int(np.count_nonzero(mask))


def _circular_moving_block_bootstrap(
    values: np.ndarray,
    *,
    block_points: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Resample circular overlapping blocks to preserve short-range covariance."""
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return values.copy()
    width = min(max(4, int(block_points)), len(values))
    block_count = int(math.ceil(len(values) / width))
    starts = rng.integers(0, len(values), size=block_count)
    offsets = np.arange(width)
    indices = (starts[:, None] + offsets[None, :]) % len(values)
    return values[indices].reshape(-1)[: len(values)]


def block_permuted_surrogate(
    lc: LightCurve,
    *,
    block_days: float = 0.5,
    seed: int = 0,
    excluded_events: Sequence[SingleTransitEvent] = (),
) -> LightCurve:
    """Create an event-neutralized moving-block bootstrap null light curve.

    Timestamps, observing gaps, uncertainties, and short-range residual covariance are
    retained.  Detected astrophysical or instrumental excursions are interpolated out
    before circular overlapping blocks are sampled with replacement.  Unlike the
    earlier pilot implementation, residual signs are not flipped, so flare/dimming
    asymmetry and the one-point residual distribution are not artificially symmetrized.
    """
    if block_days <= 0:
        raise ValueError("block_days must be positive")
    normalized = lc.normalized()
    residual = normalized.flux - 1.0
    residual, neutralized_points = _neutralize_event_windows(
        normalized.time,
        residual,
        excluded_events,
        cadence=normalized.cadence,
    )
    output = np.array(residual, copy=True)
    rng = np.random.default_rng(seed)
    block_points = max(4, int(round(block_days / normalized.cadence)))

    segments = _contiguous_segments(normalized.time, normalized.cadence)
    covered = np.zeros(len(output), dtype=bool)
    for segment in segments:
        covered[segment] = True
        output[segment] = _circular_moving_block_bootstrap(
            residual[segment],
            block_points=block_points,
            rng=rng,
        )
    output[~covered] = residual[~covered]

    return LightCurve(
        normalized.time,
        1.0 + output,
        normalized.flux_err,
        target=normalized.target,
        metadata={
            **normalized.metadata,
            "surrogate": "event-neutralized-circular-moving-block-bootstrap",
            "surrogate_seed": seed,
            "surrogate_block_days": block_days,
            "surrogate_neutralized_events": len(excluded_events),
            "surrogate_neutralized_points": neutralized_points,
        },
    )


def _quantile(values: list[float], probability: float) -> float | None:
    return None if not values else float(np.quantile(values, probability))


def run_surrogate_null_campaign(
    lc: LightCurve,
    *,
    seeds: Iterable[int] = range(32),
    block_days: float = 0.5,
    durations: tuple[float, ...] = (0.04, 0.08, 0.16),
    min_snr: float = 5.0,
    flatten_window_days: float = 1.5,
    excluded_events: Sequence[SingleTransitEvent] = (),
) -> tuple[list[SurrogateTrial], SurrogateSummary]:
    """Measure empirical no-injection extrema without conditioning on detections.

    Every surrogate is searched with an effectively zero probe threshold so its true
    maximum statistic enters the empirical distribution.  The operational ``min_snr``
    threshold is applied afterwards when false-alarm exceedances are counted.
    """
    if min_snr <= 0:
        raise ValueError("min_snr must be positive")
    trials: list[SurrogateTrial] = []
    probe_snr = 1e-6
    for seed_value in seeds:
        surrogate = block_permuted_surrogate(
            lc,
            block_days=block_days,
            seed=int(seed_value),
            excluded_events=excluded_events,
        )
        dimming_all = search_single_transits(
            surrogate,
            durations=durations,
            min_snr=probe_snr,
            flatten_window_days=flatten_window_days,
            max_events=200,
            direction="dimming",
        )
        brightening_all = search_single_transits(
            surrogate,
            durations=durations,
            min_snr=probe_snr,
            flatten_window_days=flatten_window_days,
            max_events=200,
            direction="brightening",
        )
        maximum_dimming = max((event.snr for event in dimming_all), default=None)
        maximum_brightening = max((event.snr for event in brightening_all), default=None)
        dimming_events = sum(event.snr >= min_snr for event in dimming_all)
        brightening_events = sum(event.snr >= min_snr for event in brightening_all)
        trials.append(
            SurrogateTrial(
                target=lc.target,
                sector_label=_sector_label(lc),
                seed=int(seed_value),
                method="event-neutralized-circular-moving-block-bootstrap",
                block_days=block_days,
                neutralized_events=len(excluded_events),
                neutralized_points=int(
                    surrogate.metadata.get("surrogate_neutralized_points", 0)
                ),
                dimming_events=dimming_events,
                brightening_events=brightening_events,
                maximum_dimming_snr=(
                    None if maximum_dimming is None else float(maximum_dimming)
                ),
                maximum_brightening_snr=(
                    None if maximum_brightening is None else float(maximum_brightening)
                ),
                exceeded_dimming_threshold=(
                    maximum_dimming is not None and maximum_dimming >= min_snr
                ),
                exceeded_brightening_threshold=(
                    maximum_brightening is not None and maximum_brightening >= min_snr
                ),
            )
        )

    if not trials:
        raise ValueError("at least one surrogate seed is required")
    dimming_maxima = [
        float(trial.maximum_dimming_snr)
        for trial in trials
        if trial.maximum_dimming_snr is not None
    ]
    brightening_maxima = [
        float(trial.maximum_brightening_snr)
        for trial in trials
        if trial.maximum_brightening_snr is not None
    ]
    dimming_exceedances = sum(trial.exceeded_dimming_threshold for trial in trials)
    brightening_exceedances = sum(trial.exceeded_brightening_threshold for trial in trials)
    summary = SurrogateSummary(
        target=lc.target,
        sector_label=_sector_label(lc),
        trials=len(trials),
        detection_threshold=min_snr,
        neutralized_events=len(excluded_events),
        neutralized_points=max(trial.neutralized_points for trial in trials),
        trials_with_dimming_events=dimming_exceedances,
        trials_with_brightening_events=brightening_exceedances,
        dimming_false_alarm_rate=dimming_exceedances / len(trials),
        brightening_false_alarm_rate=brightening_exceedances / len(trials),
        median_maximum_dimming_snr=_quantile(dimming_maxima, 0.50),
        p90_maximum_dimming_snr=_quantile(dimming_maxima, 0.90),
        p95_maximum_dimming_snr=_quantile(dimming_maxima, 0.95),
        maximum_dimming_snr=None if not dimming_maxima else float(max(dimming_maxima)),
        median_maximum_brightening_snr=_quantile(brightening_maxima, 0.50),
        p95_maximum_brightening_snr=_quantile(brightening_maxima, 0.95),
    )
    return trials, summary


def write_surrogate_outputs(
    trials: list[SurrogateTrial],
    summary: SurrogateSummary,
    output_dir: str | Path,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "surrogate_trials.json").write_text(
        json.dumps([trial.to_dict() for trial in trials], indent=2), encoding="utf-8"
    )
    (output / "surrogate_summary.json").write_text(
        json.dumps(summary.to_dict(), indent=2), encoding="utf-8"
    )
