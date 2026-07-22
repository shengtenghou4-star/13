from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .core import LightCurve, SingleTransitEvent
from .search import search_single_transits
from .synthetic import inject_single_transit


@dataclass(frozen=True)
class NullScreenResult:
    target: str
    sector_label: str
    cadences: int
    baseline_days: float
    median_cadence_minutes: float
    event_count: int
    maximum_snr: float | None
    event_rate_per_day: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RealInjectionTrial:
    target: str
    sector_label: str
    depth: float
    duration_days: float
    seed: int
    injected_center_days: float
    local_coverage_fraction: float
    recovered: bool
    recovered_center_days: float | None
    recovered_snr: float | None
    timing_error_days: float | None
    background_event_count: int
    novel_competing_events: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RealCompletenessCell:
    target: str
    sector_label: str
    depth: float
    duration_days: float
    trials: int
    recovered: int
    completeness: float
    confidence_low: float
    confidence_high: float
    median_timing_error_days: float | None
    median_recovered_snr: float | None
    mean_novel_competing_events: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if trials <= 0 or successes < 0 or successes > trials:
        raise ValueError("require 0 <= successes <= trials and trials > 0")
    p = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    center = (p + z2 / (2.0 * trials)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / trials + z2 / (4.0 * trials * trials)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def _sector_label(lc: LightCurve) -> str:
    sectors = lc.metadata.get("sectors", [])
    if isinstance(sectors, (list, tuple)) and sectors:
        return ";".join(str(int(value)) for value in sectors)
    return "unknown"


def _event_matches(
    event: SingleTransitEvent,
    reference: SingleTransitEvent,
    *,
    scale: float = 0.75,
) -> bool:
    tolerance = scale * max(event.duration_days, reference.duration_days)
    return abs(event.center_time_days - reference.center_time_days) <= tolerance


def _valid_injection_windows(
    lc: LightCurve,
    *,
    duration_days: float,
    excluded_events: Sequence[SingleTransitEvent],
    gap_factor: float = 3.5,
    minimum_coverage: float = 0.70,
) -> list[tuple[float, float]]:
    """Return centers whose local windows are well sampled and avoid existing events."""
    if duration_days <= 0:
        raise ValueError("duration_days must be positive")
    if not 0 < minimum_coverage <= 1:
        raise ValueError("minimum_coverage must be in (0, 1]")

    time = lc.time
    cadence = lc.cadence
    expected_points = max(3, int(round(duration_days / cadence)) + 1)
    minimum_points = max(3, int(math.ceil(minimum_coverage * expected_points)))
    stride = max(1, expected_points // 3)
    half = duration_days / 2.0
    valid: list[tuple[float, float]] = []

    for index in range(0, len(time), stride):
        center = float(time[index])
        left = int(np.searchsorted(time, center - half, side="left"))
        right = int(np.searchsorted(time, center + half, side="right"))
        count = right - left
        if count < minimum_points:
            continue
        local_time = time[left:right]
        if len(local_time) >= 2 and float(np.max(np.diff(local_time))) > gap_factor * cadence:
            continue
        if any(
            abs(center - event.center_time_days)
            <= 1.5 * max(duration_days, event.duration_days)
            for event in excluded_events
        ):
            continue
        coverage = min(1.0, count / expected_points)
        valid.append((center, float(coverage)))
    return valid


def screen_real_lightcurve(
    lc: LightCurve,
    *,
    durations: tuple[float, ...],
    flatten_window_days: float,
    min_snr: float,
    max_events: int = 200,
) -> tuple[NullScreenResult, list[SingleTransitEvent]]:
    """Run the detector before injection to record pre-existing real-data events."""
    events = search_single_transits(
        lc,
        durations=durations,
        flatten_window_days=flatten_window_days,
        min_snr=min_snr,
        max_events=max_events,
    )
    maximum_snr = max((event.snr for event in events), default=None)
    result = NullScreenResult(
        target=lc.target,
        sector_label=_sector_label(lc),
        cadences=len(lc.time),
        baseline_days=lc.baseline,
        median_cadence_minutes=lc.cadence * 24.0 * 60.0,
        event_count=len(events),
        maximum_snr=None if maximum_snr is None else float(maximum_snr),
        event_rate_per_day=len(events) / max(lc.baseline, 1e-12),
    )
    return result, events


def run_real_injection_trial(
    lc: LightCurve,
    *,
    depth: float,
    duration_days: float,
    seed: int,
    background_events: Sequence[SingleTransitEvent],
    search_durations: tuple[float, ...],
    flatten_window_days: float,
    min_snr: float,
) -> RealInjectionTrial:
    """Inject one event into an observed light curve and run a blind recovery."""
    if depth <= 0:
        raise ValueError("depth must be positive")
    normalized = lc.normalized()
    windows = _valid_injection_windows(
        normalized,
        duration_days=duration_days,
        excluded_events=background_events,
    )
    if not windows:
        raise RuntimeError(
            f"No valid injection window for {lc.target!r} at duration {duration_days} days"
        )

    rng = np.random.default_rng(seed)
    center, coverage = windows[int(rng.integers(0, len(windows)))]
    flux = inject_single_transit(
        normalized.time,
        normalized.flux,
        center=center,
        duration=duration_days,
        depth=depth,
    )
    injected = LightCurve(
        normalized.time,
        flux,
        normalized.flux_err,
        target=normalized.target,
        metadata={
            **normalized.metadata,
            "injected_center_days": center,
            "injected_depth": depth,
            "injected_duration_days": duration_days,
            "injection_seed": seed,
        },
    )
    events = search_single_transits(
        injected,
        durations=search_durations,
        flatten_window_days=flatten_window_days,
        min_snr=min_snr,
        max_events=200,
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

    return RealInjectionTrial(
        target=lc.target,
        sector_label=_sector_label(lc),
        depth=depth,
        duration_days=duration_days,
        seed=seed,
        injected_center_days=center,
        local_coverage_fraction=coverage,
        recovered=best is not None,
        recovered_center_days=None if best is None else best.center_time_days,
        recovered_snr=None if best is None else best.snr,
        timing_error_days=None if best is None else abs(best.center_time_days - center),
        background_event_count=len(background_events),
        novel_competing_events=novel_competing,
    )


def summarize_real_trials(trials: Iterable[RealInjectionTrial]) -> list[RealCompletenessCell]:
    grouped: dict[tuple[str, str, float, float], list[RealInjectionTrial]] = {}
    for trial in trials:
        key = (trial.target, trial.sector_label, trial.depth, trial.duration_days)
        grouped.setdefault(key, []).append(trial)

    cells: list[RealCompletenessCell] = []
    for (target, sector_label, depth, duration), group in sorted(grouped.items()):
        recovered = [trial for trial in group if trial.recovered]
        low, high = wilson_interval(len(recovered), len(group))
        timing = [
            trial.timing_error_days
            for trial in recovered
            if trial.timing_error_days is not None
        ]
        snrs = [trial.recovered_snr for trial in recovered if trial.recovered_snr is not None]
        cells.append(
            RealCompletenessCell(
                target=target,
                sector_label=sector_label,
                depth=depth,
                duration_days=duration,
                trials=len(group),
                recovered=len(recovered),
                completeness=len(recovered) / len(group),
                confidence_low=low,
                confidence_high=high,
                median_timing_error_days=None if not timing else float(np.median(timing)),
                median_recovered_snr=None if not snrs else float(np.median(snrs)),
                mean_novel_competing_events=float(
                    np.mean([trial.novel_competing_events for trial in group])
                ),
            )
        )
    return cells


def run_real_lightcurve_campaign(
    lc: LightCurve,
    *,
    depths: Iterable[float] = (0.004, 0.008),
    durations_days: Iterable[float] = (0.08, 0.16),
    seeds: Iterable[int] = range(4),
    min_snr: float = 5.0,
    flatten_window_days: float = 1.5,
) -> tuple[NullScreenResult, list[SingleTransitEvent], list[RealInjectionTrial], list[RealCompletenessCell]]:
    durations = tuple(float(value) for value in durations_days)
    if not durations:
        raise ValueError("at least one duration is required")
    search_durations = tuple(
        sorted(
            {
                max(0.02, 0.65 * duration)
                for duration in durations
            }
            | set(durations)
            | {1.45 * duration for duration in durations}
        )
    )
    null_screen, background_events = screen_real_lightcurve(
        lc,
        durations=search_durations,
        flatten_window_days=flatten_window_days,
        min_snr=min_snr,
    )
    trials = [
        run_real_injection_trial(
            lc,
            depth=float(depth),
            duration_days=duration,
            seed=int(seed),
            background_events=background_events,
            search_durations=search_durations,
            flatten_window_days=flatten_window_days,
            min_snr=min_snr,
        )
        for depth in depths
        for duration in durations
        for seed in seeds
    ]
    return null_screen, background_events, trials, summarize_real_trials(trials)


def _write_csv(records: Sequence[object], path: Path) -> None:
    if not records:
        return
    fieldnames = list(asdict(records[0]))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(record) for record in records)


def write_real_campaign_outputs(
    lc: LightCurve,
    null_screen: NullScreenResult,
    background_events: Sequence[SingleTransitEvent],
    trials: Sequence[RealInjectionTrial],
    cells: Sequence[RealCompletenessCell],
    output_dir: str | Path,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "experiment": "real-tess-single-transit-injection-recovery",
        "status": "calibration; not a discovery claim",
        "target": lc.target,
        "lightcurve": lc.to_dict(),
        "git_commit": os.environ.get("GITHUB_SHA"),
        "trial_count": len(trials),
        "depths": sorted({trial.depth for trial in trials}),
        "durations_days": sorted({trial.duration_days for trial in trials}),
        "seeds": sorted({trial.seed for trial in trials}),
        "important_caveat": (
            "Pre-injection events are observational signals or systematics until vetted; "
            "they are not automatically false alarms."
        ),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "null_screen.json").write_text(
        json.dumps(null_screen.to_dict(), indent=2), encoding="utf-8"
    )
    (output / "background_events.json").write_text(
        json.dumps([event.to_dict() for event in background_events], indent=2),
        encoding="utf-8",
    )
    (output / "trials.json").write_text(
        json.dumps([trial.to_dict() for trial in trials], indent=2), encoding="utf-8"
    )
    (output / "completeness.json").write_text(
        json.dumps([cell.to_dict() for cell in cells], indent=2), encoding="utf-8"
    )
    _write_csv(list(trials), output / "trials.csv")
    _write_csv(list(cells), output / "completeness.csv")

    rows = "\n".join(
        "<tr>"
        f"<td>{cell.depth:.4f}</td>"
        f"<td>{24 * cell.duration_days:.2f}</td>"
        f"<td>{cell.recovered}/{cell.trials}</td>"
        f"<td>{100 * cell.completeness:.1f}%</td>"
        f"<td>{100 * cell.confidence_low:.1f}%–{100 * cell.confidence_high:.1f}%</td>"
        f"<td>{'' if cell.median_recovered_snr is None else f'{cell.median_recovered_snr:.2f}'}</td>"
        f"<td>{cell.mean_novel_competing_events:.2f}</td>"
        "</tr>"
        for cell in cells
    )
    html = f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><title>HOU-EARTH real-data calibration</title>
<style>body{{font-family:system-ui;max-width:1100px;margin:40px auto;padding:0 20px}}table{{border-collapse:collapse;width:100%}}th,td{{padding:8px;border:1px solid #ccc;text-align:right}}</style></head>
<body><h1>HOU-EARTH real TESS injection/recovery</h1>
<p><strong>Target:</strong> {lc.target}; <strong>sectors:</strong> {_sector_label(lc)}; <strong>pre-injection events:</strong> {null_screen.event_count}.</p>
<p>This is a calibration result, not an exoplanet discovery claim. Confidence ranges are 95% Wilson intervals.</p>
<table><thead><tr><th>Depth</th><th>Duration (hours)</th><th>Recovered</th><th>Completeness</th><th>95% interval</th><th>Median SNR</th><th>Novel competing events</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""
    (output / "report.html").write_text(html, encoding="utf-8")
