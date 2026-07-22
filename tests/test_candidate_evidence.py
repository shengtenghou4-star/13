from copy import deepcopy

import pytest

from houearth.candidate_evidence import (
    CandidateEvidenceValidationError,
    freeze_candidate_evidence,
    validate_candidate_evidence,
)
from houearth.candidate_freeze import BlindCandidateInput
from houearth.provenance import canonical_json_sha256


SEARCH_DURATIONS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)


def event(
    target_id: str,
    input_hash: str,
    *,
    index: int,
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
        campaign_input_combined_sha256=input_hash,
        search_duration_family_days=SEARCH_DURATIONS,
        source_event_index=index,
    )


def evidence_payload() -> dict[str, object]:
    evidence = freeze_candidate_evidence(
        [
            event(
                "star-a",
                "1" * 64,
                index=1,
                p_value=0.04,
                snr=18.0,
                margin=10.0,
                center=4.0,
            ),
            event(
                "star-a",
                "1" * 64,
                index=0,
                p_value=0.01,
                snr=9.0,
                margin=1.0,
                center=8.0,
            ),
            event(
                "star-b",
                "2" * 64,
                index=0,
                p_value=0.02,
                snr=10.0,
                margin=2.0,
                center=7.0,
            ),
        ],
        source_commit="a" * 40,
        frozen_at_utc="2026-07-22T10:00:00Z",
    )
    return evidence.to_dict()


def rehash_events_and_package(payload: dict[str, object]) -> None:
    payload["machine_events_sha256"] = canonical_json_sha256(
        payload["machine_events"]
    )
    payload["package_sha256"] = canonical_json_sha256(
        {key: value for key, value in payload.items() if key != "package_sha256"}
    )


def assert_rejected(payload: dict[str, object], message: str) -> None:
    rehash_events_and_package(payload)
    with pytest.raises(CandidateEvidenceValidationError) as captured:
        validate_candidate_evidence(payload)
    assert any(message in error for error in captured.value.report.errors)


def test_complete_event_evidence_is_input_order_invariant_and_accepted() -> None:
    first = evidence_payload()
    assert validate_candidate_evidence(first).accepted is True
    assert len(first["machine_events"]) == 3
    assert len(first["candidate_table"]["candidates"]) == 2
    assert first["candidate_table"]["candidates"][0]["source_event_index"] == 0
    assert first["candidate_table"]["candidates"][0][
        "competing_events_considered"
    ] == 2

    reversed_evidence = freeze_candidate_evidence(
        list(
            reversed(
                [
                    event(
                        "star-a",
                        "1" * 64,
                        index=1,
                        p_value=0.04,
                        snr=18.0,
                        margin=10.0,
                        center=4.0,
                    ),
                    event(
                        "star-a",
                        "1" * 64,
                        index=0,
                        p_value=0.01,
                        snr=9.0,
                        margin=1.0,
                        center=8.0,
                    ),
                    event(
                        "star-b",
                        "2" * 64,
                        index=0,
                        p_value=0.02,
                        snr=10.0,
                        margin=2.0,
                        center=7.0,
                    ),
                ]
            )
        ),
        source_commit="a" * 40,
        frozen_at_utc="2026-07-22T10:00:00Z",
    ).to_dict()
    assert first["machine_events_sha256"] == reversed_evidence[
        "machine_events_sha256"
    ]
    assert first["candidate_table"] == reversed_evidence["candidate_table"]
    assert first["package_sha256"] == reversed_evidence["package_sha256"]


def test_rehashed_deleted_losing_event_is_rejected() -> None:
    payload = deepcopy(evidence_payload())
    del payload["machine_events"][1]
    assert_rejected(payload, "competing event count does not match event stream")


def test_rehashed_new_stronger_loser_without_table_update_is_rejected() -> None:
    payload = deepcopy(evidence_payload())
    # Make the previously losing event the clear winner, while leaving the table intact.
    payload["machine_events"][1]["empirical_familywise_p"] = 1.0 / 1000.0
    assert_rejected(payload, "selected winner field empirical_familywise_p is inconsistent")


def test_rehashed_machine_event_human_note_is_rejected() -> None:
    payload = deepcopy(evidence_payload())
    payload["machine_events"][0]["human_note"] = "looks convincing"
    assert_rejected(payload, "contains undeclared fields: human_note")


def test_rehashed_noncanonical_event_order_is_rejected() -> None:
    payload = deepcopy(evidence_payload())
    payload["machine_events"] = list(reversed(payload["machine_events"]))
    assert_rejected(payload, "machine event stream is not in canonical order")


def test_table_and_event_package_identity_must_match() -> None:
    payload = deepcopy(evidence_payload())
    payload["candidate_table"]["source_commit"] = "b" * 40
    payload["candidate_table"]["table_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in payload["candidate_table"].items()
            if key != "table_sha256"
        }
    )
    assert_rejected(payload, "source commits differ")


def test_plain_event_stream_tampering_breaks_hashes() -> None:
    payload = deepcopy(evidence_payload())
    payload["machine_events"][0]["depth"] = 0.0002
    with pytest.raises(CandidateEvidenceValidationError) as captured:
        validate_candidate_evidence(payload)
    errors = captured.value.report.errors
    assert any("machine_events_sha256 does not match" in error for error in errors)
    assert any("package_sha256 does not match" in error for error in errors)
