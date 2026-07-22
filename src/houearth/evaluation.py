from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from .core import LightCurve
from .search import search_single_transits
from .synthetic import inject_single_transit


@dataclass(frozen=True)
class SingleTransitTrial:
    depth: float
    duration_days: float
    seed: int
    injected_center_days: float
    recovered: bool
    recovered_center_days: float | None
    recovered_snr: float | None
    timing_error_days: float | None
    false_events: int

    def to_dict(self) -> dict[str, float | int | bool | None]:
        return asdict(self)


@dataclass(frozen=True)
class CompletenessCell:
    depth: float
    duration_days: float
    trials: int
    recovered: int
    completeness: float
    median_timing_error_days: float | None
    median_recovered_snr: float | None
    mean_false_events: float

    def to_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


def make_noise_lightcurve(
    *,
    baseline_days: float = 27.0,
    cadence_minutes: float = 30.0,
    noise: float = 0.0018,
    seed: int = 0,
    target: str = "synthetic-noise",
) -> LightCurve:
    """Create a deterministic TESS-like light curve without a periodic planet."""
    if baseline_days <= 2:
        raise ValueError("baseline_days must exceed two days")
    if cadence_minutes <= 0 or noise <= 0:
        raise ValueError("cadence_minutes and noise must be positive")

    rng = np.random.default_rng(seed)
    cadence_days = cadence_minutes / (24.0 * 60.0)
    time = np.arange(0.0, baseline_days, cadence_days)
    stellar = (
        0.0011 * np.sin(2 * np.pi * time / 10.7 + 0.2)
        + 0.0005 * np.sin(2 * np.pi * time / 3.4 - 0.7)
    )
    flux = 1.0 + stellar + rng.normal(0.0, noise, size=len(time))
    return LightCurve(
        time,
        flux,
        np.full_like(time, noise),
        target=target,
        metadata={
            "kind": "synthetic-noise",
            "seed": seed,
            "noise": noise,
            "baseline_days": baseline_days,
            "cadence_minutes": cadence_minutes,
        },
    )


def _trial_center(rng: np.random.Generator, baseline: float, duration: float) -> float:
    margin = max(1.0, 2.0 * duration)
    if baseline <= 2 * margin:
        raise ValueError("baseline is too short for the requested event duration")
    return float(rng.uniform(margin, baseline - margin))


def run_single_transit_trial(
    *,
    depth: float,
    duration_days: float,
    seed: int,
    baseline_days: float = 27.0,
    cadence_minutes: float = 30.0,
    noise: float = 0.0018,
    min_snr: float = 5.0,
) -> SingleTransitTrial:
    """Inject one isolated event and determine whether the detector recovers it."""
    base = make_noise_lightcurve(
        baseline_days=baseline_days,
        cadence_minutes=cadence_minutes,
        noise=noise,
        seed=seed,
        target=f"single-injection-d{depth:g}-t{duration_days:g}-s{seed}",
    )
    rng = np.random.default_rng(seed + 104729)
    center = _trial_center(rng, base.baseline, duration_days)
    injected_flux = inject_single_transit(
        base.time,
        base.flux,
        center=center,
        duration=duration_days,
        depth=depth,
    )
    injected = LightCurve(
        base.time,
        injected_flux,
        base.flux_err,
        target=base.target,
        metadata={
            **base.metadata,
            "injected_center_days": center,
            "injected_depth": depth,
            "injected_duration_days": duration_days,
        },
    )
    events = search_single_transits(
        injected,
        durations=tuple(
            sorted(
                {
                    max(0.04, 0.65 * duration_days),
                    duration_days,
                    1.45 * duration_days,
                }
            )
        ),
        flatten_window_days=max(1.5, 5.0 * duration_days),
        min_snr=min_snr,
        max_events=20,
    )
    tolerance = max(2.0 * injected.cadence, 0.65 * duration_days)
    nearby = [event for event in events if abs(event.center_time_days - center) <= tolerance]
    best = max(nearby, key=lambda event: event.snr) if nearby else None
    false_events = sum(abs(event.center_time_days - center) > tolerance for event in events)
    return SingleTransitTrial(
        depth=depth,
        duration_days=duration_days,
        seed=seed,
        injected_center_days=center,
        recovered=best is not None,
        recovered_center_days=None if best is None else best.center_time_days,
        recovered_snr=None if best is None else best.snr,
        timing_error_days=None if best is None else abs(best.center_time_days - center),
        false_events=false_events,
    )


def summarize_trials(trials: Iterable[SingleTransitTrial]) -> list[CompletenessCell]:
    grouped: dict[tuple[float, float], list[SingleTransitTrial]] = {}
    for trial in trials:
        grouped.setdefault((trial.depth, trial.duration_days), []).append(trial)

    cells: list[CompletenessCell] = []
    for (depth, duration), group in sorted(grouped.items()):
        recovered = [trial for trial in group if trial.recovered]
        timing = [trial.timing_error_days for trial in recovered if trial.timing_error_days is not None]
        snrs = [trial.recovered_snr for trial in recovered if trial.recovered_snr is not None]
        cells.append(
            CompletenessCell(
                depth=depth,
                duration_days=duration,
                trials=len(group),
                recovered=len(recovered),
                completeness=len(recovered) / len(group),
                median_timing_error_days=None if not timing else float(np.median(timing)),
                median_recovered_snr=None if not snrs else float(np.median(snrs)),
                mean_false_events=float(np.mean([trial.false_events for trial in group])),
            )
        )
    return cells


def run_single_transit_campaign(
    *,
    depths: Iterable[float] = (0.002, 0.004, 0.008, 0.012),
    durations_days: Iterable[float] = (0.08, 0.16, 0.32),
    seeds: Iterable[int] = range(8),
    baseline_days: float = 27.0,
    cadence_minutes: float = 30.0,
    noise: float = 0.0018,
    min_snr: float = 5.0,
) -> tuple[list[SingleTransitTrial], list[CompletenessCell]]:
    trials = [
        run_single_transit_trial(
            depth=float(depth),
            duration_days=float(duration),
            seed=int(seed),
            baseline_days=baseline_days,
            cadence_minutes=cadence_minutes,
            noise=noise,
            min_snr=min_snr,
        )
        for depth in depths
        for duration in durations_days
        for seed in seeds
    ]
    return trials, summarize_trials(trials)


def write_campaign_outputs(
    trials: list[SingleTransitTrial],
    cells: list[CompletenessCell],
    output_dir: str | Path,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    (output / "trials.json").write_text(
        json.dumps([trial.to_dict() for trial in trials], indent=2), encoding="utf-8"
    )
    (output / "completeness.json").write_text(
        json.dumps([cell.to_dict() for cell in cells], indent=2), encoding="utf-8"
    )

    with (output / "completeness.csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(CompletenessCell.__dataclass_fields__)
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cell.to_dict() for cell in cells)

    rows = "\n".join(
        "<tr>"
        f"<td>{cell.depth:.4f}</td>"
        f"<td>{cell.duration_days:.3f}</td>"
        f"<td>{cell.recovered}/{cell.trials}</td>"
        f"<td>{100 * cell.completeness:.1f}%</td>"
        f"<td>{'' if cell.median_recovered_snr is None else f'{cell.median_recovered_snr:.2f}'}</td>"
        f"<td>{cell.mean_false_events:.2f}</td>"
        "</tr>"
        for cell in cells
    )
    html = f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><title>HOU-EARTH completeness</title>
<style>body{{font-family:system-ui;max-width:1000px;margin:40px auto;padding:0 20px}}table{{border-collapse:collapse;width:100%}}th,td{{padding:8px;border:1px solid #ccc;text-align:right}}</style></head>
<body><h1>HOU-EARTH single-transit completeness</h1>
<p>Deterministic synthetic injection/recovery campaign. A recovered event must fall within the duration-scaled timing tolerance.</p>
<table><thead><tr><th>Depth</th><th>Duration (d)</th><th>Recovered</th><th>Completeness</th><th>Median SNR</th><th>Mean false events</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""
    (output / "report.html").write_text(html, encoding="utf-8")
