from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.candidate_protocol_validation import (
    CandidateProtocolValidationError,
    validate_frozen_candidate_table,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a frozen HOU-EARTH blind candidate table."
    )
    parser.add_argument("candidate_table", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional output path for the validation report JSON.",
    )
    args = parser.parse_args()

    payload = json.loads(args.candidate_table.read_text(encoding="utf-8"))
    report_path = args.report or args.candidate_table.with_name(
        "candidate_validation_report.json"
    )
    try:
        report = validate_frozen_candidate_table(payload)
    except CandidateProtocolValidationError as exc:
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
