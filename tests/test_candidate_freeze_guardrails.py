from dataclasses import replace

import pytest

from houearth.candidate_freeze import BlindCandidateInput, freeze_candidate_table


SEARCH_DURATIONS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)


def event() -> BlindCandidateInput:
    return BlindCandidateInput(
        target_id="star-a",
        target_name="STAR A",
        sector_label="1",
        center_time_days=1.0,
        duration_days=0.08,
        depth=0.0001,
        snr=12.0,
        empirical_familywise_p=0.01,
        matched_brightening_snr=8.0,
        snr_above_matched_control=4.0,
        campaign_input_combined_sha256="a" * 64,
        search_duration_family_days=SEARCH_DURATIONS,
        source_event_index=0,
    )


def freeze(
    events: list[BlindCandidateInput],
    *,
    frozen_at_utc: str = "2026-07-22T10:00:00Z",
    target_familywise_alpha: float = 0.05,
    table_fdr_alpha: float = 0.10,
):
    return freeze_candidate_table(
        events,
        source_commit="b" * 40,
        frozen_at_utc=frozen_at_utc,
        target_familywise_alpha=target_familywise_alpha,
        table_fdr_alpha=table_fdr_alpha,
    )


@pytest.mark.parametrize("bad_index", [True, 1.5, -1])
def test_source_event_index_must_be_an_exact_nonnegative_integer(
    bad_index: object,
) -> None:
    with pytest.raises(ValueError, match="non-negative exact integer"):
        freeze([replace(event(), source_event_index=bad_index)])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_id", 123),
        ("target_name", ""),
        ("sector_label", None),
        ("empirical_familywise_p", True),
        ("snr", "12"),
    ],
)
def test_machine_fields_reject_boolean_text_and_invalid_identifiers(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        freeze([replace(event(), **{field: value})])


@pytest.mark.parametrize(
    "timestamp",
    ["banana", "2026-07-22", "2026-07-22T10:00:00+00:00", "2026-13-22T10:00:00Z"],
)
def test_freeze_timestamp_must_be_canonical_valid_utc(timestamp: str) -> None:
    with pytest.raises(ValueError, match="frozen_at_utc"):
        freeze([event()], frozen_at_utc=timestamp)


def test_mixed_duration_families_are_rejected() -> None:
    first = event()
    second = replace(
        event(),
        target_id="star-b",
        target_name="STAR B",
        campaign_input_combined_sha256="c" * 64,
        search_duration_family_days=(0.04, 0.08, 0.16),
    )
    with pytest.raises(ValueError, match="share one duration family"):
        freeze([first, second])


def test_event_duration_must_belong_to_search_family() -> None:
    with pytest.raises(ValueError, match="belong to the frozen search-duration family"):
        freeze([replace(event(), duration_days=0.09)])


def test_matched_control_fields_are_paired_and_arithmetically_consistent() -> None:
    with pytest.raises(ValueError, match="both present or both absent"):
        freeze([replace(event(), matched_brightening_snr=None)])
    with pytest.raises(ValueError, match="must equal snr"):
        freeze([replace(event(), snr_above_matched_control=3.0)])


def test_campaign_metadata_and_event_indices_must_be_internally_consistent() -> None:
    first = event()
    with pytest.raises(ValueError, match="multiple target names"):
        freeze([first, replace(first, target_name="DIFFERENT", source_event_index=1)])
    with pytest.raises(ValueError, match="multiple sector labels"):
        freeze([first, replace(first, sector_label="2", source_event_index=1)])
    with pytest.raises(ValueError, match="unique within a campaign"):
        freeze([first, replace(first, center_time_days=2.0)])


def test_campaign_input_hash_cannot_be_reused_for_another_target() -> None:
    second = replace(
        event(),
        target_id="star-b",
        target_name="STAR B",
        source_event_index=1,
    )
    with pytest.raises(ValueError, match="cannot belong to multiple targets"):
        freeze([event(), second])


@pytest.mark.parametrize(
    ("target_alpha", "fdr_alpha"),
    [(0.04, 0.10), (0.05, 0.20)],
)
def test_phase08_thresholds_cannot_be_changed_silently(
    target_alpha: float,
    fdr_alpha: float,
) -> None:
    with pytest.raises(ValueError, match="frozen"):
        freeze(
            [event()],
            target_familywise_alpha=target_alpha,
            table_fdr_alpha=fdr_alpha,
        )


def test_same_target_with_distinct_campaign_inputs_keeps_one_row_per_input() -> None:
    first = event()
    second = replace(
        event(),
        campaign_input_combined_sha256="d" * 64,
        center_time_days=2.0,
    )
    table = freeze([first, second])
    assert len(table.candidates) == 2
    assert {row.campaign_input_combined_sha256 for row in table.candidates} == {
        "a" * 64,
        "d" * 64,
    }


def test_empty_machine_stream_freezes_an_auditable_empty_table() -> None:
    table = freeze([])
    assert table.candidates == ()
    assert len(table.table_sha256) == 64
