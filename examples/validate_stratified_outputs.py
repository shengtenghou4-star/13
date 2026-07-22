from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.protocol_validation import (
    ProtocolValidationError,
    validate_phase07_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a HOU-EARTH Phase 0.7 stratified evidence package."
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        nargs="?",
        default=Path("outputs/stratified-physical-v0.7"),
    )
    args = parser.parse_args()
    summary_path = args.output_dir / "batch_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    try:
        report = validate_phase07_summary(summary)
    except ProtocolValidationError as exc:
        report = exc.report
        (args.output_dir / "protocol_validation.json").write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
        print(json.dumps(report.to_dict(), indent=2))
        return 1

    (args.output_dir / "protocol_validation.json").write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
