from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from numbers import Real
from typing import Mapping, Sequence

from .candidate_campaign import (
    PHASE09_CALIBRATION_SCHEMA,
    PHASE09_CAMPAIGN_EVIDENCE_SCHEMA,
    PHASE09_SURROGATE_BLOCK_DAYS,
    PHASE09_SURROGATE_SEEDS,
)
from .candidate_evidence import validate_candidate_evidence
from .provenance import canonical_json_sha256
from .surrogates import DEFAULT_GAP_FACTOR, GAP_AWARE_METHOD


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_FIELDS = {
    "schema", "source_commit", "frozen_at_utc", "campaign_lock",
    "target_calibrations", "candidate_evidence", "package_sha256",
}
_TARGET_FIELDS = {
    "target_id", "target_name", "sector_label",
    "campaign_input_combined_sha256", "search_duration_family_days",
    "dimming_events", "brightening_control_events", "surrogate_trials",
    "calibration_receipt",
}
_EVENT_FIELDS = {
    "target", "center_time_days", "duration_days", "depth", "snr",
    "local_points", "direction",
}
_SURROGATE_FIELDS = {
    "target", "sector_label", "seed", "method", "block_days",
    "contiguous_segments", "gap_factor", "neutralized_events",
    "neutralized_points", "dimming_events", "brightening_events",
    "maximum_dimming_snr", "maximum_brightening_snr",
    "exceeded_dimming_threshold", "exceeded_brightening_threshold",
}


@dataclass(frozen=True)
class CandidateCampaignValidationReport:
    protocol: str
    accepted: bool
    targets: int
    surrogate_trials: int
    machine_events: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CandidateCampaignValidationError(ValueError):
    def __init__(self, report: CandidateCampaignValidationReport):
        self.report = report
        super().__init__("; ".join(report.errors))


def _closed(row: Mapping[object, object], expected: set[str], label: str, errors: list[str]) -> None:
    keys = {key for key in row if isinstance(key, str)}
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    extra.extend(repr(key) for key in row if not isinstance(key, str))
    if missing:
        errors.append(f"{label} is missing fields: {', '.join(missing)}")
    if extra:
        errors.append(f"{label} contains undeclared fields: {', '.join(extra)}")


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _same(left: object, right: object) -> bool:
    a, b = _number(left), _number(right)
    if a is None or b is None:
        return left is None and right is None
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def _duration_family(value: object) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    parsed = [_number(item) for item in value]
    if not parsed or any(item is None or item <= 0 for item in parsed):
        return ()
    result = tuple(float(item) for item in parsed)
    return result if result == tuple(sorted(set(result))) else ()


def _event(row: Mapping[str, object], target: str, direction: str, durations: tuple[float, ...]) -> dict[str, object] | None:
    if row.get("target") != target or row.get("direction") != direction:
        return None
    center = _number(row.get("center_time_days"))
    duration = _number(row.get("duration_days"))
    depth = _number(row.get("depth"))
    snr = _number(row.get("snr"))
    points = row.get("local_points")
    if (
        center is None or duration is None or depth is None or snr is None
        or center < 0 or duration <= 0 or depth <= 0 or snr < 0
        or isinstance(points, bool) or not isinstance(points, int) or points < 1
        or not any(math.isclose(duration, item, rel_tol=0.0, abs_tol=1e-12) for item in durations)
    ):
        return None
    return {
        "target": target, "center_time_days": center, "duration_days": duration,
        "depth": depth, "snr": snr, "local_points": points, "direction": direction,
    }


def _event_key(row: Mapping[str, object]) -> tuple[object, ...]:
    return (
        float(row["center_time_days"]), float(row["duration_days"]),
        -float(row["snr"]), -float(row["depth"]), int(row["local_points"]),
        row["direction"],
    )


def _control_snr(event: Mapping[str, object], controls: Sequence[Mapping[str, object]]) -> float | None:
    if not controls:
        return None
    available = sorted({float(row["duration_days"]) for row in controls})
    duration = min(
        available,
        key=lambda item: (abs(item - float(event["duration_days"])), item),
    )
    return max(
        float(row["snr"]) for row in controls
        if math.isclose(float(row["duration_days"]), duration, rel_tol=0.0, abs_tol=1e-12)
    )


def validate_candidate_campaign_evidence(
    payload: Mapping[str, object],
) -> CandidateCampaignValidationReport:
    errors: list[str] = []
    _closed(payload, _PACKAGE_FIELDS, "campaign evidence", errors)
    if payload.get("schema") != PHASE09_CAMPAIGN_EVIDENCE_SCHEMA:
        errors.append("campaign evidence schema is missing or inconsistent")

    lock_value = payload.get("campaign_lock")
    lock = lock_value if isinstance(lock_value, Mapping) else {}
    if not lock:
        errors.append("campaign lock is missing or malformed")
    lock_hash = lock.get("campaign_lock_sha256")
    expected_lock_hash = canonical_json_sha256(
        {key: value for key, value in lock.items() if key != "campaign_lock_sha256"}
    )
    if lock_hash != expected_lock_hash:
        errors.append("campaign_lock_sha256 does not match the campaign lock")
    if lock.get("source_commit") != payload.get("source_commit"):
        errors.append("campaign lock and package source commits differ")
    if lock.get("frozen_at_utc") != payload.get("frozen_at_utc"):
        errors.append("campaign lock and package freeze timestamps differ")
    if lock.get("surrogate_method") != GAP_AWARE_METHOD:
        errors.append("campaign lock surrogate method is inconsistent")
    if lock.get("surrogate_seeds") != list(PHASE09_SURROGATE_SEEDS):
        errors.append("campaign lock surrogate seed grid is inconsistent")
    if not _same(lock.get("surrogate_block_days"), PHASE09_SURROGATE_BLOCK_DAYS):
        errors.append("campaign lock surrogate block length is inconsistent")
    if not _same(lock.get("surrogate_gap_factor"), DEFAULT_GAP_FACTOR):
        errors.append("campaign lock surrogate gap factor is inconsistent")
    durations = _duration_family(lock.get("search_duration_family_days"))
    if not durations:
        errors.append("campaign lock search-duration family is invalid")

    lock_targets_value = lock.get("targets")
    lock_targets = (
        list(lock_targets_value)
        if isinstance(lock_targets_value, Sequence)
        and not isinstance(lock_targets_value, (str, bytes))
        else []
    )
    lock_map = {
        row.get("target_id"): row
        for row in lock_targets
        if isinstance(row, Mapping) and isinstance(row.get("target_id"), str)
    }
    if len(lock_map) != len(lock_targets):
        errors.append("campaign lock contains malformed or repeated targets")

    calibration_value = payload.get("target_calibrations")
    calibrations = (
        list(calibration_value)
        if isinstance(calibration_value, Sequence)
        and not isinstance(calibration_value, (str, bytes))
        else []
    )
    expected_rows: dict[tuple[str, str, int], dict[str, object]] = {}
    total_surrogates = 0
    seen: set[str] = set()

    for index, value in enumerate(calibrations):
        label = f"target calibration {index}"
        if not isinstance(value, Mapping):
            errors.append(f"{label} is not an object")
            continue
        _closed(value, _TARGET_FIELDS, label, errors)
        target_id = value.get("target_id")
        target_name = value.get("target_name")
        sector = value.get("sector_label")
        campaign_hash = value.get("campaign_input_combined_sha256")
        if not all(isinstance(item, str) and item for item in (target_id, target_name, sector)):
            errors.append(f"{label} has invalid target identity")
            continue
        if target_id in seen:
            errors.append(f"{label} repeats target_id {target_id}")
        seen.add(target_id)
        if not isinstance(campaign_hash, str) or _SHA256.fullmatch(campaign_hash) is None:
            errors.append(f"{label} has invalid campaign input SHA-256")
            continue
        lock_row = lock_map.get(target_id)
        if not isinstance(lock_row, Mapping) or (
            lock_row.get("query"), lock_row.get("sector_label"),
            lock_row.get("campaign_input_combined_sha256")
        ) != (target_name, sector, campaign_hash):
            errors.append(f"{label} identity differs from the campaign lock")
        if _duration_family(value.get("search_duration_family_days")) != durations:
            errors.append(f"{label} search-duration family differs from campaign lock")

        parsed_events: dict[str, list[dict[str, object]]] = {}
        for field, direction in (
            ("dimming_events", "dimming"),
            ("brightening_control_events", "brightening"),
        ):
            raw = value.get(field)
            rows = (
                list(raw)
                if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
                else []
            )
            parsed: list[dict[str, object]] = []
            for event_index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    errors.append(f"{label} {field} {event_index} is not an object")
                    continue
                _closed(row, _EVENT_FIELDS, f"{label} {field} {event_index}", errors)
                result = _event(row, target_name, direction, durations)
                if result is None:
                    errors.append(f"{label} {field} {event_index} is invalid")
                else:
                    parsed.append(result)
            parsed_events[field] = sorted(parsed, key=_event_key)

        surrogate_value = value.get("surrogate_trials")
        surrogate_rows = (
            list(surrogate_value)
            if isinstance(surrogate_value, Sequence)
            and not isinstance(surrogate_value, (str, bytes))
            else []
        )
        total_surrogates += len(surrogate_rows)
        maxima_by_seed: dict[int, float | None] = {}
        for trial_index, row in enumerate(surrogate_rows):
            trial_label = f"{label} surrogate trial {trial_index}"
            if not isinstance(row, Mapping):
                errors.append(f"{trial_label} is not an object")
                continue
            _closed(row, _SURROGATE_FIELDS, trial_label, errors)
            seed = row.get("seed")
            maximum = row.get("maximum_dimming_snr")
            valid_maximum = maximum is None or (
                _number(maximum) is not None and float(maximum) >= 0
            )
            valid = (
                row.get("target") == target_name
                and row.get("sector_label") == sector
                and row.get("method") == GAP_AWARE_METHOD
                and _same(row.get("block_days"), PHASE09_SURROGATE_BLOCK_DAYS)
                and _same(row.get("gap_factor"), DEFAULT_GAP_FACTOR)
                and row.get("neutralized_events") == 0
                and row.get("neutralized_points") == 0
                and isinstance(row.get("contiguous_segments"), int)
                and not isinstance(row.get("contiguous_segments"), bool)
                and row.get("contiguous_segments") >= 1
                and isinstance(seed, int) and not isinstance(seed, bool)
                and valid_maximum
            )
            if not valid or seed in maxima_by_seed:
                errors.append(f"{trial_label} is invalid")
            else:
                maxima_by_seed[seed] = None if maximum is None else float(maximum)
        if tuple(sorted(maxima_by_seed)) != PHASE09_SURROGATE_SEEDS:
            errors.append(f"{label} does not contain the exact 64-trial seed grid")
        maxima = [maxima_by_seed.get(seed) for seed in PHASE09_SURROGATE_SEEDS]

        dimming = parsed_events["dimming_events"]
        controls = parsed_events["brightening_control_events"]
        for source_index, event in enumerate(dimming):
            exceedances = sum(
                maximum is not None and maximum >= float(event["snr"])
                for maximum in maxima
            )
            p_value = (1.0 + exceedances) / 65.0
            control = _control_snr(event, controls)
            key = (target_id, campaign_hash, source_index)
            expected_rows[key] = {
                "target_id": target_id, "target_name": target_name,
                "sector_label": sector,
                "center_time_days": event["center_time_days"],
                "duration_days": event["duration_days"], "depth": event["depth"],
                "snr": event["snr"], "empirical_familywise_p": p_value,
                "matched_brightening_snr": control,
                "snr_above_matched_control": (
                    None if control is None else float(event["snr"]) - control
                ),
                "campaign_input_combined_sha256": campaign_hash,
                "search_duration_family_days": list(durations),
                "source_event_index": source_index, "event_direction": "dimming",
            }

        receipt = value.get("calibration_receipt")
        if not isinstance(receipt, Mapping) or receipt.get("schema") != PHASE09_CALIBRATION_SCHEMA:
            errors.append(f"{label} calibration receipt is missing or inconsistent")
        else:
            checks = {
                "target_id": target_id, "target_name": target_name,
                "sector_label": sector,
                "campaign_input_combined_sha256": campaign_hash,
                "surrogate_trials": 64, "dimming_events": len(dimming),
                "brightening_control_events": len(controls),
                "derived_machine_events": len(dimming),
            }
            for field, expected in checks.items():
                if receipt.get(field) != expected:
                    errors.append(f"{label} calibration receipt field {field} is inconsistent")
            if not _same(receipt.get("minimum_resolvable_familywise_p"), 1.0 / 65.0):
                errors.append(f"{label} calibration p-value resolution is inconsistent")

    if set(lock_map) != seen:
        errors.append("campaign lock targets do not match target calibrations")

    evidence_value = payload.get("candidate_evidence")
    evidence = evidence_value if isinstance(evidence_value, Mapping) else {}
    if not evidence:
        errors.append("candidate_evidence is missing or malformed")
    else:
        try:
            validate_candidate_evidence(evidence)
        except Exception as exc:
            report = getattr(exc, "report", None)
            if report is None:
                errors.append("candidate_evidence validation crashed")
            else:
                errors.extend(f"candidate_evidence: {item}" for item in report.errors)
    if evidence.get("source_commit") != payload.get("source_commit"):
        errors.append("candidate evidence and campaign source commits differ")
    if evidence.get("frozen_at_utc") != payload.get("frozen_at_utc"):
        errors.append("candidate evidence and campaign freeze timestamps differ")

    observed_value = evidence.get("machine_events")
    observed_rows = (
        list(observed_value)
        if isinstance(observed_value, Sequence)
        and not isinstance(observed_value, (str, bytes))
        else []
    )
    observed: dict[tuple[str, str, int], Mapping[str, object]] = {}
    for row in observed_rows:
        if not isinstance(row, Mapping):
            continue
        key = (
            row.get("target_id"), row.get("campaign_input_combined_sha256"),
            row.get("source_event_index"),
        )
        if isinstance(key[0], str) and isinstance(key[1], str) and isinstance(key[2], int):
            observed[key] = row
    if set(observed) != set(expected_rows):
        errors.append("derived machine event identities do not match raw calibration inputs")
    numeric = {
        "center_time_days", "duration_days", "depth", "snr",
        "empirical_familywise_p", "matched_brightening_snr",
        "snr_above_matched_control",
    }
    for key, expected in expected_rows.items():
        row = observed.get(key)
        if row is None:
            continue
        for field, value in expected.items():
            if field in numeric:
                valid = _same(row.get(field), value)
            elif field == "search_duration_family_days":
                raw = row.get(field)
                valid = (
                    isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
                    and tuple(raw) == tuple(value)
                )
            else:
                valid = row.get(field) == value
            if not valid:
                errors.append(f"{key[0]} event {key[2]} field {field} is inconsistent")

    package_hash = payload.get("package_sha256")
    expected_hash = canonical_json_sha256(
        {key: value for key, value in payload.items() if key != "package_sha256"}
    )
    if not isinstance(package_hash, str) or package_hash != expected_hash:
        errors.append("campaign evidence package SHA-256 is missing or inconsistent")

    report = CandidateCampaignValidationReport(
        protocol="HOU-EARTH Phase 0.9 blind real-campaign calibration evidence",
        accepted=not errors,
        targets=len(calibrations),
        surrogate_trials=total_surrogates,
        machine_events=len(observed_rows),
        errors=tuple(errors),
    )
    if errors:
        raise CandidateCampaignValidationError(report)
    return report
