from __future__ import annotations

import math
from collections import defaultdict
from statistics import median
from typing import Iterable, Mapping, Sequence


def duration_matched_controls(
    controls: Sequence[Mapping[str, object]],
    duration_days: float,
) -> list[Mapping[str, object]]:
    """Select same-duration controls, or the nearest available duration bin."""
    if duration_days <= 0:
        raise ValueError("duration_days must be positive")
    if not controls:
        return []

    exact = [
        control
        for control in controls
        if math.isclose(
            float(control["duration_days"]),
            duration_days,
            rel_tol=1e-9,
            abs_tol=1e-12,
        )
    ]
    if exact:
        return exact

    distances = [
        abs(math.log(float(control["duration_days"]) / duration_days))
        for control in controls
    ]
    nearest = min(distances)
    return [
        control
        for control, distance in zip(controls, distances)
        if math.isclose(distance, nearest, rel_tol=1e-9, abs_tol=1e-12)
    ]


def empirical_upper_tail_probability(signal_snr: float, control_snrs: Sequence[float]) -> float | None:
    """Conservative finite-sample upper-tail probability with add-one smoothing."""
    if not control_snrs:
        return None
    exceedances = sum(float(value) >= signal_snr for value in control_snrs)
    return (1.0 + exceedances) / (1.0 + len(control_snrs))


def annotate_trial_rows(
    trial_rows: Iterable[Mapping[str, object]],
    controls: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Attach duration-matched brightening statistics without altering raw trials."""
    annotated: list[dict[str, object]] = []
    for source in trial_rows:
        row = dict(source)
        duration = float(row["duration_days"])
        recovered = str(row["recovered"]).lower() == "true"
        signal_value = row.get("recovered_snr")
        signal_snr = float(signal_value) if recovered and signal_value not in (None, "") else None
        matched = duration_matched_controls(controls, duration)
        control_snrs = [float(control["snr"]) for control in matched]
        control_maximum = max(control_snrs) if control_snrs else None
        margin = (
            None
            if signal_snr is None or control_maximum is None
            else signal_snr - control_maximum
        )
        p_value = (
            None
            if signal_snr is None
            else empirical_upper_tail_probability(signal_snr, control_snrs)
        )
        row.update(
            {
                "matched_control_duration_days": (
                    None if not matched else float(matched[0]["duration_days"])
                ),
                "matched_control_count": len(matched),
                "matched_control_maximum_snr": control_maximum,
                "snr_above_matched_control": margin,
                "brightening_empirical_p": p_value,
            }
        )
        annotated.append(row)
    return annotated


def summarize_annotated_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    pool_targets: bool,
) -> list[dict[str, object]]:
    """Summarize completeness and matched-control separation by grid cell."""
    grouped: dict[tuple[object, ...], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        base = (float(row["depth"]), float(row["duration_days"]))
        key = base if pool_targets else (str(row["target_id"]), *base)
        grouped[key].append(row)

    summaries: list[dict[str, object]] = []
    for key, group in sorted(grouped.items(), key=lambda item: str(item[0])):
        recovered = [row for row in group if str(row["recovered"]).lower() == "true"]
        margins = [
            float(row["snr_above_matched_control"])
            for row in recovered
            if row.get("snr_above_matched_control") not in (None, "")
        ]
        p_values = [
            float(row["brightening_empirical_p"])
            for row in recovered
            if row.get("brightening_empirical_p") not in (None, "")
        ]
        above = sum(value > 0 for value in margins)
        common: dict[str, object] = {
            "targets": len({str(row["target_id"]) for row in group}),
            "trials": len(group),
            "recovered": len(recovered),
            "completeness": len(recovered) / len(group),
            "recoveries_with_matched_control": len(margins),
            "recoveries_above_matched_control": above,
            "fraction_above_matched_control": (
                None if not margins else above / len(margins)
            ),
            "median_snr_above_matched_control": (
                None if not margins else median(margins)
            ),
            "median_brightening_empirical_p": (
                None if not p_values else median(p_values)
            ),
        }
        if pool_targets:
            depth, duration = key
            summary = {"depth": depth, "duration_days": duration, **common}
        else:
            target_id, depth, duration = key
            summary = {
                "target_id": target_id,
                "depth": depth,
                "duration_days": duration,
                **common,
            }
        summaries.append(summary)
    return summaries
