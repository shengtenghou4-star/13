from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.phase12_locked_inputs import load_phase12_locked_selection
from houearth.phase13_sensitivity import (
    PHASE13_TOTAL_TRIALS,
    _blind_row_from_mapping,
    atomic_write_phase13_checkpoint,
    build_phase13_plan_lock,
    build_phase13_public_receipt,
    load_phase13_baselines,
    run_phase13_target,
    validate_phase13_target_checkpoint,
)
from houearth.provenance import canonical_json_sha256


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-directory", required=True)
    parser.add_argument("--phase12-search-evidence-directory", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--frozen-at-utc", required=True)
    parser.add_argument("--batch-id", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()

    selection = load_phase12_locked_selection(args.selection_directory)
    evidence = Path(args.phase12_search_evidence_directory)
    calibrations = _read_json(evidence / "private_raw/target_calibration_inputs.json")
    machine_json = _read_json(evidence / "candidate_evidence/machine_events.json")
    baselines = load_phase13_baselines(
        selection,
        target_calibration_inputs=calibrations,
        baseline_machine_events=machine_json,
    )
    plan = build_phase13_plan_lock(
        selection,
        baselines,
        source_commit=args.source_commit,
        frozen_at_utc=args.frozen_at_utc,
    )
    output = Path(args.output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan_path = output / "phase13_plan_lock.json"
    if plan_path.exists() and _read_json(plan_path) != plan:
        raise RuntimeError("existing Phase 0.13 plan lock differs")
    _write_json(plan_path, plan)

    baseline_by_id = {row.target_id: row for row in baselines}
    item_by_id = {row.target_id: row for row in selection.inputs}
    machine_rows = tuple(_blind_row_from_mapping(row) for row in machine_json)

    if not args.aggregate:
        if args.batch_id is None:
            raise SystemExit("--batch-id is required unless --aggregate is used")
        batch = [row for row in baselines if row.batch_id == args.batch_id]
        for ordinal, baseline in enumerate(batch, start=1):
            path = (
                output
                / "target_checkpoints"
                / f"batch-{args.batch_id:02d}"
                / f"{baseline.target_id}.json"
            )
            if path.exists():
                payload = _read_json(path)
                validate_phase13_target_checkpoint(
                    payload, plan_lock=plan, baseline=baseline
                )
                print(f"batch {args.batch_id} target {ordinal}/16 reused", flush=True)
                continue
            payload = run_phase13_target(
                item_by_id[baseline.target_id],
                baseline,
                plan_lock=plan,
                baseline_machine_rows=machine_rows,
            )
            atomic_write_phase13_checkpoint(payload, path)
            validate_phase13_target_checkpoint(
                _read_json(path), plan_lock=plan, baseline=baseline
            )
            print(f"batch {args.batch_id} target {ordinal}/16 complete", flush=True)
        hashes = [
            _read_json(path)["checkpoint_sha256"]
            for path in sorted(
                (
                    output
                    / "target_checkpoints"
                    / f"batch-{args.batch_id:02d}"
                ).glob("*.json")
            )
        ]
        receipt = {
            "batch_id": args.batch_id,
            "targets": len(hashes),
            "trials": len(hashes) * 32,
            "checkpoint_hashes_sha256": canonical_json_sha256(hashes),
        }
        _write_json(
            output / "batch_receipts" / f"batch-{args.batch_id:02d}.json",
            receipt,
        )
        return

    checkpoints = []
    for baseline in baselines:
        path = (
            output
            / "target_checkpoints"
            / f"batch-{baseline.batch_id:02d}"
            / f"{baseline.target_id}.json"
        )
        payload = _read_json(path)
        validate_phase13_target_checkpoint(
            payload, plan_lock=plan, baseline=baseline
        )
        checkpoints.append(payload)
    receipt = build_phase13_public_receipt(
        checkpoints,
        plan_lock=plan,
        baselines=baselines,
        baseline_machine_rows=machine_rows,
    )
    if receipt["trials"] != PHASE13_TOTAL_TRIALS:
        raise RuntimeError("Phase 0.13 aggregate trial count differs")
    _write_json(output / "PUBLIC_AGGREGATE_RECEIPT.json", receipt)


if __name__ == "__main__":
    main()
