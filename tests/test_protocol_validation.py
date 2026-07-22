import pytest

from houearth.protocol_validation import (
    ProtocolValidationError,
    validate_phase07_summary,
)
from houearth.provenance import HASH_SCHEMA
from houearth.search_grids import physical_single_event_search_durations


SEARCH_DURATIONS = physical_single_event_search_durations((0.08, 0.16))
VALID_STRATUM = {
    "campaign_input_hash_schema": HASH_SCHEMA,
    "campaign_input_combined_sha256": "a" * 64,
    "product_provenance_sha256": "b" * 64,
    "query_provenance_sha256": "c" * 64,
}


def target(target_id: str, policy: str, *, completed: bool = True) -> dict[str, object]:
    surrogate_count = 64 if policy == "unmasked-null" else 0
    surrogate_status = "completed" if policy == "unmasked-null" else "skipped"
    surrogate_summary: dict[str, object] = {"status": surrogate_status}
    if policy == "unmasked-null":
        surrogate_summary["search_durations_days"] = SEARCH_DURATIONS
    return {
        "target_id": target_id,
        "status": "completed" if completed else "failed",
        "surrogate_policy": policy,
        "stratum": dict(VALID_STRATUM),
        "physical_trials": 32 if completed else 0,
        "surrogate_trials": surrogate_count if completed else 0,
        "surrogate_summary": surrogate_summary,
    }


def valid_summary() -> dict[str, object]:
    targets = [
        target("hd-10700", "unmasked-null"),
        target("hd-20794", "unmasked-null"),
        target("hd-69830", "unmasked-null"),
        target("au-mic", "skip-known-transits"),
        target("toi-700", "skip-known-transits"),
        target("lhs-3844", "skip-known-transits"),
    ]
    return {
        "targets": targets,
        "search_durations_days": SEARCH_DURATIONS,
        "total_physical_trials": 192,
        "total_surrogate_trials": 192,
        "minimum_resolvable_surrogate_p": 1.0 / 65.0,
    }


def test_valid_phase07_summary_is_accepted() -> None:
    report = validate_phase07_summary(valid_summary())
    assert report.accepted is True
    assert report.completed_targets == 6
    assert report.completed_null_targets == 3
    assert report.physical_trials == 192
    assert report.surrogate_trials == 192
    assert report.errors == ()


def test_partial_batch_can_pass_frozen_minimum_gate() -> None:
    summary = valid_summary()
    summary["targets"] = [
        target("hd-10700", "unmasked-null"),
        target("hd-20794", "unmasked-null"),
        target("au-mic", "skip-known-transits"),
        target("toi-700", "skip-known-transits"),
        target("hd-69830", "unmasked-null", completed=False),
        target("lhs-3844", "skip-known-transits", completed=False),
    ]
    summary["total_physical_trials"] = 128
    summary["total_surrogate_trials"] = 128
    report = validate_phase07_summary(summary)
    assert report.accepted is True
    assert report.completed_targets == 4
    assert report.completed_null_targets == 2


def test_missing_null_evidence_is_rejected_even_with_four_targets() -> None:
    summary = valid_summary()
    summary["targets"] = [
        target("hd-10700", "unmasked-null"),
        target("au-mic", "skip-known-transits"),
        target("toi-700", "skip-known-transits"),
        target("lhs-3844", "skip-known-transits"),
    ]
    summary["total_physical_trials"] = 128
    summary["total_surrogate_trials"] = 64
    with pytest.raises(ProtocolValidationError) as captured:
        validate_phase07_summary(summary)
    assert captured.value.report.accepted is False
    assert any("completed null targets" in error for error in captured.value.report.errors)


def test_known_transit_host_cannot_produce_null_trials() -> None:
    summary = valid_summary()
    host = summary["targets"][3]
    host["surrogate_trials"] = 64
    host["surrogate_summary"] = {
        "status": "completed",
        "search_durations_days": SEARCH_DURATIONS,
    }
    summary["total_surrogate_trials"] = 256
    with pytest.raises(ProtocolValidationError) as captured:
        validate_phase07_summary(summary)
    assert any("known transit host" in error for error in captured.value.report.errors)


def test_malformed_surrogate_summary_is_structurally_rejected() -> None:
    summary = valid_summary()
    null_target = summary["targets"][0]
    null_target["surrogate_summary"] = None
    with pytest.raises(ProtocolValidationError) as captured:
        validate_phase07_summary(summary)
    errors = captured.value.report.errors
    assert any("surrogate summary is missing or malformed" in error for error in errors)
    assert any("null campaign not completed" in error for error in errors)


def test_nonfinite_or_malformed_summary_fields_are_rejected_not_crashed() -> None:
    summary = valid_summary()
    summary["minimum_resolvable_surrogate_p"] = float("nan")
    summary["targets"].append("not-an-object")
    with pytest.raises(ProtocolValidationError) as captured:
        validate_phase07_summary(summary)
    errors = captured.value.report.errors
    assert any("malformed non-object" in error for error in errors)
    assert any("minimum empirical p resolution" in error for error in errors)


def test_mismatched_surrogate_search_family_is_rejected() -> None:
    summary = valid_summary()
    summary["targets"][0]["surrogate_summary"]["search_durations_days"] = (
        0.04,
        0.08,
        0.16,
    )
    with pytest.raises(ProtocolValidationError) as captured:
        validate_phase07_summary(summary)
    assert any(
        "surrogate search-duration family is inconsistent" in error
        for error in captured.value.report.errors
    )


def test_mismatched_root_search_family_is_rejected() -> None:
    summary = valid_summary()
    summary["search_durations_days"] = (0.04, 0.08, 0.16)
    with pytest.raises(ProtocolValidationError) as captured:
        validate_phase07_summary(summary)
    assert any(
        "root search-duration family is missing or inconsistent" in error
        for error in captured.value.report.errors
    )


def test_missing_or_invalid_data_fingerprints_are_rejected() -> None:
    summary = valid_summary()
    summary["targets"][0]["stratum"]["campaign_input_combined_sha256"] = "not-a-hash"
    summary["targets"][1]["stratum"]["campaign_input_hash_schema"] = "wrong-schema"
    with pytest.raises(ProtocolValidationError) as captured:
        validate_phase07_summary(summary)
    errors = captured.value.report.errors
    assert any("campaign_input_combined_sha256 is missing or invalid" in error for error in errors)
    assert any("campaign-input hash schema is inconsistent" in error for error in errors)
