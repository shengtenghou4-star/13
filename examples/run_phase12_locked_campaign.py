from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.phase12_resume_campaign import run_phase12_locked_campaign


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the HOU-EARTH Phase 0.12 blind search from the exact frozen "
            "64-target selection package. Network re-downloads are forbidden."
        )
    )
    parser.add_argument("--selection-directory", type=Path, required=True)
    parser.add_argument("--private-evidence-sink", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--frozen-at-utc")
    args = parser.parse_args()

    result = run_phase12_locked_campaign(
        selection_directory=args.selection_directory,
        output_directory=args.private_evidence_sink,
        source_commit=args.source_commit,
        frozen_at_utc=args.frozen_at_utc,
    )
    print(json.dumps(result.public_receipt, indent=2, sort_keys=True))
    print(json.dumps({"private_manifest_sha256": result.private_manifest_sha256}))


if __name__ == "__main__":
    main()
