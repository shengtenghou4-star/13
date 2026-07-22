from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .core import LightCurve, SingleTransitEvent
from .physical import inject_physical_single_transit
from .real_evaluation import (
    _event_matches,
    _sector_label,
    _valid_injection_windows,
    screen_real_lightcurve,
    wilson_interval,
)
from .search import search_single_transits


@dataclass(frozen=True)
class PhysicalInjectionTrial:
    target: str
    sector_label: str
    depth: float
    duration_days: float
    impact_parameter: float
    radius_ratio: float
    limb_u1: float
    limb_u2: float
    seed: int
    injected_center_days: float
    local_coverage_fraction: float
    recovered: bool
    recovered_center_days: float | None
    recovered_snr: float | None
    timing_error_days: float | None
    matched_control_snr: float | None
    snr_above_matched_control: float | None
    novel_competing_events: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PhysicalCompletenessCell:
    target: str
    sector_label: str
    depth: float
    duration_days: float
    impact_parameter: float
    trials: int
    recovered: int
    completeness: float
    confidence_low: float
    confidence_high: float
    median_recovered_snr: float | None
    median_snr_above_matched_control: float | None
    median_timing_error_days: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _matched_control_snr(
    controls: Sequence[SingleTransitEvent],
    duration_days: float,
) -> float | None:
    if not controls:
        return None
    available = sorted({event.duration_days for event in controls})
    matched_duration = min(available, key=lambda value: abs(value - duration_days))
    values = [event.snr for event in controls if event.duration_days == matched_duration]
    return None if not values else float(max(values))


def run_physical_injection_trial(
    lc: LightCurve,
    *,
    depth: float,
    duration_days: float,
    impact_parameter: float,
    seed: int,
    background_events: Sequence[SingleTransitEvent],
    brightening_controls: Sequence[SingleTransitEvent],
    search_durations: tuple[float, ...],
    flatten_window_days: float,
    min_snr: float,
    limb_u1: float,
    limb_u2: float,
) -> PhysicalInjectionTrial:
    normalized = lc.normalized()
    excluded_events = [*background_events, *brightening_controls]
    windows = _valid_injection_windows(
        normalized,
        duration_days=duration_days,
        excluded_events=excluded_events,
    )
    if not windows:
        raise RuntimeError(
            f"No valid physical-transit window for {lc.target!r} at {duration_days} days"
        )

    rng = np.random.default_rng(seed)
    center, coverage = windows[int(rng.integers(0, len(windows)))]
    flux, radius_ratio = inject_physical_single_transit(
        normalized.time,
        normalized.flux,
        center=center,
        duration=duration_days,
        depth=depth,
        impact_parameter=impact_parameter,
        u1=limb_u1,
        u2=limb_u2,
    )
    injected = LightCurve(
        normalized.time,
        flux,
        normalized.flux_err,
        target=normalized.target,
        metadata={
            **normalized.metadata,
            "injection_model": "quadratic-limb-darkened-small-planet",
            "injected_center_days": center,
            "injected_depth": depth,
            "injected_duration_days": duration_days,
            "impact_parameter": impact_parameter,
            "radius_ratio": radius_ratio,
            "limb_u1": limb_u1,
            "limb_u2": limb_u2,
            "injection_seed": seed,
        },
    )
    events = search_single_transits(
        injected,
        durations=search_durations,
        flatten_window_days=flatten_window_days,
        min_snr=min_snr,
        max_events=200,
        direction="dimming",
    )
    tolerance = max(2.0 * injected.cadence, 0.65 * duration_days)
    nearby = [event for event in events if abs(event.center_time_days - center) <= tolerance]
    best = max(nearby, key=lambda event: event.snr) if nearby else None

    novel_competing = 0
    for event in events:
        if abs(event.center_time_days - center) <= tolerance:
            continue
        if any(_event_matches(event, reference) for reference in background_events):
            continue
        novel_competing += 1

    control_snr = _matched_control_snr(brightening_controls, duration_days)
    margin = None
    if best is not None and control_snr is not None:
        margin = float(best.snr - control_snr)

    return PhysicalInjectionTrial(
        target=lc.target,
        sector_label=_sector_label(lc),
        depth=depth,
        duration_days=duration_days,
        impact_parameter=impact_parameter,
        radius_ratio=radius_ratio,
        limb_u1=limb_u1,
        limb_u2=limb_u2,
        seed=seed,
        injected_center_days=center,
        local_coverage_fraction=coverage,
        recovered=best is not None,
        recovered_center_days=None if best is None else best.center_time_days,
        recovered_snr=None if best is None else best.snr,
        timing_error_days=None if best is None else abs(best.center_time_days - center),
        matched_control_snr=control_snr,
        snr_above_matched_control=margin,
        novel_competing_events=novel_competing,
    )


def summarize_physical_trials(
    trials: Iterable[PhysicalInjectionTrial],
) -> list[PhysicalCompletenessCell]:
    grouped: dict[tuple[str, str, float, float, float], list[PhysicalInjectionTrial]] = {}
    for trial in trials:
        key = (
            trial.target,
            trial.sector_label,
            trial.depth,
            trial.duration_days,
            trial.impact_parameter,
        )
        grouped.setdefault(key, []).append(trial)

    cells: list[PhysicalCompletenessCell] = []
    for (target, sector, depth, duration, impact), group in sorted(grouped.items()):
        recovered = [trial for trial in group if trial.recovered]
        low, high = wilson_interval(len(recovered), len(group))
        snrs = [trial.recovered_snr for trial in recovered if trial.recovered_snr is not None]
        margins = [
            trial.snr_above_matched_control
            for trial in recovered
            if trial.snr_above_matched_control is not None
        ]
        timing = [
            trial.timing_error_days
            for trial in recovered
            if trial.timing_error_days is not None
        ]
        cells.append(
            PhysicalCompletenessCell(
                target=target,
                sector_label=sector,
                depth=depth,
                duration_days=duration,
                impact_parameter=impact,
                trials=len(group),
                recovered=len(recovered),
                completeness=len(recovered) / len(group),
                confidence_low=low,
                confidence_high=high,
                median_recovered_snr=None if not snrs else float(np.median(snrs)),
                median_snr_above_matched_control=(
                    None if not margins else float(np.median(margins))
                ),
                median_timing_error_days=None if not timing else float(np.median(timing)),
            )
        )
    return cells


def run_physical_campaign(
    lc: LightCurve,
    *,
    depths: Iterable[float] = (0.0001, 0.0002),
    durations_days: Iterable[float] = (0.08, 0.16),
    impact_parameters: Iterable[float] = (0.0, 0.6),
    seeds: Iterable[int] = range(4),
    min_snr: float = 5.0,
    flatten_window_days: float = 1.5,
    limb_u1: float = 0.35,
    limb_u2: float = 0.25,
) -> tuple[
    object,
    list[SingleTransitEvent],
    list[SingleTransitEvent],
    list[PhysicalInjectionTrial],
    list[PhysicalCompletenessCell],
]:
    durations = tuple(float(value) for value in durations_days)
    search_durations = tuple(
        sorted(
            {max(0.02, 0.65 * value) for value in durations}
            | set(durations)
            | {1.45 * value for value in durations}
        )
    )
    null_screen, background, brightening = screen_real_lightcurve(
        lc,
        durations=search_durations,
        flatten_window_days=flatten_window_days,
        min_snr=min_snr,
    )
    trials = [
        run_physical_injection_trial(
            lc,
            depth=float(depth),
            duration_days=float(duration),
            impact_parameter=float(impact),
            seed=int(seed),
            background_events=background,
            brightening_controls=brightening,
            search_durations=search_durations,
            flatten_window_days=flatten_window_days,
            min_snr=min_snr,
            limb_u1=limb_u1,
            limb_u2=limb_u2,
        )
        for depth in depths
        for duration in durations
        for impact in impact_parameters
        for seed in seeds
    ]
    return null_screen, background, brightening, trials, summarize_physical_trials(trials)


def write_physical_outputs(
    trials: list[PhysicalInjectionTrial],
    cells: list[PhysicalCompletenessCell],
    output_dir: str | Path,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "physical_trials.json").write_text(
        json.dumps([trial.to_dict() for trial in trials], indent=2), encoding="utf-8"
    )
    (output / "physical_completeness.json").write_text(
        json.dumps([cell.to_dict() for cell in cells], indent=2), encoding="utf-8"
    )
