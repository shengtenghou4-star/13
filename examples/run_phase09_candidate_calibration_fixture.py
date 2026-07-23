from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.candidate_campaign import (
    build_blind_candidate_inputs,
    freeze_candidate_campaign_evidence,
)
from houearth.candidate_campaign_validation import validate_candidate_campaign_evidence
from houearth.candidate_evidence import (
    freeze_candidate_evidence,
    validate_candidate_evidence,
    write_candidate_evidence,
)
from houearth.candidate_protocol_validation import validate_frozen_candidate_table
from houearth.core import SingleTransitEvent
from houearth.provenance import canonical_json_sha256
from houearth.surrogates import DEFAULT_GAP_FACTOR, GAP_AWARE_METHOD, SurrogateTrial


DURATIONS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)
FROZEN_AT = "2026-07-23T00:00:00Z"


def event(target: str, center: float, duration: float, snr: float, direction: str) -> SingleTransitEvent:
    return SingleTransitEvent(
        target=target, center_time_days=center, duration_days=duration,
        depth=0.0001, snr=snr, local_points=8, direction=direction,
    )


def trials(target: str, sector: str, maxima: list[float | None]) -> list[SurrogateTrial]:
    return [
        SurrogateTrial(
            target=target, sector_label=sector, seed=seed,
            method=GAP_AWARE_METHOD, block_days=0.5, contiguous_segments=2,
            gap_factor=3.5, neutralized_events=0, neutralized_points=0,
            dimming_events=1 if maximum is not None and maximum >= 5.0 else 0,
            brightening_events=0,
            maximum_dimming_snr=maximum, maximum_brightening_snr=4.0,
            exceeded_dimming_threshold=maximum is not None and maximum >= 5.0,
            exceeded_brightening_threshold=False,
        )
        for seed, maximum in enumerate(maxima)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    specs = [
        ("fixture-null-a", "SYNTHETIC NULL A", "101", "1" * 64, [5.0] * 63 + [10.0]),
        ("fixture-null-b", "SYNTHETIC NULL B", "102", "2" * 64, [None] * 62 + [9.5, 12.0]),
        ("fixture-null-c", "SYNTHETIC NULL C", "103", "3" * 64, [8.0] * 64),
    ]
    lock_payload = {
        "schema": "houearth-blind-real-campaign-lock-v0.9.0",
        "source_commit": args.source_commit,
        "frozen_at_utc": FROZEN_AT,
        "manifest_sha256": canonical_json_sha256(specs),
        "eligible_target_rule": "surrogate_policy == unmasked-null",
        "excluded_targets": [],
        "search_duration_family_days": list(DURATIONS),
        "flatten_window_days": 1.5,
        "minimum_search_snr": 5.0,
        "maximum_machine_events_per_direction": 200,
        "surrogate_method": GAP_AWARE_METHOD,
        "surrogate_seeds": list(range(64)),
        "surrogate_block_days": 0.5,
        "surrogate_gap_factor": DEFAULT_GAP_FACTOR,
        "targets": [
            {
                "target_id": target_id, "query": target_name,
                "intended_role": "synthetic-null", "sector_label": sector,
                "campaign_input_combined_sha256": campaign_hash,
                "query_provenance_sha256": str(index + 4) * 64,
                "product_provenance_sha256": str(index + 7) * 64,
            }
            for index, (target_id, target_name, sector, campaign_hash, _) in enumerate(specs)
        ],
    }
    campaign_lock = {
        **lock_payload,
        "campaign_lock_sha256": canonical_json_sha256(lock_payload),
    }

    machine_rows = []
    target_calibrations = []
    for index, (target_id, target_name, sector, campaign_hash, maxima) in enumerate(specs):
        dimming = [
            event(target_name, 5.0 + index, 0.08, 10.0 - index, "dimming"),
            event(target_name, 9.0 + index, 0.16, 8.0 - index, "dimming"),
        ]
        controls = [event(target_name, 2.0, 0.08, 7.0 + index, "brightening")]
        nulls = trials(target_name, sector, maxima)
        derived, receipt = build_blind_candidate_inputs(
            target_id=target_id, target_name=target_name, sector_label=sector,
            campaign_input_sha256=campaign_hash,
            search_duration_family_days=DURATIONS,
            dimming_events=dimming, brightening_control_events=controls,
            surrogate_trials=nulls,
        )
        machine_rows.extend(derived)
        target_calibrations.append(
            {
                "target_id": target_id, "target_name": target_name,
                "sector_label": sector,
                "campaign_input_combined_sha256": campaign_hash,
                "search_duration_family_days": list(DURATIONS),
                "dimming_events": [row.to_dict() for row in dimming],
                "brightening_control_events": [row.to_dict() for row in controls],
                "surrogate_trials": [row.to_dict() for row in nulls],
                "calibration_receipt": receipt.to_dict(),
            }
        )

    evidence = freeze_candidate_evidence(
        machine_rows, source_commit=args.source_commit, frozen_at_utc=FROZEN_AT
    )
    campaign = freeze_candidate_campaign_evidence(
        source_commit=args.source_commit, frozen_at_utc=FROZEN_AT,
        campaign_lock=campaign_lock, target_calibrations=target_calibrations,
        candidate_evidence=evidence.to_dict(),
    )
    table_report = validate_frozen_candidate_table(evidence.candidate_table.to_dict())
    evidence_report = validate_candidate_evidence(evidence.to_dict())
    campaign_report = validate_candidate_campaign_evidence(campaign)

    args.output.mkdir(parents=True, exist_ok=True)
    write_candidate_evidence(evidence, args.output)
    files = {
        "campaign_lock.json": campaign_lock,
        "target_calibration_inputs.json": target_calibrations,
        "candidate_campaign_evidence.json": campaign,
        "table_validation_report.json": table_report.to_dict(),
        "candidate_evidence_validation_report.json": evidence_report.to_dict(),
        "candidate_campaign_validation_report.json": campaign_report.to_dict(),
    }
    for name, payload in files.items():
        (args.output / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    summary = {
        "status": "synthetic Phase 0.9 fixture; no astronomical claim",
        "source_commit": args.source_commit, "targets": len(specs),
        "surrogate_trials": 64 * len(specs), "machine_events": len(machine_rows),
        "candidate_rows": len(evidence.candidate_table.candidates),
        "screened_in": sum(
            row.blind_status == "screened-in" for row in evidence.candidate_table.candidates
        ),
        "all_unopened": all(
            row.manual_review_status == "unopened"
            for row in evidence.candidate_table.candidates
        ),
        "all_unclassified": all(
            row.astrophysical_status == "unclassified"
            for row in evidence.candidate_table.candidates
        ),
        "candidate_table_sha256": evidence.candidate_table.table_sha256,
        "candidate_evidence_sha256": evidence.package_sha256,
        "candidate_campaign_evidence_sha256": campaign["package_sha256"],
        "all_validations_accepted": (
            table_report.accepted and evidence_report.accepted and campaign_report.accepted
        ),
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
