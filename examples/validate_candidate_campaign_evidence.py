from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.candidate_campaign_validation import validate_candidate_campaign_evidence


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Independently validate a Phase 0.9 candidate campaign evidence package."
    )
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    report = validate_candidate_campaign_evidence(payload)
    encoded = json.dumps(report.to_dict(), indent=2)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
