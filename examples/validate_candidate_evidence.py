from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.candidate_evidence import (
    CandidateEvidenceValidationError,
    validate_candidate_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a complete HOU-EARTH machine-event stream and its frozen "
            "blind candidate table."
        )
    )
    parser.add_argument("candidate_evidence", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional output path for the validation report JSON.",
    )
    args = parser.parse_args()

    payload = json.loads(args.candidate_evidence.read_text(encoding="utf-8"))
    report_path = args.report or args.candidate_evidence.with_name(
        "candidate_evidence_validation_report.json"
    )
    try:
        report = validate_candidate_evidence(payload)
    except CandidateEvidenceValidationError as exc:
        report_path.write_text(
            json.dumps(exc.report.to_dict(), indent=2), encoding="utf-8"
        )
        print(json.dumps(exc.report.to_dict(), indent=2))
        return 1

    report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
