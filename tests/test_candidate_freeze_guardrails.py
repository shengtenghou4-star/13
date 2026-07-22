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


def freeze(events: list[BlindCandidateInput]):
    return freeze_candidate_table(
        events,
        source_commit="b" * 40,
        frozen_at_utc="2026-07-22T10:00:00Z",
    )


@pytest.mark.parametrize("bad_index", [True, 1.5, -1])
def test_source_event_index_must_be_an_exact_nonnegative_integer(
    bad_index: object,
) -> None:
    with pytest.raises(ValueError, match="non-negative exact integer"):
        freeze([replace(event(), source_event_index=bad_index)])


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
