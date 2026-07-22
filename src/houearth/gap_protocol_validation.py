from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from .surrogates import DEFAULT_GAP_FACTOR, GAP_AWARE_METHOD


# Backward-compatible public protocol names, sourced from the implementation.
SURROGATE_METHOD = GAP_AWARE_METHOD
SURROGATE_GAP_FACTOR = DEFAULT_GAP_FACTOR


@dataclass(frozen=True)
class GapProtocolValidationReport:
    protocol: str
    accepted: bool
    completed_null_targets: int
    surrogate_trials: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class GapProtocolValidationError(ValueError):
    def __init__(self, report: GapProtocolValidationReport):
        self.report = report
        super().__init__("; ".join(report.errors))


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _exact_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _finite_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def validate_phase07_gap_summary(
    summary: Mapping[str, object],
    *,
    minimum_completed_null_targets: int = 2,
    surrogate_trials_per_null_target: int = 64,
    expected_method: str = SURROGATE_METHOD,
    expected_gap_factor: float = SURROGATE_GAP_FACTOR,
) -> GapProtocolValidationReport:
    """Validate gap-aware null evidence independently of the main protocol gate."""
    target_value = summary.get("targets", [])
    if isinstance(target_value, Sequence) and not isinstance(
        target_value, (str, bytes)
    ):
        targets = [item for item in target_value if isinstance(item, Mapping)]
    else:
        targets = []

    null_targets = [
        item
        for item in targets
        if item.get("status") == "completed"
        and item.get("surrogate_policy") == "unmasked-null"
    ]
    errors: list[str] = []
    trial_total = 0

    if len(null_targets) < minimum_completed_null_targets:
        errors.append(
            "completed null targets "
            f"{len(null_targets)} < required {minimum_completed_null_targets}"
        )

    for item in null_targets:
        target_id = str(item.get("target_id", "unknown"))
        record = _mapping(item.get("surrogate_summary"))
        if record.get("status") != "completed":
            errors.append(f"{target_id}: surrogate summary is not completed")
        if record.get("method") != expected_method:
            errors.append(f"{target_id}: surrogate method is inconsistent")

        gap_factor = _finite_float(record.get("gap_factor"))
        if gap_factor is None or not math.isclose(
            gap_factor,
            expected_gap_factor,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            errors.append(f"{target_id}: surrogate gap factor is inconsistent")

        minimum_segments = _exact_int(record.get("minimum_segments"))
        maximum_segments = _exact_int(record.get("maximum_segments"))
        if minimum_segments is None or maximum_segments is None:
            errors.append(f"{target_id}: segment counts are missing or non-integral")
        elif minimum_segments < 1 or maximum_segments < 1:
            errors.append(f"{target_id}: segment counts must be positive")
        elif minimum_segments != maximum_segments:
            errors.append(
                f"{target_id}: segment count changed across fixed-timestamp trials"
            )

        count = _exact_int(item.get("surrogate_trials"))
        if count is None:
            errors.append(f"{target_id}: surrogate trial count is non-integral")
            count = 0
        if count != surrogate_trials_per_null_target:
            errors.append(
                f"{target_id}: surrogate trials {count} "
                f"!= {surrogate_trials_per_null_target}"
            )
        trial_total += count

    report = GapProtocolValidationReport(
        protocol="HOU-EARTH Phase 0.7 gap-aware surrogate evidence",
        accepted=not errors,
        completed_null_targets=len(null_targets),
        surrogate_trials=trial_total,
        errors=tuple(errors),
    )
    if errors:
        raise GapProtocolValidationError(report)
    return report
