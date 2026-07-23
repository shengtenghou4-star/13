from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from numbers import Real
from pathlib import Path
from typing import Iterable, Sequence

from .provenance import canonical_json_sha256


CANDIDATE_SCHEMA = "houearth-frozen-candidate-table-v0.8.0"
TARGET_FAMILYWISE_ALPHA = 0.05
TABLE_FDR_ALPHA = 0.10
SELECTION_RULE = (
    "one event per (target_id,campaign_input_sha256), selected by ascending "
    "target-familywise p, descending matched-control margin, descending SNR, "
    "descending depth, ascending time and source index"
)
RANKING_RULE = (
    "screened-in first; then ascending BH q and familywise p, descending "
    "matched-control margin and SNR, then deterministic target/time ties"
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True)
class BlindCandidateInput:
    """Machine-produced event evidence available before manual inspection."""

    target_id: str
    target_name: str
    sector_label: str
    center_time_days: float
    duration_days: float
    depth: float
    snr: float
    empirical_familywise_p: float
    matched_brightening_snr: float | None
    snr_above_matched_control: float | None
    campaign_input_combined_sha256: str
    search_duration_family_days: tuple[float, ...]
    source_event_index: int
    event_direction: str = "dimming"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FrozenCandidateRecord:
    candidate_id: str
    target_id: str
    target_name: str
    sector_label: str
    center_time_days: float
    duration_days: float
    depth: float
    snr: float
    empirical_familywise_p: float
    benjamini_hochberg_q: float
    matched_brightening_snr: float | None
    snr_above_matched_control: float | None
    campaign_input_combined_sha256: str
    search_duration_family_days: tuple[float, ...]
    source_event_index: int
    competing_events_considered: int
    blind_priority_rank: int
    blind_status: str
    exclusion_reasons: tuple[str, ...]
    manual_review_status: str
    astrophysical_status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FrozenCandidateTable:
    schema: str
    source_commit: str
    frozen_at_utc: str
    target_familywise_alpha: float
    table_fdr_alpha: float
    selection_rule: str
    ranking_rule: str
    candidates: tuple[FrozenCandidateRecord, ...]
    table_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number, not boolean or text")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return parsed


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _validate_utc_timestamp(value: object) -> str:
    if not isinstance(value, str) or _UTC_PATTERN.fullmatch(value) is None:
        raise ValueError("frozen_at_utc must use YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("frozen_at_utc is not a valid UTC timestamp") from exc
    return value


def benjamini_hochberg_qvalues(p_values: Sequence[float]) -> list[float]:
    """Return monotone Benjamini-Hochberg adjusted q-values.

    Inputs are target-level familywise p-values. HOU-EARTH applies this only after
    reducing each campaign-input light curve to one predeclared top dimming event.
    """
    values = [_finite_number(value, "p-value") for value in p_values]
    if any(value < 0 or value > 1 for value in values):
        raise ValueError("p-values must lie in [0, 1]")
    count = len(values)
    if count == 0:
        return []

    order = sorted(range(count), key=lambda index: (values[index], index))
    adjusted = [1.0] * count
    running = 1.0
    for reverse_rank, index in enumerate(reversed(order), start=1):
        rank = count - reverse_rank + 1
        raw = values[index] * count / rank
        running = min(running, raw, 1.0)
        adjusted[index] = running
    return adjusted


def _validated_duration_family(event: BlindCandidateInput) -> tuple[float, ...]:
    if not isinstance(event.search_duration_family_days, Sequence) or isinstance(
        event.search_duration_family_days, (str, bytes)
    ):
        raise ValueError("search_duration_family_days must be a numeric sequence")
    durations = tuple(
        _finite_number(value, "search duration")
        for value in event.search_duration_family_days
    )
    if not durations or any(value <= 0 for value in durations):
        raise ValueError("search_duration_family_days must contain positive values")
    if tuple(sorted(set(durations))) != durations:
        raise ValueError("search_duration_family_days must be sorted and unique")
    return durations


def _validate_input(event: BlindCandidateInput) -> tuple[float, ...]:
    _nonempty_string(event.target_id, "target_id")
    _nonempty_string(event.target_name, "target_name")
    _nonempty_string(event.sector_label, "sector_label")
    if event.event_direction != "dimming":
        raise ValueError("blind candidate inputs must be dimming events")

    center = _finite_number(event.center_time_days, "center_time_days")
    duration = _finite_number(event.duration_days, "duration_days")
    depth = _finite_number(event.depth, "depth")
    snr = _finite_number(event.snr, "snr")
    p_value = _finite_number(
        event.empirical_familywise_p, "empirical_familywise_p"
    )
    if duration <= 0:
        raise ValueError("duration_days must be positive")
    if depth <= 0:
        raise ValueError("depth must be positive")
    if snr < 0:
        raise ValueError("snr must be non-negative")
    if not 0 <= p_value <= 1:
        raise ValueError("empirical_familywise_p must lie in [0, 1]")
    if (
        isinstance(event.source_event_index, bool)
        or not isinstance(event.source_event_index, int)
        or event.source_event_index < 0
    ):
        raise ValueError("source_event_index must be a non-negative exact integer")
    if (
        not isinstance(event.campaign_input_combined_sha256, str)
        or _SHA256_PATTERN.fullmatch(event.campaign_input_combined_sha256) is None
    ):
        raise ValueError("campaign_input_combined_sha256 must be lowercase SHA-256")

    durations = _validated_duration_family(event)
    if not any(math.isclose(duration, value, rel_tol=0.0, abs_tol=1e-12) for value in durations):
        raise ValueError("duration_days must belong to the frozen search-duration family")

    matched_missing = event.matched_brightening_snr is None
    margin_missing = event.snr_above_matched_control is None
    if matched_missing != margin_missing:
        raise ValueError(
            "matched_brightening_snr and snr_above_matched_control must be both "
            "present or both absent"
        )
    if not matched_missing:
        matched = _finite_number(
            event.matched_brightening_snr, "matched_brightening_snr"
        )
        margin = _finite_number(
            event.snr_above_matched_control, "snr_above_matched_control"
        )
        if matched < 0:
            raise ValueError("matched_brightening_snr must be non-negative")
        if not math.isclose(snr - matched, margin, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(
                "snr_above_matched_control must equal snr - matched_brightening_snr"
            )

    # Force evaluation so malformed values cannot hide behind type annotations.
    _ = center
    return durations


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


def _candidate_id(event: BlindCandidateInput, source_commit: str) -> str:
    digest = canonical_json_sha256(
        {
            "schema": CANDIDATE_SCHEMA,
            "source_commit": source_commit,
            "target_id": event.target_id,
            "sector_label": event.sector_label,
            "center_time_days": event.center_time_days,
            "duration_days": event.duration_days,
            "depth": event.depth,
            "campaign_input_combined_sha256": event.campaign_input_combined_sha256,
            "source_event_index": event.source_event_index,
        }
    )
    return f"hou-{digest[:24]}"


def _screen_reasons(
    event: BlindCandidateInput,
    q_value: float,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if event.empirical_familywise_p > TARGET_FAMILYWISE_ALPHA:
        reasons.append("target-familywise-p-above-threshold")
    if q_value > TABLE_FDR_ALPHA:
        reasons.append("table-bh-q-above-threshold")
    if event.snr_above_matched_control is None:
        reasons.append("missing-matched-brightening-control")
    elif event.snr_above_matched_control <= 0:
        reasons.append("not-stronger-than-matched-brightening-control")
    return tuple(reasons)


def freeze_candidate_table(
    events: Iterable[BlindCandidateInput],
    *,
    source_commit: str,
    frozen_at_utc: str,
    target_familywise_alpha: float = TARGET_FAMILYWISE_ALPHA,
    table_fdr_alpha: float = TABLE_FDR_ALPHA,
) -> FrozenCandidateTable:
    """Freeze one top machine-selected dimming event per campaign input.

    The Phase 0.8 schema fixes both statistical thresholds. Human notes, plots, target
    fame, and astrophysical interpretation are deliberately absent from the input.
    """
    if not isinstance(source_commit, str) or _GIT_SHA_PATTERN.fullmatch(source_commit) is None:
        raise ValueError("source_commit must be a lowercase 40-character Git SHA")
    frozen_at_utc = _validate_utc_timestamp(frozen_at_utc)

    target_alpha = _finite_number(
        target_familywise_alpha, "target_familywise_alpha"
    )
    fdr_alpha = _finite_number(table_fdr_alpha, "table_fdr_alpha")
    if not math.isclose(
        target_alpha, TARGET_FAMILYWISE_ALPHA, rel_tol=0.0, abs_tol=1e-12
    ):
        raise ValueError("Phase 0.8 target familywise alpha is frozen at 0.05")
    if not math.isclose(fdr_alpha, TABLE_FDR_ALPHA, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("Phase 0.8 table FDR alpha is frozen at 0.10")

    grouped: dict[tuple[str, str], list[BlindCandidateInput]] = defaultdict(list)
    duration_families: set[tuple[float, ...]] = set()
    hash_owners: dict[str, str] = {}
    for event in events:
        duration_families.add(_validate_input(event))
        owner = hash_owners.setdefault(
            event.campaign_input_combined_sha256, event.target_id
        )
        if owner != event.target_id:
            raise ValueError("one campaign-input hash cannot belong to multiple targets")
        grouped[(event.target_id, event.campaign_input_combined_sha256)].append(event)
    if len(duration_families) > 1:
        raise ValueError("all events in one frozen table must share one duration family")

    selected: list[tuple[BlindCandidateInput, int]] = []
    for group in grouped.values():
        target_names = {event.target_name for event in group}
        sector_labels = {event.sector_label for event in group}
        source_indices = [event.source_event_index for event in group]
        if len(target_names) != 1:
            raise ValueError("one campaign input cannot contain multiple target names")
        if len(sector_labels) != 1:
            raise ValueError("one campaign input cannot contain multiple sector labels")
        if len(set(source_indices)) != len(source_indices):
            raise ValueError("source_event_index must be unique within a campaign input")
        winner = min(group, key=_selection_key)
        selected.append((winner, len(group)))
    selected.sort(
        key=lambda item: (
            item[0].target_id,
            item[0].campaign_input_combined_sha256,
            item[0].center_time_days,
        )
    )

    q_values = benjamini_hochberg_qvalues(
        [event.empirical_familywise_p for event, _ in selected]
    )
    provisional: list[dict[str, object]] = []
    for (event, competing_count), q_value in zip(selected, q_values):
        reasons = _screen_reasons(event, q_value)
        provisional.append(
            {
                "event": event,
                "competing_count": competing_count,
                "q_value": q_value,
                "reasons": reasons,
            }
        )

    provisional.sort(
        key=lambda row: (
            bool(row["reasons"]),
            float(row["q_value"]),
            float(row["event"].empirical_familywise_p),
            -(
                float(row["event"].snr_above_matched_control)
                if row["event"].snr_above_matched_control is not None
                else float("-inf")
            ),
            -float(row["event"].snr),
            row["event"].target_id,
            float(row["event"].center_time_days),
        )
    )

    records: list[FrozenCandidateRecord] = []
    for rank, row in enumerate(provisional, start=1):
        event = row["event"]
        reasons = tuple(row["reasons"])
        records.append(
            FrozenCandidateRecord(
                candidate_id=_candidate_id(event, source_commit),
                target_id=event.target_id,
                target_name=event.target_name,
                sector_label=event.sector_label,
                center_time_days=float(event.center_time_days),
                duration_days=float(event.duration_days),
                depth=float(event.depth),
                snr=float(event.snr),
                empirical_familywise_p=float(event.empirical_familywise_p),
                benjamini_hochberg_q=float(row["q_value"]),
                matched_brightening_snr=(
                    None
                    if event.matched_brightening_snr is None
                    else float(event.matched_brightening_snr)
                ),
                snr_above_matched_control=(
                    None
                    if event.snr_above_matched_control is None
                    else float(event.snr_above_matched_control)
                ),
                campaign_input_combined_sha256=event.campaign_input_combined_sha256,
                search_duration_family_days=tuple(
                    float(value) for value in event.search_duration_family_days
                ),
                source_event_index=event.source_event_index,
                competing_events_considered=int(row["competing_count"]),
                blind_priority_rank=rank,
                blind_status="screened-in" if not reasons else "screened-out",
                exclusion_reasons=reasons,
                manual_review_status="unopened",
                astrophysical_status="unclassified",
            )
        )

    hash_payload = {
        "schema": CANDIDATE_SCHEMA,
        "source_commit": source_commit,
        "frozen_at_utc": frozen_at_utc,
        "target_familywise_alpha": TARGET_FAMILYWISE_ALPHA,
        "table_fdr_alpha": TABLE_FDR_ALPHA,
        "selection_rule": SELECTION_RULE,
        "ranking_rule": RANKING_RULE,
        "candidates": [record.to_dict() for record in records],
    }
    table_hash = canonical_json_sha256(hash_payload)
    return FrozenCandidateTable(
        schema=CANDIDATE_SCHEMA,
        source_commit=source_commit,
        frozen_at_utc=frozen_at_utc,
        target_familywise_alpha=TARGET_FAMILYWISE_ALPHA,
        table_fdr_alpha=TABLE_FDR_ALPHA,
        selection_rule=SELECTION_RULE,
        ranking_rule=RANKING_RULE,
        candidates=tuple(records),
        table_sha256=table_hash,
    )


def write_frozen_candidate_table(
    table: FrozenCandidateTable,
    output_dir: str | Path,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "candidate_table.json").write_text(
        __import__("json").dumps(table.to_dict(), indent=2), encoding="utf-8"
    )
    rows = [record.to_dict() for record in table.candidates]
    if not rows:
        (output / "candidate_table.csv").write_text("", encoding="utf-8")
        return
    with (output / "candidate_table.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "search_duration_family_days": ";".join(
                        str(value) for value in row["search_duration_family_days"]
                    ),
                    "exclusion_reasons": ";".join(row["exclusion_reasons"]),
                }
            )
