from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.private_campaign import run_phase10_private_campaign


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the HOU-EARTH Phase 0.10 three-target blind campaign. "
            "Candidate-level outputs must be written only to a private evidence sink."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/stratified_targets_v0.7.csv"),
    )
    parser.add_argument("--private-evidence-sink", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--frozen-at-utc")
    args = parser.parse_args()

    result = run_phase10_private_campaign(
        manifest_path=args.manifest,
        output_directory=args.private_evidence_sink,
        source_commit=args.source_commit,
        frozen_at_utc=args.frozen_at_utc,
    )
    # Deliberately print only candidate-safe aggregate metadata.
    print(json.dumps(result.public_receipt, indent=2, sort_keys=True))
    print(json.dumps({"private_manifest_sha256": result.private_manifest_sha256}))


if __name__ == "__main__":
    main()
