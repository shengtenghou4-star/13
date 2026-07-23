from copy import deepcopy

import pytest

from houearth.candidate_freeze import BlindCandidateInput, freeze_candidate_table
from houearth.candidate_protocol_validation import (
    CandidateProtocolValidationError,
    validate_frozen_candidate_table,
)
from houearth.provenance import canonical_json_sha256


SOURCE_COMMIT = "a" * 40
SEARCH_DURATIONS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)


def event(
    target_id: str,
    campaign_hash: str,
    *,
    p_value: float,
    snr: float,
    margin: float,
    center: float,
) -> BlindCandidateInput:
    return BlindCandidateInput(
        target_id=target_id,
        target_name=target_id.upper(),
        sector_label="1",
        center_time_days=center,
        duration_days=0.08,
        depth=0.0001,
        snr=snr,
        empirical_familywise_p=p_value,
        matched_brightening_snr=snr - margin,
        snr_above_matched_control=margin,
        campaign_input_combined_sha256=campaign_hash,
        search_duration_family_days=SEARCH_DURATIONS,
        source_event_index=0,
    )


def valid_payload() -> dict[str, object]:
    table = freeze_candidate_table(
        [
            event(
                "star-a",
                "1" * 64,
                p_value=0.01,
                snr=12.0,
                margin=4.0,
                center=1.0,
            ),
            event(
                "star-b",
                "2" * 64,
                p_value=0.20,
                snr=20.0,
                margin=2.0,
                center=2.0,
            ),
        ],
        source_commit=SOURCE_COMMIT,
        frozen_at_utc="2026-07-22T10:00:00Z",
    )
    payload = table.to_dict()
    payload["candidates"] = list(payload["candidates"])
    return payload


def rehash(payload: dict[str, object]) -> None:
    payload["table_sha256"] = canonical_json_sha256(
        {key: value for key, value in payload.items() if key != "table_sha256"}
    )


def validate_rehashed_tampering(
    payload: dict[str, object],
) -> CandidateProtocolValidationError:
    rehash(payload)
    with pytest.raises(CandidateProtocolValidationError) as captured:
        validate_frozen_candidate_table(payload)
    return captured.value


def test_valid_frozen_candidate_table_is_accepted() -> None:
    report = validate_frozen_candidate_table(valid_payload())
    assert report.accepted is True
    assert report.candidates == 2
    assert report.screened_in == 1
    assert report.errors == ()


def test_rehashed_manual_review_tampering_is_rejected() -> None:
    payload = deepcopy(valid_payload())
    payload["candidates"][0]["manual_review_status"] = "opened"
    error = validate_rehashed_tampering(payload)
    assert any("not frozen before manual review" in item for item in error.report.errors)


def test_rehashed_q_value_tampering_is_rejected() -> None:
    payload = deepcopy(valid_payload())
    payload["candidates"][0]["benjamini_hochberg_q"] = 0.000001
    payload["candidates"][0]["exclusion_reasons"] = []
    error = validate_rehashed_tampering(payload)
    assert any("BH q-value is inconsistent" in item for item in error.report.errors)


def test_rehashed_ranking_manipulation_is_rejected() -> None:
    payload = deepcopy(valid_payload())
    payload["candidates"] = list(reversed(payload["candidates"]))
    payload["candidates"][0]["blind_priority_rank"] = 1
    payload["candidates"][1]["blind_priority_rank"] = 2
    error = validate_rehashed_tampering(payload)
    assert any("not in the frozen blind ranking order" in item for item in error.report.errors)


def test_rehashed_candidate_id_forgery_is_rejected() -> None:
    payload = deepcopy(valid_payload())
    payload["candidates"][0]["candidate_id"] = "hou-" + "f" * 24
    error = validate_rehashed_tampering(payload)
    assert any("does not match frozen evidence" in item for item in error.report.errors)


def test_plain_payload_tampering_breaks_table_hash() -> None:
    payload = deepcopy(valid_payload())
    payload["candidates"][0]["snr"] = 999.0
    with pytest.raises(CandidateProtocolValidationError) as captured:
        validate_frozen_candidate_table(payload)
    assert any("table_sha256 does not match" in item for item in captured.value.report.errors)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("frozen_at_utc", "banana", "not canonical UTC"),
        ("target_familywise_alpha", 0.04, "not frozen at 0.05"),
        ("table_fdr_alpha", 0.20, "not frozen at 0.10"),
        ("selection_rule", "choose what looks nice", "selection_rule"),
        ("ranking_rule", "manual priority", "ranking_rule"),
    ],
)
def test_rehashed_protocol_metadata_tampering_is_rejected(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = deepcopy(valid_payload())
    payload[field] = value
    error = validate_rehashed_tampering(payload)
    assert any(message in item for item in error.report.errors)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("target_name", "", "target_name is invalid"),
        ("center_time_days", "1.0", "center time is invalid"),
        ("duration_days", -0.08, "duration is invalid"),
        ("depth", -0.0001, "depth is invalid"),
        ("snr", True, "SNR is invalid"),
    ],
)
def test_rehashed_scientific_field_tampering_is_rejected(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = deepcopy(valid_payload())
    payload["candidates"][0][field] = value
    error = validate_rehashed_tampering(payload)
    assert any(message in item for item in error.report.errors)


def test_rehashed_matched_control_arithmetic_tampering_is_rejected() -> None:
    payload = deepcopy(valid_payload())
    payload["candidates"][0]["snr_above_matched_control"] = 999.0
    error = validate_rehashed_tampering(payload)
    assert any("matched-control arithmetic" in item for item in error.report.errors)


def test_rehashed_duration_outside_search_family_is_rejected() -> None:
    payload = deepcopy(valid_payload())
    payload["candidates"][0]["duration_days"] = 0.09
    error = validate_rehashed_tampering(payload)
    assert any("outside the search family" in item for item in error.report.errors)


def test_rehashed_campaign_hash_reuse_across_targets_is_rejected() -> None:
    payload = deepcopy(valid_payload())
    payload["candidates"][1]["campaign_input_combined_sha256"] = payload[
        "candidates"
    ][0]["campaign_input_combined_sha256"]
    error = validate_rehashed_tampering(payload)
    assert any("belongs to multiple targets" in item for item in error.report.errors)
