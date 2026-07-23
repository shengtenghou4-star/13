from dataclasses import replace

import pytest

from houearth.candidate_freeze import (
    BlindCandidateInput,
    benjamini_hochberg_qvalues,
    freeze_candidate_table,
)


SOURCE_COMMIT = "a" * 40
SEARCH_DURATIONS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)


def event(
    target_id: str,
    *,
    campaign_hash: str,
    p_value: float,
    snr: float,
    margin: float | None,
    center: float,
    source_index: int,
) -> BlindCandidateInput:
    matched = None if margin is None else snr - margin
    return BlindCandidateInput(
        target_id=target_id,
        target_name=target_id.upper(),
        sector_label="1",
        center_time_days=center,
        duration_days=0.08,
        depth=0.00012,
        snr=snr,
        empirical_familywise_p=p_value,
        matched_brightening_snr=matched,
        snr_above_matched_control=margin,
        campaign_input_combined_sha256=campaign_hash,
        search_duration_family_days=SEARCH_DURATIONS,
        source_event_index=source_index,
    )


def freeze(events: list[BlindCandidateInput]):
    return freeze_candidate_table(
        events,
        source_commit=SOURCE_COMMIT,
        frozen_at_utc="2026-07-22T10:00:00Z",
    )


def test_benjamini_hochberg_qvalues_are_monotone_and_order_preserving() -> None:
    q_values = benjamini_hochberg_qvalues([0.01, 0.04, 0.03])
    assert q_values == pytest.approx([0.03, 0.04, 0.04])


def test_freeze_is_independent_of_input_order() -> None:
    events = [
        event(
            "star-a",
            campaign_hash="1" * 64,
            p_value=0.01,
            snr=12.0,
            margin=4.0,
            center=5.0,
            source_index=0,
        ),
        event(
            "star-b",
            campaign_hash="2" * 64,
            p_value=0.02,
            snr=10.0,
            margin=2.0,
            center=7.0,
            source_index=1,
        ),
    ]
    first = freeze(events)
    second = freeze(list(reversed(events)))
    assert first.table_sha256 == second.table_sha256
    assert first.candidates == second.candidates
    assert all(record.manual_review_status == "unopened" for record in first.candidates)
    assert all(record.astrophysical_status == "unclassified" for record in first.candidates)


def test_one_predeclared_winner_is_kept_per_campaign_input() -> None:
    weaker = event(
        "star-a",
        campaign_hash="3" * 64,
        p_value=0.04,
        snr=18.0,
        margin=10.0,
        center=4.0,
        source_index=0,
    )
    stronger = event(
        "star-a",
        campaign_hash="3" * 64,
        p_value=0.01,
        snr=9.0,
        margin=1.0,
        center=8.0,
        source_index=1,
    )
    table = freeze([weaker, stronger])
    assert len(table.candidates) == 1
    record = table.candidates[0]
    assert record.center_time_days == 8.0
    assert record.source_event_index == 1
    assert record.competing_events_considered == 2


def test_blind_screen_requires_p_q_and_positive_control_margin() -> None:
    table = freeze(
        [
            event(
                "star-a",
                campaign_hash="4" * 64,
                p_value=0.01,
                snr=12.0,
                margin=3.0,
                center=1.0,
                source_index=0,
            ),
            event(
                "star-b",
                campaign_hash="5" * 64,
                p_value=0.20,
                snr=30.0,
                margin=-1.0,
                center=2.0,
                source_index=0,
            ),
        ]
    )
    first, second = table.candidates
    assert first.target_id == "star-a"
    assert first.blind_status == "screened-in"
    assert first.exclusion_reasons == ()
    assert second.blind_status == "screened-out"
    assert "target-familywise-p-above-threshold" in second.exclusion_reasons
    assert "table-bh-q-above-threshold" in second.exclusion_reasons
    assert "not-stronger-than-matched-brightening-control" in second.exclusion_reasons


def test_table_hash_changes_when_machine_evidence_changes() -> None:
    original = event(
        "star-a",
        campaign_hash="6" * 64,
        p_value=0.01,
        snr=12.0,
        margin=3.0,
        center=1.0,
        source_index=0,
    )
    changed = replace(original, depth=0.00013)
    assert freeze([original]).table_sha256 != freeze([changed]).table_sha256


@pytest.mark.parametrize(
    "bad_event",
    [
        event(
            "star-a",
            campaign_hash="x" * 64,
            p_value=0.01,
            snr=12.0,
            margin=3.0,
            center=1.0,
            source_index=0,
        ),
        replace(
            event(
                "star-a",
                campaign_hash="7" * 64,
                p_value=0.01,
                snr=12.0,
                margin=3.0,
                center=1.0,
                source_index=0,
            ),
            empirical_familywise_p=1.1,
        ),
        replace(
            event(
                "star-a",
                campaign_hash="8" * 64,
                p_value=0.01,
                snr=12.0,
                margin=3.0,
                center=1.0,
                source_index=0,
            ),
            search_duration_family_days=(0.08, 0.052),
        ),
    ],
)
def test_invalid_machine_evidence_is_rejected(bad_event: BlindCandidateInput) -> None:
    with pytest.raises(ValueError):
        freeze([bad_event])
