from copy import deepcopy

import pytest

from houearth.candidate_campaign import (
    build_blind_candidate_inputs,
    freeze_candidate_campaign_evidence,
)
from houearth.candidate_campaign_validation import (
    CandidateCampaignValidationError,
    validate_candidate_campaign_evidence,
)
from houearth.candidate_evidence import freeze_candidate_evidence
from houearth.core import SingleTransitEvent
from houearth.provenance import canonical_json_sha256
from houearth.surrogates import GAP_AWARE_METHOD, SurrogateTrial


DURATIONS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)
SOURCE = "a" * 40
FROZEN_AT = "2026-07-23T00:00:00Z"
CAMPAIGN_HASH = "1" * 64


def event(center: float, duration: float, snr: float, *, direction: str) -> SingleTransitEvent:
    return SingleTransitEvent(
        target="SYNTHETIC STAR",
        center_time_days=center,
        duration_days=duration,
        depth=0.0001,
        snr=snr,
        local_points=8,
        direction=direction,
    )


def trials() -> list[SurrogateTrial]:
    return [
        SurrogateTrial(
            target="SYNTHETIC STAR", sector_label="1", seed=seed,
            method=GAP_AWARE_METHOD, block_days=0.5, contiguous_segments=2,
            gap_factor=3.5, neutralized_events=0, neutralized_points=0,
            dimming_events=1, brightening_events=1,
            maximum_dimming_snr=5.0 if seed < 63 else 10.0,
            maximum_brightening_snr=4.0,
            exceeded_dimming_threshold=True,
            exceeded_brightening_threshold=False,
        )
        for seed in range(64)
    ]


def package() -> dict[str, object]:
    dimming = [
        event(8.0, 0.08, 10.0, direction="dimming"),
        event(4.0, 0.16, 8.0, direction="dimming"),
    ]
    brightening = [event(2.0, 0.08, 7.0, direction="brightening")]
    surrogate_rows = trials()
    machine_rows, receipt = build_blind_candidate_inputs(
        target_id="synthetic-star", target_name="SYNTHETIC STAR",
        sector_label="1", campaign_input_sha256=CAMPAIGN_HASH,
        search_duration_family_days=DURATIONS, dimming_events=dimming,
        brightening_control_events=brightening, surrogate_trials=surrogate_rows,
    )
    evidence = freeze_candidate_evidence(
        machine_rows, source_commit=SOURCE, frozen_at_utc=FROZEN_AT
    )
    lock_payload = {
        "schema": "houearth-blind-real-campaign-lock-v0.9.0",
        "source_commit": SOURCE, "frozen_at_utc": FROZEN_AT,
        "manifest_sha256": "2" * 64,
        "eligible_target_rule": "surrogate_policy == unmasked-null",
        "excluded_targets": [],
        "search_duration_family_days": list(DURATIONS),
        "flatten_window_days": 1.5, "minimum_search_snr": 5.0,
        "maximum_machine_events_per_direction": 200,
        "surrogate_method": GAP_AWARE_METHOD,
        "surrogate_seeds": list(range(64)),
        "surrogate_block_days": 0.5, "surrogate_gap_factor": 3.5,
        "targets": [{
            "target_id": "synthetic-star", "query": "SYNTHETIC STAR",
            "intended_role": "synthetic-null", "sector_label": "1",
            "campaign_input_combined_sha256": CAMPAIGN_HASH,
            "query_provenance_sha256": "3" * 64,
            "product_provenance_sha256": "4" * 64,
        }],
    }
    lock = {**lock_payload, "campaign_lock_sha256": canonical_json_sha256(lock_payload)}
    target = {
        "target_id": "synthetic-star", "target_name": "SYNTHETIC STAR",
        "sector_label": "1", "campaign_input_combined_sha256": CAMPAIGN_HASH,
        "search_duration_family_days": list(DURATIONS),
        "dimming_events": [row.to_dict() for row in dimming],
        "brightening_control_events": [row.to_dict() for row in brightening],
        "surrogate_trials": [row.to_dict() for row in surrogate_rows],
        "calibration_receipt": receipt.to_dict(),
    }
    return freeze_candidate_campaign_evidence(
        source_commit=SOURCE, frozen_at_utc=FROZEN_AT, campaign_lock=lock,
        target_calibrations=[target], candidate_evidence=evidence.to_dict(),
    )


def rehash(payload: dict[str, object]) -> None:
    payload["package_sha256"] = canonical_json_sha256(
        {key: value for key, value in payload.items() if key != "package_sha256"}
    )


def assert_rejected(payload: dict[str, object], message: str) -> None:
    rehash(payload)
    with pytest.raises(CandidateCampaignValidationError) as captured:
        validate_candidate_campaign_evidence(payload)
    assert any(message in error for error in captured.value.report.errors)


def test_complete_campaign_evidence_is_accepted() -> None:
    report = validate_candidate_campaign_evidence(package())
    assert report.accepted is True
    assert report.targets == 1
    assert report.surrogate_trials == 64
    assert report.machine_events == 2


def test_rehashed_surrogate_change_cannot_fake_event_p_value() -> None:
    payload = deepcopy(package())
    payload["target_calibrations"][0]["surrogate_trials"][0]["maximum_dimming_snr"] = 20.0
    assert_rejected(payload, "empirical_familywise_p is inconsistent")


def test_rehashed_deleted_machine_source_event_is_detected() -> None:
    payload = deepcopy(package())
    del payload["target_calibrations"][0]["dimming_events"][0]
    assert_rejected(payload, "machine event identities do not match")


def test_rehashed_human_note_is_rejected_by_closed_schema() -> None:
    payload = deepcopy(package())
    payload["target_calibrations"][0]["human_note"] = "looks planetary"
    assert_rejected(payload, "contains undeclared fields: human_note")


def test_rehashed_campaign_lock_target_change_is_detected() -> None:
    payload = deepcopy(package())
    payload["campaign_lock"]["targets"][0]["query"] = "OTHER STAR"
    lock = payload["campaign_lock"]
    lock["campaign_lock_sha256"] = canonical_json_sha256(
        {key: value for key, value in lock.items() if key != "campaign_lock_sha256"}
    )
    assert_rejected(payload, "identity differs from the campaign lock")


def test_plain_campaign_tampering_breaks_package_hash() -> None:
    payload = deepcopy(package())
    payload["target_calibrations"][0]["dimming_events"][0]["snr"] = 30.0
    with pytest.raises(CandidateCampaignValidationError) as captured:
        validate_candidate_campaign_evidence(payload)
    assert any("package SHA-256" in error for error in captured.value.report.errors)
