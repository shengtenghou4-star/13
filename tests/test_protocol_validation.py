import pytest

from houearth.protocol_validation import (
    ProtocolValidationError,
    validate_phase07_summary,
)


def target(target_id: str, policy: str, *, completed: bool = True) -> dict[str, object]:
    surrogate_count = 64 if policy == "unmasked-null" else 0
    surrogate_status = "completed" if policy == "unmasked-null" else "skipped"
    return {
        "target_id": target_id,
        "status": "completed" if completed else "failed",
        "surrogate_policy": policy,
        "physical_trials": 32 if completed else 0,
        "surrogate_trials": surrogate_count if completed else 0,
        "surrogate_summary": {"status": surrogate_status},
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
    host["surrogate_summary"] = {"status": "completed"}
    summary["total_surrogate_trials"] = 256
    with pytest.raises(ProtocolValidationError) as captured:
        validate_phase07_summary(summary)
    assert any("known transit host" in error for error in captured.value.report.errors)
