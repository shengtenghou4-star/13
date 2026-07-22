from copy import deepcopy

import pytest

from houearth.candidate_freeze import BlindCandidateInput, freeze_candidate_table
from houearth.candidate_protocol_validation import (
    CandidateProtocolValidationError,
    validate_frozen_candidate_table,
)
from houearth.provenance import canonical_json_sha256


SEARCH_DURATIONS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)


def valid_payload() -> dict[str, object]:
    table = freeze_candidate_table(
        [
            BlindCandidateInput(
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
                campaign_input_combined_sha256="1" * 64,
                search_duration_family_days=SEARCH_DURATIONS,
                source_event_index=0,
            )
        ],
        source_commit="a" * 40,
        frozen_at_utc="2026-07-22T10:00:00Z",
    )
    payload = table.to_dict()
    payload["candidates"] = list(payload["candidates"])
    return payload


def rehash(payload: dict[str, object]) -> None:
    payload["table_sha256"] = canonical_json_sha256(
        {key: value for key, value in payload.items() if key != "table_sha256"}
    )


def assert_rejected(payload: dict[str, object], message: str) -> None:
    rehash(payload)
    with pytest.raises(CandidateProtocolValidationError) as captured:
        validate_frozen_candidate_table(payload)
    assert any(message in error for error in captured.value.report.errors)


def test_explicit_empty_candidate_table_is_valid_but_missing_field_is_not() -> None:
    empty = freeze_candidate_table(
        [],
        source_commit="a" * 40,
        frozen_at_utc="2026-07-22T10:00:00Z",
    ).to_dict()
    assert validate_frozen_candidate_table(empty).accepted is True

    missing = deepcopy(empty)
    del missing["candidates"]
    assert_rejected(missing, "missing fields: candidates")


def test_rehashed_top_level_human_annotation_is_rejected() -> None:
    payload = valid_payload()
    payload["human_notes"] = "looks planetary"
    assert_rejected(payload, "undeclared fields: human_notes")


def test_rehashed_row_manual_score_is_rejected() -> None:
    payload = valid_payload()
    payload["candidates"][0]["manual_score"] = 99
    assert_rejected(payload, "undeclared fields: manual_score")


def test_rehashed_missing_required_row_field_is_rejected() -> None:
    payload = valid_payload()
    del payload["candidates"][0]["target_name"]
    assert_rejected(payload, "row is missing fields: target_name")


def test_non_string_schema_keys_are_rejected() -> None:
    payload = valid_payload()
    payload[7] = "hidden"
    assert_rejected(payload, "undeclared fields: 7")
