from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from .search_grids import physical_single_event_search_durations


@dataclass(frozen=True)
class ProtocolValidationReport:
    protocol: str
    accepted: bool
    completed_targets: int
    completed_null_targets: int
    physical_trials: int
    surrogate_trials: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ProtocolValidationError(ValueError):
    def __init__(self, report: ProtocolValidationReport):
        self.report = report
        super().__init__("; ".join(report.errors))


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _safe_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _float_tuple(value: object) -> tuple[float, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    parsed: list[float] = []
    for item in value:
        number = _safe_float(item)
        if number is None:
            return None
        parsed.append(number)
    return tuple(parsed)


def _same_float_tuple(
    observed: tuple[float, ...] | None,
    expected: tuple[float, ...],
) -> bool:
    if observed is None or len(observed) != len(expected):
        return False
    return all(
        math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
        for left, right in zip(observed, expected)
    )


def validate_phase07_summary(
    summary: Mapping[str, object],
    *,
    minimum_completed_targets: int = 4,
    minimum_completed_null_targets: int = 2,
    physical_trials_per_target: int = 32,
    surrogate_trials_per_null_target: int = 64,
    physical_durations_days: tuple[float, ...] = (0.08, 0.16),
) -> ProtocolValidationReport:
    """Validate a Phase 0.7 evidence summary without discarding partial results."""
    expected_search_durations = physical_single_event_search_durations(
        physical_durations_days
    )
    targets_value = summary.get("targets", [])
    malformed_targets = False
    if isinstance(targets_value, Sequence) and not isinstance(
        targets_value, (str, bytes)
    ):
        target_items = list(targets_value)
        targets = [item for item in target_items if isinstance(item, Mapping)]
        malformed_targets = len(targets) != len(target_items)
    else:
        targets = []
        malformed_targets = targets_value not in (None, [], ())

    completed = [item for item in targets if item.get("status") == "completed"]
    completed_null = [
        item
        for item in completed
        if item.get("surrogate_policy") == "unmasked-null"
        and _mapping(item.get("surrogate_summary")).get("status") == "completed"
    ]
    physical_trials = sum(
        _safe_int(item.get("physical_trials")) for item in completed
    )
    surrogate_trials = sum(
        _safe_int(item.get("surrogate_trials")) for item in completed
    )
    errors: list[str] = []

    if malformed_targets:
        errors.append("targets contains malformed non-object entries")
    root_search_durations = _float_tuple(summary.get("search_durations_days"))
    if not _same_float_tuple(root_search_durations, expected_search_durations):
        errors.append("root search-duration family is missing or inconsistent")
    if len(completed) < minimum_completed_targets:
        errors.append(
            f"completed targets {len(completed)} < required {minimum_completed_targets}"
        )
    if len(completed_null) < minimum_completed_null_targets:
        errors.append(
            "completed null targets "
            f"{len(completed_null)} < required {minimum_completed_null_targets}"
        )

    for item in completed:
        target_id = str(item.get("target_id", "unknown"))
        count = _safe_int(item.get("physical_trials"))
        if count != physical_trials_per_target:
            errors.append(
                f"{target_id}: physical trials {count} != {physical_trials_per_target}"
            )

        policy = item.get("surrogate_policy")
        surrogate_count = _safe_int(item.get("surrogate_trials"))
        surrogate_value = item.get("surrogate_summary")
        surrogate_summary = _mapping(surrogate_value)
        surrogate_status = surrogate_summary.get("status")
        if not isinstance(surrogate_value, Mapping):
            errors.append(f"{target_id}: surrogate summary is missing or malformed")

        if policy == "unmasked-null":
            if surrogate_status != "completed":
                errors.append(f"{target_id}: null campaign not completed")
            if surrogate_count != surrogate_trials_per_null_target:
                errors.append(
                    f"{target_id}: surrogate trials {surrogate_count} "
                    f"!= {surrogate_trials_per_null_target}"
                )
            target_search_durations = _float_tuple(
                surrogate_summary.get("search_durations_days")
            )
            if not _same_float_tuple(
                target_search_durations, expected_search_durations
            ):
                errors.append(
                    f"{target_id}: surrogate search-duration family is inconsistent"
                )
        elif policy == "skip-known-transits":
            if surrogate_count != 0:
                errors.append(
                    f"{target_id}: known transit host produced {surrogate_count} null trials"
                )
            if surrogate_status != "skipped":
                errors.append(f"{target_id}: missing explicit surrogate skip evidence")
        else:
            errors.append(f"{target_id}: unknown surrogate policy {policy!r}")

    reported_physical = _safe_int(
        summary.get("total_physical_trials"), default=physical_trials
    )
    reported_surrogate = _safe_int(
        summary.get("total_surrogate_trials"), default=surrogate_trials
    )
    if reported_physical != physical_trials:
        errors.append(
            f"reported physical total {reported_physical} != target sum {physical_trials}"
        )
    if reported_surrogate != surrogate_trials:
        errors.append(
            f"reported surrogate total {reported_surrogate} != target sum {surrogate_trials}"
        )

    minimum_p = _safe_float(summary.get("minimum_resolvable_surrogate_p"))
    expected_p = 1.0 / (surrogate_trials_per_null_target + 1.0)
    if minimum_p is None or abs(minimum_p - expected_p) > 1e-12:
        errors.append(
            "minimum empirical p resolution is missing or inconsistent with "
            f"{surrogate_trials_per_null_target} null trials"
        )

    report = ProtocolValidationReport(
        protocol="HOU-EARTH Phase 0.7 stratified physical pilot",
        accepted=not errors,
        completed_targets=len(completed),
        completed_null_targets=len(completed_null),
        physical_trials=physical_trials,
        surrogate_trials=surrogate_trials,
        errors=tuple(errors),
    )
    if errors:
        raise ProtocolValidationError(report)
    return report
