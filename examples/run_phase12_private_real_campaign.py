from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.phase12_campaign import run_phase12_private_campaign


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the HOU-EARTH Phase 0.12 64-target batched multi-sector "
            "blind campaign. Candidate-level outputs must remain private."
        )
    )
    parser.add_argument(
        "--pool",
        type=Path,
        default=Path("data/phase12_batched_multisector_pool.csv"),
    )
    parser.add_argument("--private-evidence-sink", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--frozen-at-utc")
    args = parser.parse_args()

    result = run_phase12_private_campaign(
        pool_path=args.pool,
        output_directory=args.private_evidence_sink,
        source_commit=args.source_commit,
        frozen_at_utc=args.frozen_at_utc,
    )
    print(json.dumps(result.public_receipt, indent=2, sort_keys=True))
    print(json.dumps({"private_manifest_sha256": result.private_manifest_sha256}))


if __name__ == "__main__":
    main()
