from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np

from .real_evaluation import RealInjectionTrial, wilson_interval


@dataclass(frozen=True)
class PooledCompletenessCell:
    depth: float
    duration_days: float
    targets: int
    trials: int
    recovered: int
    completeness: float
    confidence_low: float
    confidence_high: float
    median_recovered_snr: float | None
    median_timing_error_days: float | None
    median_snr_above_control: float | None
    mean_novel_competing_events: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def pool_real_trials(trials: Iterable[RealInjectionTrial]) -> list[PooledCompletenessCell]:
    """Pool equal depth-duration cells while retaining the number of targets."""
    grouped: dict[tuple[float, float], list[RealInjectionTrial]] = {}
    for trial in trials:
        grouped.setdefault((trial.depth, trial.duration_days), []).append(trial)

    cells: list[PooledCompletenessCell] = []
    for (depth, duration), group in sorted(grouped.items()):
        recovered = [trial for trial in group if trial.recovered]
        low, high = wilson_interval(len(recovered), len(group))
        snrs = [trial.recovered_snr for trial in recovered if trial.recovered_snr is not None]
        timing = [
            trial.timing_error_days
            for trial in recovered
            if trial.timing_error_days is not None
        ]
        margins = [
            trial.snr_above_control
            for trial in recovered
            if trial.snr_above_control is not None
        ]
        cells.append(
            PooledCompletenessCell(
                depth=depth,
                duration_days=duration,
                targets=len({(trial.target, trial.sector_label) for trial in group}),
                trials=len(group),
                recovered=len(recovered),
                completeness=len(recovered) / len(group),
                confidence_low=low,
                confidence_high=high,
                median_recovered_snr=None if not snrs else float(np.median(snrs)),
                median_timing_error_days=None if not timing else float(np.median(timing)),
                median_snr_above_control=(
                    None if not margins else float(np.median(margins))
                ),
                mean_novel_competing_events=float(
                    np.mean([trial.novel_competing_events for trial in group])
                ),
            )
        )
    return cells
