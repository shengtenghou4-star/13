from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from numbers import Real
from typing import Mapping, Sequence

from .candidate_freeze import (
    CANDIDATE_SCHEMA,
    RANKING_RULE,
    SELECTION_RULE,
    TABLE_FDR_ALPHA,
    TARGET_FAMILYWISE_ALPHA,
    benjamini_hochberg_qvalues,
)
from .provenance import canonical_json_sha256


_CANDIDATE_ID_PATTERN = re.compile(r"^hou-[0-9a-f]{24}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


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


def _exact_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _valid_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or _UTC_PATTERN.fullmatch(value) is None:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


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
        number = _finite_number(item)
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
    *,
    p_value: float,
    q_value: float,
    margin_present: bool,
    margin: float | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if p_value > TARGET_FAMILYWISE_ALPHA:
        reasons.append("target-familywise-p-above-threshold")
    if q_value > TABLE_FDR_ALPHA:
        reasons.append("table-bh-q-above-threshold")
    if not margin_present:
        reasons.append("missing-matched-brightening-control")
    elif margin is not None and margin <= 0:
        reasons.append("not-stronger-than-matched-brightening-control")
    return tuple(reasons)


def validate_frozen_candidate_table(
    payload: Mapping[str, object],
) -> CandidateProtocolValidationReport:
    """Recompute all frozen candidate-table invariants from serialized evidence."""
    errors: list[str] = []
    if payload.get("schema") != CANDIDATE_SCHEMA:
        errors.append("candidate schema is missing or inconsistent")

    source_commit = payload.get("source_commit")
    if not isinstance(source_commit, str) or _GIT_SHA_PATTERN.fullmatch(source_commit) is None:
        errors.append("source_commit is missing or invalid")
        source_commit = "0" * 40

    if not _valid_utc_timestamp(payload.get("frozen_at_utc")):
        errors.append("frozen_at_utc is missing or not canonical UTC")

    target_alpha = _finite_number(payload.get("target_familywise_alpha"))
    fdr_alpha = _finite_number(payload.get("table_fdr_alpha"))
    if target_alpha is None or not math.isclose(
        target_alpha, TARGET_FAMILYWISE_ALPHA, rel_tol=0.0, abs_tol=1e-12
    ):
        errors.append("target familywise alpha is not frozen at 0.05")
    if fdr_alpha is None or not math.isclose(
        fdr_alpha, TABLE_FDR_ALPHA, rel_tol=0.0, abs_tol=1e-12
    ):
        errors.append("table FDR alpha is not frozen at 0.10")
    if payload.get("selection_rule") != SELECTION_RULE:
        errors.append("selection_rule is missing or inconsistent")
    if payload.get("ranking_rule") != RANKING_RULE:
        errors.append("ranking_rule is missing or inconsistent")

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
    hash_owners: dict[str, str] = {}
    duration_families: set[tuple[float, ...]] = set()
    p_values: list[float] = []

    for index, record in enumerate(candidates, start=1):
        label = str(record.get("candidate_id", f"candidate-{index}"))
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str) or _CANDIDATE_ID_PATTERN.fullmatch(
            candidate_id
        ) is None:
            errors.append(f"{label}: candidate_id is invalid")
        elif candidate_id in candidate_ids:
            errors.append(f"{label}: candidate_id is duplicated")
        else:
            candidate_ids.add(candidate_id)

        for field in ("target_id", "target_name", "sector_label"):
            if not _valid_nonempty_string(record.get(field)):
                errors.append(f"{label}: {field} is invalid")
        target_id = record.get("target_id")
        campaign_hash = record.get("campaign_input_combined_sha256")
        if not isinstance(campaign_hash, str) or _SHA256_PATTERN.fullmatch(
            campaign_hash
        ) is None:
            errors.append(f"{label}: campaign input hash is invalid")
        if isinstance(target_id, str) and isinstance(campaign_hash, str):
            key = (target_id, campaign_hash)
            if key in campaign_keys:
                errors.append(f"{label}: duplicate campaign-input candidate")
            campaign_keys.add(key)
            owner = hash_owners.setdefault(campaign_hash, target_id)
            if owner != target_id:
                errors.append(f"{label}: campaign hash belongs to multiple targets")

        expected_id = _candidate_id(record, source_commit)
        if expected_id is None or candidate_id != expected_id:
            errors.append(f"{label}: candidate_id does not match frozen evidence")

        rank = _exact_int(record.get("blind_priority_rank"))
        if rank != index:
            errors.append(f"{label}: blind priority rank is not sequential")
        competing = _exact_int(record.get("competing_events_considered"))
        if competing is None or competing < 1:
            errors.append(f"{label}: competing event count is invalid")
        source_index = _exact_int(record.get("source_event_index"))
        if source_index is None or source_index < 0:
            errors.append(f"{label}: source event index is invalid")

        center = _finite_number(record.get("center_time_days"))
        duration = _finite_number(record.get("duration_days"))
        depth = _finite_number(record.get("depth"))
        snr = _finite_number(record.get("snr"))
        if center is None:
            errors.append(f"{label}: center time is invalid")
        if duration is None or duration <= 0:
            errors.append(f"{label}: duration is invalid")
        if depth is None or depth <= 0:
            errors.append(f"{label}: depth is invalid")
        if snr is None or snr < 0:
            errors.append(f"{label}: SNR is invalid")

        family = _duration_family(record.get("search_duration_family_days"))
        if family is None:
            errors.append(f"{label}: duration family is invalid")
        else:
            duration_families.add(family)
            if duration is not None and not any(
                math.isclose(duration, value, rel_tol=0.0, abs_tol=1e-12)
                for value in family
            ):
                errors.append(f"{label}: event duration is outside the search family")

        p_value = _finite_number(record.get("empirical_familywise_p"))
        q_value = _finite_number(record.get("benjamini_hochberg_q"))
        if p_value is None or not 0 <= p_value <= 1:
            errors.append(f"{label}: empirical familywise p is invalid")
            p_values.append(1.0)
            p_for_reasons = 1.0
        else:
            p_values.append(p_value)
            p_for_reasons = p_value
        if q_value is None or not 0 <= q_value <= 1:
            errors.append(f"{label}: BH q-value is invalid")
            q_for_reasons = 1.0
        else:
            q_for_reasons = q_value

        matched_value = record.get("matched_brightening_snr")
        margin_value = record.get("snr_above_matched_control")
        matched_present = matched_value is not None
        margin_present = margin_value is not None
        matched = None if not matched_present else _finite_number(matched_value)
        margin = None if not margin_present else _finite_number(margin_value)
        if matched_present != margin_present:
            errors.append(f"{label}: matched control and margin presence disagree")
        if matched_present and (matched is None or matched < 0):
            errors.append(f"{label}: matched brightening SNR is invalid")
        if margin_present and margin is None:
            errors.append(f"{label}: matched-control margin is invalid")
        if (
            matched is not None
            and margin is not None
            and snr is not None
            and not math.isclose(snr - matched, margin, rel_tol=1e-12, abs_tol=1e-12)
        ):
            errors.append(f"{label}: matched-control arithmetic is inconsistent")

        reasons = _string_sequence(record.get("exclusion_reasons"))
        expected_reasons = _expected_reasons(
            p_value=p_for_reasons,
            q_value=q_for_reasons,
            margin_present=margin_present,
            margin=margin,
        )
        if reasons is None:
            errors.append(f"{label}: exclusion reasons are malformed")
            reasons = ()
        if reasons != expected_reasons:
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
        observed_q = _finite_number(record.get("benjamini_hochberg_q"))
        if observed_q is None or not math.isclose(
            observed_q, expected_q, rel_tol=0.0, abs_tol=1e-12
        ):
            errors.append(
                f"{record.get('candidate_id', 'unknown')}: BH q-value is inconsistent"
            )

    def ranking_key(record: Mapping[str, object]) -> tuple[object, ...]:
        reasons = _string_sequence(record.get("exclusion_reasons")) or ()
        q_value = _finite_number(record.get("benjamini_hochberg_q"))
        p_value = _finite_number(record.get("empirical_familywise_p"))
        margin = _finite_number(record.get("snr_above_matched_control"))
        snr_value = _finite_number(record.get("snr"))
        center_value = _finite_number(record.get("center_time_days"))
        return (
            bool(reasons),
            1.0 if q_value is None else q_value,
            1.0 if p_value is None else p_value,
            -(float("-inf") if margin is None else margin),
            -(float("-inf") if snr_value is None else snr_value),
            str(record.get("target_id", "")),
            float("inf") if center_value is None else center_value,
        )

    if list(candidates) != sorted(candidates, key=ranking_key):
        errors.append("candidate rows are not in the frozen blind ranking order")

    reported_hash = payload.get("table_sha256")
    hash_payload = {key: value for key, value in payload.items() if key != "table_sha256"}
    recomputed_hash = canonical_json_sha256(hash_payload)
    if not isinstance(reported_hash, str) or _SHA256_PATTERN.fullmatch(
        reported_hash
    ) is None:
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
