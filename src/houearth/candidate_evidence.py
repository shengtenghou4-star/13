from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, fields
from numbers import Real
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .candidate_freeze import (
    BlindCandidateInput,
    FrozenCandidateTable,
    freeze_candidate_table,
    write_frozen_candidate_table,
)
from .candidate_protocol_validation import validate_frozen_candidate_table
from .provenance import canonical_json_sha256


CANDIDATE_EVIDENCE_SCHEMA = "houearth-candidate-evidence-package-v0.8.0"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_EVENT_FIELDS = frozenset(field.name for field in fields(BlindCandidateInput))


@dataclass(frozen=True)
class FrozenCandidateEvidence:
    schema: str
    source_commit: str
    frozen_at_utc: str
    machine_events: tuple[BlindCandidateInput, ...]
    machine_events_sha256: str
    candidate_table: FrozenCandidateTable
    package_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateEvidenceValidationReport:
    protocol: str
    accepted: bool
    machine_events: int
    campaign_inputs: int
    candidates: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CandidateEvidenceValidationError(ValueError):
    def __init__(self, report: CandidateEvidenceValidationReport):
        self.report = report
        super().__init__("; ".join(report.errors))


def _event_stream_key(event: BlindCandidateInput) -> tuple[object, ...]:
    return (
        event.target_id,
        event.campaign_input_combined_sha256,
        event.source_event_index,
        float(event.center_time_days),
        float(event.duration_days),
        float(event.depth),
        float(event.snr),
        float(event.empirical_familywise_p),
    )


def _selection_key(event: BlindCandidateInput) -> tuple[object, ...]:
    margin = (
        float(event.snr_above_matched_control)
        if event.snr_above_matched_control is not None
        else float("-inf")
    )
    return (
        float(event.empirical_familywise_p),
        -margin,
        -float(event.snr),
        -float(event.depth),
        float(event.center_time_days),
        int(event.source_event_index),
    )


def _package_hash_payload(
    *,
    source_commit: str,
    frozen_at_utc: str,
    machine_events: Sequence[BlindCandidateInput] | Sequence[Mapping[str, object]],
    machine_events_sha256: str,
    candidate_table: FrozenCandidateTable | Mapping[str, object],
) -> dict[str, object]:
    event_rows = [
        event.to_dict() if isinstance(event, BlindCandidateInput) else dict(event)
        for event in machine_events
    ]
    table_payload = (
        candidate_table.to_dict()
        if isinstance(candidate_table, FrozenCandidateTable)
        else dict(candidate_table)
    )
    return {
        "schema": CANDIDATE_EVIDENCE_SCHEMA,
        "source_commit": source_commit,
        "frozen_at_utc": frozen_at_utc,
        "machine_events": event_rows,
        "machine_events_sha256": machine_events_sha256,
        "candidate_table": table_payload,
    }


def freeze_candidate_evidence(
    events: Iterable[BlindCandidateInput],
    *,
    source_commit: str,
    frozen_at_utc: str,
) -> FrozenCandidateEvidence:
    """Freeze the complete machine event stream and its selected blind table together."""
    materialized = tuple(events)
    table = freeze_candidate_table(
        materialized,
        source_commit=source_commit,
        frozen_at_utc=frozen_at_utc,
    )
    ordered_events = tuple(sorted(materialized, key=_event_stream_key))
    event_hash = canonical_json_sha256(
        [event.to_dict() for event in ordered_events]
    )
    package_payload = _package_hash_payload(
        source_commit=source_commit,
        frozen_at_utc=frozen_at_utc,
        machine_events=ordered_events,
        machine_events_sha256=event_hash,
        candidate_table=table,
    )
    package_hash = canonical_json_sha256(package_payload)
    return FrozenCandidateEvidence(
        schema=CANDIDATE_EVIDENCE_SCHEMA,
        source_commit=source_commit,
        frozen_at_utc=frozen_at_utc,
        machine_events=ordered_events,
        machine_events_sha256=event_hash,
        candidate_table=table,
        package_sha256=package_hash,
    )


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _exact_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _closed_event_row(row: Mapping[object, object]) -> tuple[list[str], list[str]]:
    string_keys = {key for key in row if isinstance(key, str)}
    missing = sorted(_EVENT_FIELDS - string_keys)
    extra = sorted(string_keys - _EVENT_FIELDS)
    extra.extend(repr(key) for key in row if not isinstance(key, str))
    return missing, extra


def _event_from_row(
    row: Mapping[str, object],
    *,
    source_commit: str,
    frozen_at_utc: str,
) -> BlindCandidateInput | None:
    try:
        event = BlindCandidateInput(
            target_id=row["target_id"],
            target_name=row["target_name"],
            sector_label=row["sector_label"],
            center_time_days=row["center_time_days"],
            duration_days=row["duration_days"],
            depth=row["depth"],
            snr=row["snr"],
            empirical_familywise_p=row["empirical_familywise_p"],
            matched_brightening_snr=row["matched_brightening_snr"],
            snr_above_matched_control=row["snr_above_matched_control"],
            campaign_input_combined_sha256=row[
                "campaign_input_combined_sha256"
            ],
            search_duration_family_days=tuple(
                row["search_duration_family_days"]
            ),
            source_event_index=row["source_event_index"],
            event_direction=row["event_direction"],
        )
        # Singleton freezing exercises the strict field validator without relying on the
        # multi-event winner chosen by the production table builder.
        freeze_candidate_table(
            [event],
            source_commit=source_commit,
            frozen_at_utc=frozen_at_utc,
        )
    except (KeyError, TypeError, ValueError):
        return None
    return event


def _same_number(left: object, right: object) -> bool:
    left_value = _finite_number(left)
    right_value = _finite_number(right)
    if left_value is None or right_value is None:
        return left is None and right is None
    return math.isclose(left_value, right_value, rel_tol=1e-12, abs_tol=1e-12)


def validate_candidate_evidence(
    payload: Mapping[str, object],
) -> CandidateEvidenceValidationReport:
    """Validate that the blind table was selected from the complete frozen event stream."""
    errors: list[str] = []
    expected_package_fields = {
        "schema",
        "source_commit",
        "frozen_at_utc",
        "machine_events",
        "machine_events_sha256",
        "candidate_table",
        "package_sha256",
    }
    actual_package_fields = {key for key in payload if isinstance(key, str)}
    missing_package = sorted(expected_package_fields - actual_package_fields)
    extra_package = sorted(actual_package_fields - expected_package_fields)
    extra_package.extend(repr(key) for key in payload if not isinstance(key, str))
    if missing_package:
        errors.append(
            f"evidence package is missing fields: {', '.join(missing_package)}"
        )
    if extra_package:
        errors.append(
            f"evidence package contains undeclared fields: {', '.join(extra_package)}"
        )
    if payload.get("schema") != CANDIDATE_EVIDENCE_SCHEMA:
        errors.append("evidence package schema is missing or inconsistent")

    source_commit = payload.get("source_commit")
    if not isinstance(source_commit, str) or _GIT_SHA_PATTERN.fullmatch(source_commit) is None:
        errors.append("evidence source_commit is missing or invalid")
        source_commit = "0" * 40
    frozen_at_utc = payload.get("frozen_at_utc")
    if not isinstance(frozen_at_utc, str):
        errors.append("evidence frozen_at_utc is missing or invalid")
        frozen_at_utc = "1970-01-01T00:00:00Z"

    event_value = payload.get("machine_events")
    event_rows: list[Mapping[str, object]] = []
    if isinstance(event_value, Sequence) and not isinstance(event_value, (str, bytes)):
        raw_events = list(event_value)
        event_rows = [row for row in raw_events if isinstance(row, Mapping)]
        if len(event_rows) != len(raw_events):
            errors.append("machine_events contains malformed non-object entries")
    else:
        errors.append("machine_events is missing or malformed")

    events: list[BlindCandidateInput] = []
    for index, row in enumerate(event_rows):
        missing, extra = _closed_event_row(row)
        label = f"machine event {index}"
        if missing:
            errors.append(f"{label} is missing fields: {', '.join(missing)}")
        if extra:
            errors.append(f"{label} contains undeclared fields: {', '.join(extra)}")
        event = _event_from_row(
            row,
            source_commit=source_commit,
            frozen_at_utc=frozen_at_utc,
        )
        if event is None:
            errors.append(f"{label} is not valid machine evidence")
        else:
            events.append(event)

    if events and events != sorted(events, key=_event_stream_key):
        errors.append("machine event stream is not in canonical order")

    observed_event_hash = payload.get("machine_events_sha256")
    expected_event_hash = canonical_json_sha256([dict(row) for row in event_rows])
    if not isinstance(observed_event_hash, str) or _SHA256_PATTERN.fullmatch(
        observed_event_hash
    ) is None:
        errors.append("machine_events_sha256 is missing or invalid")
    elif observed_event_hash != expected_event_hash:
        errors.append("machine_events_sha256 does not match the event stream")

    table_value = payload.get("candidate_table")
    if not isinstance(table_value, Mapping):
        errors.append("candidate_table is missing or malformed")
        table_payload: Mapping[str, object] = {}
    else:
        table_payload = table_value
        try:
            validate_frozen_candidate_table(table_payload)
        except Exception as exc:
            report = getattr(exc, "report", None)
            if report is None:
                errors.append("candidate_table validation crashed")
            else:
                errors.extend(
                    f"candidate_table: {error}" for error in report.errors
                )

    if table_payload.get("source_commit") != source_commit:
        errors.append("candidate table and event package source commits differ")
    if table_payload.get("frozen_at_utc") != frozen_at_utc:
        errors.append("candidate table and event package freeze timestamps differ")

    groups: dict[tuple[str, str], list[BlindCandidateInput]] = {}
    hash_owners: dict[str, str] = {}
    duration_families: set[tuple[float, ...]] = set()
    for event in events:
        key = (event.target_id, event.campaign_input_combined_sha256)
        groups.setdefault(key, []).append(event)
        owner = hash_owners.setdefault(
            event.campaign_input_combined_sha256, event.target_id
        )
        if owner != event.target_id:
            errors.append("one campaign-input hash belongs to multiple targets")
        duration_families.add(tuple(event.search_duration_family_days))
    if len(duration_families) > 1:
        errors.append("machine event stream mixes search-duration families")

    expected_winners: dict[tuple[str, str], tuple[BlindCandidateInput, int]] = {}
    for key, group in groups.items():
        if len({event.target_name for event in group}) != 1:
            errors.append(f"{key[0]}: campaign input mixes target names")
        if len({event.sector_label for event in group}) != 1:
            errors.append(f"{key[0]}: campaign input mixes sector labels")
        indices = [event.source_event_index for event in group]
        if len(indices) != len(set(indices)):
            errors.append(f"{key[0]}: campaign input repeats source event indices")
        expected_winners[key] = (min(group, key=_selection_key), len(group))

    candidate_value = table_payload.get("candidates", [])
    candidate_rows = (
        [row for row in candidate_value if isinstance(row, Mapping)]
        if isinstance(candidate_value, Sequence)
        and not isinstance(candidate_value, (str, bytes))
        else []
    )
    observed_candidates: dict[tuple[str, str], Mapping[str, object]] = {}
    for row in candidate_rows:
        target_id = row.get("target_id")
        input_hash = row.get("campaign_input_combined_sha256")
        if isinstance(target_id, str) and isinstance(input_hash, str):
            observed_candidates[(target_id, input_hash)] = row

    if set(observed_candidates) != set(expected_winners):
        errors.append("candidate campaign inputs do not match the frozen event stream")

    copied_fields = (
        "target_id",
        "target_name",
        "sector_label",
        "center_time_days",
        "duration_days",
        "depth",
        "snr",
        "empirical_familywise_p",
        "matched_brightening_snr",
        "snr_above_matched_control",
        "campaign_input_combined_sha256",
        "source_event_index",
    )
    for key, (winner, competing_count) in expected_winners.items():
        row = observed_candidates.get(key)
        if row is None:
            continue
        winner_dict = winner.to_dict()
        for field in copied_fields:
            if field in (
                "center_time_days",
                "duration_days",
                "depth",
                "snr",
                "empirical_familywise_p",
                "matched_brightening_snr",
                "snr_above_matched_control",
            ):
                if not _same_number(row.get(field), winner_dict[field]):
                    errors.append(f"{key[0]}: selected winner field {field} is inconsistent")
            elif row.get(field) != winner_dict[field]:
                errors.append(f"{key[0]}: selected winner field {field} is inconsistent")
        row_family = tuple(row.get("search_duration_family_days", ()))
        if row_family != tuple(winner.search_duration_family_days):
            errors.append(f"{key[0]}: selected winner duration family is inconsistent")
        if _exact_int(row.get("competing_events_considered")) != competing_count:
            errors.append(f"{key[0]}: competing event count does not match event stream")

    package_hash = payload.get("package_sha256")
    expected_package_hash = canonical_json_sha256(
        {
            key: value
            for key, value in payload.items()
            if key != "package_sha256"
        }
    )
    if not isinstance(package_hash, str) or _SHA256_PATTERN.fullmatch(package_hash) is None:
        errors.append("package_sha256 is missing or invalid")
    elif package_hash != expected_package_hash:
        errors.append("package_sha256 does not match the evidence package")

    report = CandidateEvidenceValidationReport(
        protocol="HOU-EARTH Phase 0.8 complete machine-event evidence package",
        accepted=not errors,
        machine_events=len(event_rows),
        campaign_inputs=len(groups),
        candidates=len(candidate_rows),
        errors=tuple(errors),
    )
    if errors:
        raise CandidateEvidenceValidationError(report)
    return report


def write_candidate_evidence(
    evidence: FrozenCandidateEvidence,
    output_dir: str | Path,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_frozen_candidate_table(evidence.candidate_table, output)
    (output / "machine_events.json").write_text(
        __import__("json").dumps(
            [event.to_dict() for event in evidence.machine_events], indent=2
        ),
        encoding="utf-8",
    )
    (output / "candidate_evidence.json").write_text(
        __import__("json").dumps(evidence.to_dict(), indent=2),
        encoding="utf-8",
    )
