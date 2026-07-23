from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.phase11_campaign import run_phase11_private_campaign


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the HOU-EARTH Phase 0.11 ranked-pool blind expansion. "
            "Candidate-level outputs must remain inside a private evidence sink."
        )
    )
    parser.add_argument(
        "--pool",
        type=Path,
        default=Path("data/phase11_expanded_target_pool.csv"),
    )
    parser.add_argument("--private-evidence-sink", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--frozen-at-utc")
    args = parser.parse_args()

    result = run_phase11_private_campaign(
        pool_path=args.pool,
        output_directory=args.private_evidence_sink,
        source_commit=args.source_commit,
        frozen_at_utc=args.frozen_at_utc,
    )
    print(json.dumps(result.public_receipt, indent=2, sort_keys=True))
    print(json.dumps({"private_manifest_sha256": result.private_manifest_sha256}))


if __name__ == "__main__":
    main()
