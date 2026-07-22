from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .core import LightCurve, SingleTransitEvent
from .search import search_single_transits


GAP_AWARE_METHOD = "gap-aware-circular-moving-block-bootstrap"
DEFAULT_GAP_FACTOR = 3.5


@dataclass(frozen=True)
class SurrogateTrial:
    target: str
    sector_label: str
    seed: int
    method: str
    block_days: float
    contiguous_segments: int
    gap_factor: float
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
    minimum_segments: int
    maximum_segments: int
    gap_factor: float
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
    gap_factor: float = DEFAULT_GAP_FACTOR,
) -> list[slice]:
    """Return non-empty observing segments separated by large cadence gaps."""
    if gap_factor <= 1.0:
        raise ValueError("gap_factor must be greater than 1")
    time = np.asarray(time, dtype=float)
    if len(time) == 0:
        return []
    breaks = np.flatnonzero(np.diff(time) > gap_factor * cadence) + 1
    starts = np.concatenate([[0], breaks])
    stops = np.concatenate([breaks, [len(time)]])
    return [
        slice(int(start), int(stop))
        for start, stop in zip(starts, stops)
        if stop > start
    ]


def _segment_normalized_residuals(
    lc: LightCurve,
    segments: Sequence[slice],
) -> np.ndarray:
    """Normalize each contiguous observing segment independently."""
    residual = np.empty(len(lc.time), dtype=float)
    for segment in segments:
        values = np.asarray(lc.flux[segment], dtype=float)
        baseline = float(np.median(values))
        if not np.isfinite(baseline) or baseline == 0:
            raise ValueError("cannot normalize a segment with zero/invalid median flux")
        residual[segment] = values / baseline - 1.0
    return residual


def _neutralize_event_windows(
    time: np.ndarray,
    residual: np.ndarray,
    events: Sequence[SingleTransitEvent],
    *,
    cadence: float,
    segments: Sequence[slice],
    padding: float = 1.5,
) -> tuple[np.ndarray, int]:
    """Interpolate event windows only within their contiguous observing segment.

    The interpolation never uses samples across a TESS downlink or quality gap. This
    prevents an event close to a segment boundary from borrowing an unrelated baseline
    from the next observing segment.
    """
    if padding <= 0:
        raise ValueError("padding must be positive")
    cleaned = np.array(residual, dtype=float, copy=True)
    replaced = 0

    for segment in segments:
        segment_time = np.asarray(time[segment], dtype=float)
        segment_values = np.asarray(cleaned[segment], dtype=float)
        mask = np.zeros(len(segment_values), dtype=bool)
        for event in events:
            duration = max(float(event.duration_days), 2.0 * cadence)
            half_width = 0.5 * padding * duration
            mask |= (
                np.abs(segment_time - float(event.center_time_days)) <= half_width
            )
        if not np.any(mask):
            continue

        valid = (~mask) & np.isfinite(segment_values) & np.isfinite(segment_time)
        if np.count_nonzero(valid) < 2:
            raise RuntimeError(
                "Too few unmasked cadences within a contiguous segment to neutralize "
                "detected events"
            )
        segment_values[mask] = np.interp(
            segment_time[mask], segment_time[valid], segment_values[valid]
        )
        cleaned[segment] = segment_values
        replaced += int(np.count_nonzero(mask))

    return cleaned, replaced


def _circular_moving_block_indices(
    length: int,
    *,
    block_points: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw circular overlapping-block indices for one contiguous segment."""
    if length <= 0:
        return np.array([], dtype=int)
    width = min(max(1, int(block_points)), length)
    block_count = int(math.ceil(length / width))
    starts = rng.integers(0, length, size=block_count)
    offsets = np.arange(width)
    indices = (starts[:, None] + offsets[None, :]) % length
    return indices.reshape(-1)[:length]


def _circular_moving_block_bootstrap(
    values: np.ndarray,
    *,
    block_points: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Resample circular overlapping blocks to preserve short-range covariance."""
    values = np.asarray(values, dtype=float)
    indices = _circular_moving_block_indices(
        len(values), block_points=block_points, rng=rng
    )
    return values[indices]


def block_permuted_surrogate(
    lc: LightCurve,
    *,
    block_days: float = 0.5,
    seed: int = 0,
    excluded_events: Sequence[SingleTransitEvent] = (),
    gap_factor: float = DEFAULT_GAP_FACTOR,
) -> LightCurve:
    """Create a gap-aware moving-block bootstrap null light curve.

    Timestamps and observing gaps remain fixed. Residuals and their corresponding
    uncertainties are resampled with identical indices *within* each contiguous
    observing segment; no block may cross a downlink or quality gap. Residual signs are
    never flipped, so flare/dimming asymmetry is not artificially symmetrized.
    """
    if block_days <= 0:
        raise ValueError("block_days must be positive")
    if gap_factor <= 1.0:
        raise ValueError("gap_factor must be greater than 1")

    cadence = lc.cadence
    segments = _contiguous_segments(lc.time, cadence, gap_factor)
    if not segments:
        raise RuntimeError("no contiguous observing segments available")

    residual = _segment_normalized_residuals(lc, segments)
    residual, neutralized_points = _neutralize_event_windows(
        lc.time,
        residual,
        excluded_events,
        cadence=cadence,
        segments=segments,
    )

    output = np.empty_like(residual)
    output_err = None if lc.flux_err is None else np.empty_like(lc.flux_err)
    rng = np.random.default_rng(seed)
    block_points = max(1, int(round(block_days / cadence)))

    for segment in segments:
        segment_length = segment.stop - segment.start
        indices = _circular_moving_block_indices(
            segment_length,
            block_points=block_points,
            rng=rng,
        )
        output[segment] = residual[segment][indices]
        if output_err is not None:
            output_err[segment] = lc.flux_err[segment][indices]

    return LightCurve(
        lc.time,
        1.0 + output,
        output_err,
        target=lc.target,
        metadata={
            **lc.metadata,
            "surrogate": GAP_AWARE_METHOD,
            "surrogate_seed": seed,
            "surrogate_block_days": block_days,
            "surrogate_gap_factor": gap_factor,
            "surrogate_contiguous_segments": len(segments),
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
    gap_factor: float = DEFAULT_GAP_FACTOR,
) -> tuple[list[SurrogateTrial], SurrogateSummary]:
    """Measure empirical no-injection extrema without conditioning on detections.

    Every surrogate is searched with an effectively zero probe threshold so its true
    maximum statistic enters the empirical distribution. The operational ``min_snr``
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
            gap_factor=gap_factor,
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
        segment_count = int(
            surrogate.metadata.get("surrogate_contiguous_segments", 0)
        )
        recorded_gap_factor = float(
            surrogate.metadata.get("surrogate_gap_factor", gap_factor)
        )
        trials.append(
            SurrogateTrial(
                target=lc.target,
                sector_label=_sector_label(lc),
                seed=int(seed_value),
                method=GAP_AWARE_METHOD,
                block_days=block_days,
                contiguous_segments=segment_count,
                gap_factor=recorded_gap_factor,
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
    brightening_exceedances = sum(
        trial.exceeded_brightening_threshold for trial in trials
    )
    segment_counts = [trial.contiguous_segments for trial in trials]

    summary = SurrogateSummary(
        target=lc.target,
        sector_label=_sector_label(lc),
        trials=len(trials),
        detection_threshold=min_snr,
        minimum_segments=min(segment_counts),
        maximum_segments=max(segment_counts),
        gap_factor=gap_factor,
        neutralized_events=len(excluded_events),
        neutralized_points=max(trial.neutralized_points for trial in trials),
        trials_with_dimming_events=dimming_exceedances,
        trials_with_brightening_events=brightening_exceedances,
        dimming_false_alarm_rate=dimming_exceedances / len(trials),
        brightening_false_alarm_rate=brightening_exceedances / len(trials),
        median_maximum_dimming_snr=_quantile(dimming_maxima, 0.50),
        p90_maximum_dimming_snr=_quantile(dimming_maxima, 0.90),
        p95_maximum_dimming_snr=_quantile(dimming_maxima, 0.95),
        maximum_dimming_snr=(
            None if not dimming_maxima else float(max(dimming_maxima))
        ),
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
