from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from .candidate_freeze import CANDIDATE_SCHEMA, benjamini_hochberg_qvalues
from .provenance import canonical_json_sha256


_CANDIDATE_ID_PATTERN = re.compile(r"^hou-[0-9a-f]{24}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class CandidateProtocolValidationReport:
    protocol: str
    accepted: bool
    candidates: int
    screened_in: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CandidateProtocolValidationError(ValueError):
    def __init__(self, report: CandidateProtocolValidationReport):
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


def _string_sequence(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _duration_family(value: object) -> tuple[float, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    parsed: list[float] = []
    for item in value:
        number = _finite_float(item)
        if number is None or number <= 0:
            return None
        parsed.append(number)
    result = tuple(parsed)
    if not result or tuple(sorted(set(result))) != result:
        return None
    return result


def _candidate_id(record: Mapping[str, object], source_commit: str) -> str | None:
    required = (
        "target_id",
        "sector_label",
        "center_time_days",
        "duration_days",
        "depth",
        "campaign_input_combined_sha256",
        "source_event_index",
    )
    if any(field not in record for field in required):
        return None
    digest = canonical_json_sha256(
        {
            "schema": CANDIDATE_SCHEMA,
            "source_commit": source_commit,
            "target_id": record["target_id"],
            "sector_label": record["sector_label"],
            "center_time_days": record["center_time_days"],
            "duration_days": record["duration_days"],
            "depth": record["depth"],
            "campaign_input_combined_sha256": record[
                "campaign_input_combined_sha256"
            ],
            "source_event_index": record["source_event_index"],
        }
    )
    return f"hou-{digest[:24]}"


def _expected_reasons(
    record: Mapping[str, object],
    *,
    target_alpha: float,
    fdr_alpha: float,
) -> tuple[str, ...] | None:
    p_value = _finite_float(record.get("empirical_familywise_p"))
    q_value = _finite_float(record.get("benjamini_hochberg_q"))
    if p_value is None or not 0 <= p_value <= 1:
        return None
    if q_value is None or not 0 <= q_value <= 1:
        return None
    margin_value = record.get("snr_above_matched_control")
    margin = None if margin_value is None else _finite_float(margin_value)
    if margin_value is not None and margin is None:
        return None

    reasons: list[str] = []
    if p_value > target_alpha:
        reasons.append("target-familywise-p-above-threshold")
    if q_value > fdr_alpha:
        reasons.append("table-bh-q-above-threshold")
    if margin_value is None:
        reasons.append("missing-matched-brightening-control")
    elif margin is not None and margin <= 0:
        reasons.append("not-stronger-than-matched-brightening-control")
    return tuple(reasons)


def validate_frozen_candidate_table(
    payload: Mapping[str, object],
) -> CandidateProtocolValidationReport:
    """Recompute the blind-table invariants from a serialized evidence payload."""
    errors: list[str] = []
    if payload.get("schema") != CANDIDATE_SCHEMA:
        errors.append("candidate schema is missing or inconsistent")

    source_commit = payload.get("source_commit")
    if not isinstance(source_commit, str) or not _GIT_SHA_PATTERN.fullmatch(source_commit):
        errors.append("source_commit is missing or invalid")
        source_commit = "0" * 40

    target_alpha = _finite_float(payload.get("target_familywise_alpha"))
    fdr_alpha = _finite_float(payload.get("table_fdr_alpha"))
    if target_alpha is None or not 0 < target_alpha < 1:
        errors.append("target_familywise_alpha is invalid")
        target_alpha = 0.05
    if fdr_alpha is None or not 0 < fdr_alpha < 1:
        errors.append("table_fdr_alpha is invalid")
        fdr_alpha = 0.10

    for field in ("frozen_at_utc", "selection_rule", "ranking_rule"):
        if not isinstance(payload.get(field), str) or not str(payload.get(field)).strip():
            errors.append(f"{field} is missing or empty")

    candidate_value = payload.get("candidates", [])
    if isinstance(candidate_value, Sequence) and not isinstance(
        candidate_value, (str, bytes)
    ):
        candidate_items = list(candidate_value)
        candidates = [item for item in candidate_items if isinstance(item, Mapping)]
        if len(candidates) != len(candidate_items):
            errors.append("candidates contains malformed non-object entries")
    else:
        candidates = []
        errors.append("candidates is missing or malformed")

    candidate_ids: set[str] = set()
    campaign_keys: set[tuple[str, str]] = set()
    duration_families: set[tuple[float, ...]] = set()
    p_values: list[float] = []
    expected_reason_rows: list[tuple[str, ...] | None] = []

    for index, record in enumerate(candidates, start=1):
        label = str(record.get("candidate_id", f"candidate-{index}"))
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str) or not _CANDIDATE_ID_PATTERN.fullmatch(
            candidate_id
        ):
            errors.append(f"{label}: candidate_id is invalid")
        elif candidate_id in candidate_ids:
            errors.append(f"{label}: candidate_id is duplicated")
        else:
            candidate_ids.add(candidate_id)
        expected_id = _candidate_id(record, source_commit)
        if expected_id is None or candidate_id != expected_id:
            errors.append(f"{label}: candidate_id does not match frozen evidence")

        target_id = record.get("target_id")
        campaign_hash = record.get("campaign_input_combined_sha256")
        if not isinstance(target_id, str) or not target_id.strip():
            errors.append(f"{label}: target_id is invalid")
        if not isinstance(campaign_hash, str) or not _SHA256_PATTERN.fullmatch(
            campaign_hash
        ):
            errors.append(f"{label}: campaign input hash is invalid")
        if isinstance(target_id, str) and isinstance(campaign_hash, str):
            key = (target_id, campaign_hash)
            if key in campaign_keys:
                errors.append(f"{label}: duplicate campaign-input candidate")
            campaign_keys.add(key)

        rank = _exact_int(record.get("blind_priority_rank"))
        if rank != index:
            errors.append(f"{label}: blind priority rank is not sequential")
        competing = _exact_int(record.get("competing_events_considered"))
        if competing is None or competing < 1:
            errors.append(f"{label}: competing event count is invalid")
        source_index = _exact_int(record.get("source_event_index"))
        if source_index is None or source_index < 0:
            errors.append(f"{label}: source event index is invalid")

        family = _duration_family(record.get("search_duration_family_days"))
        if family is None:
            errors.append(f"{label}: duration family is invalid")
        else:
            duration_families.add(family)

        p_value = _finite_float(record.get("empirical_familywise_p"))
        if p_value is None or not 0 <= p_value <= 1:
            errors.append(f"{label}: empirical familywise p is invalid")
            p_values.append(1.0)
        else:
            p_values.append(p_value)

        reasons = _string_sequence(record.get("exclusion_reasons"))
        expected_reasons = _expected_reasons(
            record,
            target_alpha=target_alpha,
            fdr_alpha=fdr_alpha,
        )
        expected_reason_rows.append(expected_reasons)
        if reasons is None:
            errors.append(f"{label}: exclusion reasons are malformed")
            reasons = ()
        if expected_reasons is None or reasons != expected_reasons:
            errors.append(f"{label}: exclusion reasons do not match machine evidence")

        expected_status = "screened-in" if not reasons else "screened-out"
        if record.get("blind_status") != expected_status:
            errors.append(f"{label}: blind status is inconsistent")
        if record.get("manual_review_status") != "unopened":
            errors.append(f"{label}: table was not frozen before manual review")
        if record.get("astrophysical_status") != "unclassified":
            errors.append(f"{label}: astrophysical status was assigned before freeze")

    if len(duration_families) > 1:
        errors.append("candidate table mixes multiple search-duration families")

    recomputed_q = benjamini_hochberg_qvalues(p_values)
    for record, expected_q in zip(candidates, recomputed_q):
        observed_q = _finite_float(record.get("benjamini_hochberg_q"))
        if observed_q is None or not math.isclose(
            observed_q, expected_q, rel_tol=0.0, abs_tol=1e-12
        ):
            errors.append(
                f"{record.get('candidate_id', 'unknown')}: BH q-value is inconsistent"
            )

    def ranking_key(record: Mapping[str, object]) -> tuple[object, ...]:
        reasons = _string_sequence(record.get("exclusion_reasons")) or ()
        q_value = _finite_float(record.get("benjamini_hochberg_q"))
        p_value = _finite_float(record.get("empirical_familywise_p"))
        margin = _finite_float(record.get("snr_above_matched_control"))
        snr = _finite_float(record.get("snr"))
        center = _finite_float(record.get("center_time_days"))
        return (
            bool(reasons),
            1.0 if q_value is None else q_value,
            1.0 if p_value is None else p_value,
            -(float("-inf") if margin is None else margin),
            -(float("-inf") if snr is None else snr),
            str(record.get("target_id", "")),
            float("inf") if center is None else center,
        )

    if list(candidates) != sorted(candidates, key=ranking_key):
        errors.append("candidate rows are not in the frozen blind ranking order")

    reported_hash = payload.get("table_sha256")
    hash_payload = {key: value for key, value in payload.items() if key != "table_sha256"}
    recomputed_hash = canonical_json_sha256(hash_payload)
    if not isinstance(reported_hash, str) or not _SHA256_PATTERN.fullmatch(
        reported_hash
    ):
        errors.append("table_sha256 is missing or invalid")
    elif reported_hash != recomputed_hash:
        errors.append("table_sha256 does not match candidate payload")

    screened_in = sum(
        record.get("blind_status") == "screened-in" for record in candidates
    )
    report = CandidateProtocolValidationReport(
        protocol="HOU-EARTH Phase 0.8 frozen blind candidate table",
        accepted=not errors,
        candidates=len(candidates),
        screened_in=screened_in,
        errors=tuple(errors),
    )
    if errors:
        raise CandidateProtocolValidationError(report)
    return report
