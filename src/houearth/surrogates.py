from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from .core import LightCurve
from .search import search_single_transits


@dataclass(frozen=True)
class SurrogateTrial:
    target: str
    sector_label: str
    seed: int
    block_days: float
    dimming_events: int
    brightening_events: int
    maximum_dimming_snr: float | None
    maximum_brightening_snr: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SurrogateSummary:
    target: str
    sector_label: str
    trials: int
    trials_with_dimming_events: int
    trials_with_brightening_events: int
    median_maximum_dimming_snr: float | None
    p95_maximum_dimming_snr: float | None
    p99_maximum_dimming_snr: float | None
    median_maximum_brightening_snr: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sector_label(lc: LightCurve) -> str:
    sectors = lc.metadata.get("sectors", [])
    if isinstance(sectors, (list, tuple)) and sectors:
        return ";".join(str(int(value)) for value in sectors)
    return "unknown"


def _contiguous_segments(time: np.ndarray, cadence: float, gap_factor: float = 3.5) -> list[slice]:
    breaks = np.flatnonzero(np.diff(time) > gap_factor * cadence) + 1
    starts = np.concatenate([[0], breaks])
    stops = np.concatenate([breaks, [len(time)]])
    return [slice(int(start), int(stop)) for start, stop in zip(starts, stops) if stop - start >= 4]


def block_permuted_surrogate(
    lc: LightCurve,
    *,
    block_days: float = 0.5,
    seed: int = 0,
) -> LightCurve:
    """Create a null curve while preserving short-range correlated structure.

    Residual blocks are permuted and independently sign-flipped inside each
    contiguous observing segment. Timestamps, gaps, uncertainties, and the local
    covariance inside each block remain intact, while coherent event phase is broken.
    """
    if block_days <= 0:
        raise ValueError("block_days must be positive")
    normalized = lc.normalized()
    residual = normalized.flux - 1.0
    output = np.empty_like(residual)
    rng = np.random.default_rng(seed)
    block_points = max(4, int(round(block_days / normalized.cadence)))

    for segment in _contiguous_segments(normalized.time, normalized.cadence):
        values = residual[segment]
        blocks = [values[start : start + block_points] for start in range(0, len(values), block_points)]
        order = rng.permutation(len(blocks))
        rebuilt: list[np.ndarray] = []
        for index in order:
            block = np.array(blocks[int(index)], copy=True)
            if rng.random() < 0.5:
                block *= -1.0
            rebuilt.append(block)
        joined = np.concatenate(rebuilt)[: len(values)]
        output[segment] = joined

    covered = np.zeros(len(output), dtype=bool)
    for segment in _contiguous_segments(normalized.time, normalized.cadence):
        covered[segment] = True
    output[~covered] = residual[~covered]
    return LightCurve(
        normalized.time,
        1.0 + output,
        normalized.flux_err,
        target=normalized.target,
        metadata={
            **normalized.metadata,
            "surrogate": "block-permutation-sign-flip",
            "surrogate_seed": seed,
            "surrogate_block_days": block_days,
        },
    )


def run_surrogate_null_campaign(
    lc: LightCurve,
    *,
    seeds: Iterable[int] = range(16),
    block_days: float = 0.5,
    durations: tuple[float, ...] = (0.04, 0.08, 0.16),
    min_snr: float = 5.0,
    flatten_window_days: float = 1.5,
) -> tuple[list[SurrogateTrial], SurrogateSummary]:
    trials: list[SurrogateTrial] = []
    for seed_value in seeds:
        surrogate = block_permuted_surrogate(lc, block_days=block_days, seed=int(seed_value))
        dimming = search_single_transits(
            surrogate,
            durations=durations,
            min_snr=min_snr,
            flatten_window_days=flatten_window_days,
            max_events=200,
            direction="dimming",
        )
        brightening = search_single_transits(
            surrogate,
            durations=durations,
            min_snr=min_snr,
            flatten_window_days=flatten_window_days,
            max_events=200,
            direction="brightening",
        )
        trials.append(
            SurrogateTrial(
                target=lc.target,
                sector_label=_sector_label(lc),
                seed=int(seed_value),
                block_days=block_days,
                dimming_events=len(dimming),
                brightening_events=len(brightening),
                maximum_dimming_snr=max((event.snr for event in dimming), default=None),
                maximum_brightening_snr=max((event.snr for event in brightening), default=None),
            )
        )

    dimming_maxima = [trial.maximum_dimming_snr for trial in trials if trial.maximum_dimming_snr is not None]
    brightening_maxima = [
        trial.maximum_brightening_snr for trial in trials if trial.maximum_brightening_snr is not None
    ]
    summary = SurrogateSummary(
        target=lc.target,
        sector_label=_sector_label(lc),
        trials=len(trials),
        trials_with_dimming_events=sum(trial.dimming_events > 0 for trial in trials),
        trials_with_brightening_events=sum(trial.brightening_events > 0 for trial in trials),
        median_maximum_dimming_snr=(
            None if not dimming_maxima else float(np.median(dimming_maxima))
        ),
        p95_maximum_dimming_snr=(
            None if not dimming_maxima else float(np.quantile(dimming_maxima, 0.95))
        ),
        p99_maximum_dimming_snr=(
            None if not dimming_maxima else float(np.quantile(dimming_maxima, 0.99))
        ),
        median_maximum_brightening_snr=(
            None if not brightening_maxima else float(np.median(brightening_maxima))
        ),
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
