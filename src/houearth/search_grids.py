from __future__ import annotations

from typing import Iterable


def physical_single_event_search_durations(
    durations_days: Iterable[float],
) -> tuple[float, ...]:
    """Return the frozen matched-filter duration family for physical injections.

    Every requested first-to-fourth-contact duration is searched at 0.65x, 1.0x, and
    1.45x.  The same returned family must be used for physical recovery and for every
    full-search surrogate maximum entering empirical significance calibration.
    """
    durations = tuple(float(value) for value in durations_days)
    if not durations:
        raise ValueError("at least one physical duration is required")
    if any(value <= 0 for value in durations):
        raise ValueError("physical durations must be positive")
    return tuple(
        sorted(
            {max(0.02, 0.65 * value) for value in durations}
            | set(durations)
            | {1.45 * value for value in durations}
        )
    )
