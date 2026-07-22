from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from statistics import median
from typing import Iterable, Sequence

import numpy as np

from .physical_evaluation import PhysicalInjectionTrial
from .real_evaluation import wilson_interval
from .surrogates import SurrogateTrial


@dataclass(frozen=True)
class SurrogateCalibratedTrial:
    target: str
    sector_label: str
    depth: float
    duration_days: float
    impact_parameter: float
    seed: int
    recovered: bool
    recovered_snr: float | None
    null_trials: int
    minimum_resolvable_p: float
    significance_alpha: float
    empirical_familywise_p: float | None
    null_p95_maximum_snr: float | None
    snr_above_null_p95: float | None
    significant_at_0_05: bool | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SurrogateCalibratedCell:
    target: str
    sector_label: str
    depth: float
    duration_days: float
    impact_parameter: float
    trials: int
    recovered: int
    calibrated_recoveries: int
    significance_alpha: float
    significant_recoveries_0_05: int
    significant_completeness_0_05: float
    significant_confidence_low_0_05: float
    significant_confidence_high_0_05: float
    fraction_of_recoveries_significant_0_05: float | None
    median_empirical_familywise_p: float | None
    median_snr_above_null_p95: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def empirical_familywise_p(
    signal_snr: float,
    null_maximum_snrs: Sequence[float],
) -> float:
    """Conservative finite-sample p-value against full-search null maxima.

    Every null statistic is the maximum over the same searched duration family, so the
    comparison incorporates the within-light-curve look-elsewhere effect. Add-one
    smoothing prevents zero p-values and makes the finite resolution explicit.
    """
    if not null_maximum_snrs:
        raise ValueError("at least one null maximum is required")
    exceedances = sum(float(value) >= float(signal_snr) for value in null_maximum_snrs)
    return (1.0 + exceedances) / (1.0 + len(null_maximum_snrs))


def calibrate_physical_trials(
    physical_trials: Iterable[PhysicalInjectionTrial],
    surrogate_trials: Iterable[SurrogateTrial],
    *,
    alpha: float = 0.05,
) -> list[SurrogateCalibratedTrial]:
    if not math.isclose(alpha, 0.05, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("the Phase 0.7 evidence schema is frozen at alpha=0.05")
    nulls = [
        float(trial.maximum_dimming_snr)
        for trial in surrogate_trials
        if trial.maximum_dimming_snr is not None
    ]
    if not nulls:
        raise ValueError("surrogate trials contain no dimming maxima")
    null_p95 = float(np.quantile(nulls, 0.95))
    resolution = 1.0 / (1.0 + len(nulls))

    rows: list[SurrogateCalibratedTrial] = []
    for trial in physical_trials:
        p_value = None
        margin = None
        significant = None
        if trial.recovered and trial.recovered_snr is not None:
            p_value = empirical_familywise_p(trial.recovered_snr, nulls)
            margin = float(trial.recovered_snr - null_p95)
            significant = p_value <= alpha
        rows.append(
            SurrogateCalibratedTrial(
                target=trial.target,
                sector_label=trial.sector_label,
                depth=trial.depth,
                duration_days=trial.duration_days,
                impact_parameter=trial.impact_parameter,
                seed=trial.seed,
                recovered=trial.recovered,
                recovered_snr=trial.recovered_snr,
                null_trials=len(nulls),
                minimum_resolvable_p=resolution,
                significance_alpha=alpha,
                empirical_familywise_p=p_value,
                null_p95_maximum_snr=null_p95,
                snr_above_null_p95=margin,
                significant_at_0_05=significant,
            )
        )
    return rows


def summarize_surrogate_calibrated_trials(
    rows: Iterable[SurrogateCalibratedTrial],
) -> list[SurrogateCalibratedCell]:
    grouped: dict[
        tuple[str, str, float, float, float],
        list[SurrogateCalibratedTrial],
    ] = defaultdict(list)
    for row in rows:
        key = (
            row.target,
            row.sector_label,
            row.depth,
            row.duration_days,
            row.impact_parameter,
        )
        grouped[key].append(row)

    cells: list[SurrogateCalibratedCell] = []
    for (target, sector, depth, duration, impact), group in sorted(grouped.items()):
        alphas = {row.significance_alpha for row in group}
        if len(alphas) != 1:
            raise ValueError("a calibrated cell cannot mix significance thresholds")
        alpha = next(iter(alphas))
        recovered = [row for row in group if row.recovered]
        calibrated = [
            row for row in recovered if row.empirical_familywise_p is not None
        ]
        significant = [
            row for row in calibrated if row.significant_at_0_05 is True
        ]
        significant_low, significant_high = wilson_interval(
            len(significant), len(group)
        )
        p_values = [
            float(row.empirical_familywise_p)
            for row in calibrated
            if row.empirical_familywise_p is not None
        ]
        margins = [
            float(row.snr_above_null_p95)
            for row in calibrated
            if row.snr_above_null_p95 is not None
        ]
        cells.append(
            SurrogateCalibratedCell(
                target=target,
                sector_label=sector,
                depth=depth,
                duration_days=duration,
                impact_parameter=impact,
                trials=len(group),
                recovered=len(recovered),
                calibrated_recoveries=len(calibrated),
                significance_alpha=alpha,
                significant_recoveries_0_05=len(significant),
                significant_completeness_0_05=len(significant) / len(group),
                significant_confidence_low_0_05=significant_low,
                significant_confidence_high_0_05=significant_high,
                fraction_of_recoveries_significant_0_05=(
                    None if not calibrated else len(significant) / len(calibrated)
                ),
                median_empirical_familywise_p=(
                    None if not p_values else median(p_values)
                ),
                median_snr_above_null_p95=(
                    None if not margins else median(margins)
                ),
            )
        )
    return cells
