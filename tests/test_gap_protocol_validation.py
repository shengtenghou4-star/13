import pytest

from houearth.gap_protocol_validation import (
    GapProtocolValidationError,
    SURROGATE_GAP_FACTOR,
    SURROGATE_METHOD,
    validate_phase07_gap_summary,
)


def null_target(target_id: str) -> dict[str, object]:
    return {
        "target_id": target_id,
        "status": "completed",
        "surrogate_policy": "unmasked-null",
        "surrogate_trials": 64,
        "surrogate_summary": {
            "status": "completed",
            "method": SURROGATE_METHOD,
            "gap_factor": SURROGATE_GAP_FACTOR,
            "minimum_segments": 2,
            "maximum_segments": 2,
        },
    }


def valid_summary() -> dict[str, object]:
    return {
        "targets": [
            null_target("hd-10700"),
            null_target("hd-20794"),
            null_target("hd-69830"),
            {
                "target_id": "au-mic",
                "status": "completed",
                "surrogate_policy": "skip-known-transits",
                "surrogate_trials": 0,
                "surrogate_summary": {"status": "skipped"},
            },
        ]
    }


def test_valid_gap_aware_evidence_is_accepted() -> None:
    report = validate_phase07_gap_summary(valid_summary())
    assert report.accepted is True
    assert report.completed_null_targets == 3
    assert report.surrogate_trials == 192
    assert report.errors == ()


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("method", "circular-moving-block-bootstrap", "method is inconsistent"),
        ("gap_factor", 4.0, "gap factor is inconsistent"),
        ("minimum_segments", 0, "segment counts must be positive"),
        ("maximum_segments", 3, "segment count changed"),
    ],
)
def test_gap_metadata_mismatch_is_rejected(
    field: str, bad_value: object, message: str
) -> None:
    summary = valid_summary()
    summary["targets"][0]["surrogate_summary"][field] = bad_value
    with pytest.raises(GapProtocolValidationError) as captured:
        validate_phase07_gap_summary(summary)
    assert any(message in error for error in captured.value.report.errors)


def test_one_completed_null_target_is_not_enough() -> None:
    summary = {"targets": [null_target("hd-10700")]}
    with pytest.raises(GapProtocolValidationError) as captured:
        validate_phase07_gap_summary(summary)
    assert any("completed null targets" in error for error in captured.value.report.errors)


def test_nonintegral_or_wrong_surrogate_count_is_rejected() -> None:
    summary = valid_summary()
    summary["targets"][0]["surrogate_trials"] = 63.5
    with pytest.raises(GapProtocolValidationError) as captured:
        validate_phase07_gap_summary(summary)
    errors = captured.value.report.errors
    assert any("non-integral" in error for error in errors)
    assert any("!= 64" in error for error in errors)
