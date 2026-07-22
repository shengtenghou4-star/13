from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.candidate_evidence import (
    freeze_candidate_evidence,
    validate_candidate_evidence,
    write_candidate_evidence,
)
from houearth.candidate_freeze import BlindCandidateInput
from houearth.candidate_protocol_validation import validate_frozen_candidate_table


SEARCH_DURATIONS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)


def fixture_events() -> list[BlindCandidateInput]:
    """Return deterministic synthetic machine evidence, not astronomical candidates."""
    return [
        BlindCandidateInput(
            target_id="fixture-a",
            target_name="SYNTHETIC FIXTURE A",
            sector_label="101",
            center_time_days=5.25,
            duration_days=0.08,
            depth=0.00012,
            snr=12.4,
            empirical_familywise_p=1.0 / 65.0,
            matched_brightening_snr=7.2,
            snr_above_matched_control=5.2,
            campaign_input_combined_sha256="1" * 64,
            search_duration_family_days=SEARCH_DURATIONS,
            source_event_index=0,
        ),
        BlindCandidateInput(
            target_id="fixture-a",
            target_name="SYNTHETIC FIXTURE A",
            sector_label="101",
            center_time_days=9.50,
            duration_days=0.16,
            depth=0.00020,
            snr=15.0,
            empirical_familywise_p=3.0 / 65.0,
            matched_brightening_snr=8.0,
            snr_above_matched_control=7.0,
            campaign_input_combined_sha256="1" * 64,
            search_duration_family_days=SEARCH_DURATIONS,
            source_event_index=1,
        ),
        BlindCandidateInput(
            target_id="fixture-b",
            target_name="SYNTHETIC FIXTURE B",
            sector_label="102",
            center_time_days=7.75,
            duration_days=0.116,
            depth=0.00010,
            snr=9.5,
            empirical_familywise_p=2.0 / 65.0,
            matched_brightening_snr=8.8,
            snr_above_matched_control=0.7,
            campaign_input_combined_sha256="2" * 64,
            search_duration_family_days=SEARCH_DURATIONS,
            source_event_index=0,
        ),
        BlindCandidateInput(
            target_id="fixture-c",
            target_name="SYNTHETIC FIXTURE C",
            sector_label="103",
            center_time_days=12.0,
            duration_days=0.052,
            depth=0.00030,
            snr=20.0,
            empirical_familywise_p=12.0 / 65.0,
            matched_brightening_snr=21.0,
            snr_above_matched_control=-1.0,
            campaign_input_combined_sha256="3" * 64,
            search_duration_family_days=SEARCH_DURATIONS,
            source_event_index=0,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic synthetic frozen-candidate evidence package."
    )
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/candidate-freeze-fixture-v0.8"),
    )
    args = parser.parse_args()

    evidence = freeze_candidate_evidence(
        fixture_events(),
        source_commit=args.source_commit,
        frozen_at_utc="2026-07-22T10:00:00Z",
    )
    write_candidate_evidence(evidence, args.output)
    table_report = validate_frozen_candidate_table(evidence.candidate_table.to_dict())
    evidence_report = validate_candidate_evidence(evidence.to_dict())
    (args.output / "candidate_validation_report.json").write_text(
        json.dumps(table_report.to_dict(), indent=2), encoding="utf-8"
    )
    (args.output / "candidate_evidence_validation_report.json").write_text(
        json.dumps(evidence_report.to_dict(), indent=2), encoding="utf-8"
    )
    manifest = {
        "fixture_only": True,
        "astronomical_claim": "none",
        "source_commit": args.source_commit,
        "input_events": len(evidence.machine_events),
        "frozen_campaign_rows": len(evidence.candidate_table.candidates),
        "screened_in_rows": table_report.screened_in,
        "machine_events_sha256": evidence.machine_events_sha256,
        "candidate_table_sha256": evidence.candidate_table.table_sha256,
        "evidence_package_sha256": evidence.package_sha256,
        "table_validation_accepted": table_report.accepted,
        "event_stream_validation_accepted": evidence_report.accepted,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
