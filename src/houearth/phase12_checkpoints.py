from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .provenance import canonical_json_sha256

PHASE12_TARGET_CHECKPOINT_SCHEMA = "houearth-phase12-target-checkpoint-v1"
PHASE12_BATCH_CHECKPOINT_RECEIPT_SCHEMA = "houearth-phase12-batch-checkpoint-receipt-v1"


class Phase12CheckpointError(ValueError):
    """Raised when restart-safe Phase 0.12 evidence is incomplete or altered."""


@dataclass(frozen=True)
class Phase12CheckpointIdentity:
    source_commit: str
    selection_lock_sha256: str
    selection_campaign_lock_sha256: str
    selection_private_manifest_sha256: str
    locked_input_set_sha256: str
    batch_id: int
    ordinal_in_batch: int
    target_id: str
    query: str
    intended_role: str
    sector_label: str
    stratum_position: int
    csv_relative_path: str
    csv_sha256: str
    campaign_input_combined_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": PHASE12_TARGET_CHECKPOINT_SCHEMA,
            **self.__dict__,
        }


def build_phase12_target_checkpoint(
    *,
    identity: Phase12CheckpointIdentity,
    rows: Sequence[Mapping[str, Any]],
    calibration: Mapping[str, Any],
    summary: Mapping[str, Any],
    elapsed_seconds: float,
) -> dict[str, object]:
    if elapsed_seconds < 0:
        raise Phase12CheckpointError("elapsed_seconds must be non-negative")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise Phase12CheckpointError("rows must be a sequence")
    body: dict[str, object] = {
        **identity.to_dict(),
        "rows": [dict(row) for row in rows],
        "calibration": dict(calibration),
        "summary": dict(summary),
        "elapsed_seconds": float(elapsed_seconds),
    }
    return {**body, "checkpoint_sha256": canonical_json_sha256(body)}


def validate_phase12_target_checkpoint(
    payload: Mapping[str, Any],
    *,
    expected_identity: Phase12CheckpointIdentity | None = None,
) -> dict[str, object]:
    checkpoint = dict(payload)
    recorded = checkpoint.pop("checkpoint_sha256", None)
    if checkpoint.get("schema") != PHASE12_TARGET_CHECKPOINT_SCHEMA:
        raise Phase12CheckpointError("unexpected target checkpoint schema")
    if recorded != canonical_json_sha256(checkpoint):
        raise Phase12CheckpointError("target checkpoint SHA-256 mismatch")
    if expected_identity is not None:
        for key, expected in expected_identity.to_dict().items():
            if checkpoint.get(key) != expected:
                raise Phase12CheckpointError(f"target checkpoint identity mismatch: {key}")
    if not isinstance(checkpoint.get("rows"), list):
        raise Phase12CheckpointError("target checkpoint rows are missing")
    if not isinstance(checkpoint.get("calibration"), dict):
        raise Phase12CheckpointError("target checkpoint calibration is missing")
    if not isinstance(checkpoint.get("summary"), dict):
        raise Phase12CheckpointError("target checkpoint summary is missing")
    return dict(payload)


def write_phase12_json_atomic(path: str | Path, payload: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + f".tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False),
            encoding="utf-8",
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_phase12_target_checkpoint(
    path: str | Path,
    *,
    expected_identity: Phase12CheckpointIdentity | None = None,
) -> dict[str, object]:
    source = Path(path)
    if not source.is_file():
        raise Phase12CheckpointError(f"target checkpoint is missing: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase12CheckpointError(f"target checkpoint is unreadable: {source}") from exc
    return validate_phase12_target_checkpoint(payload, expected_identity=expected_identity)


def build_phase12_batch_checkpoint_receipt(
    *,
    source_commit: str,
    selection_lock_sha256: str,
    locked_input_set_sha256: str,
    batch_id: int,
    checkpoint_sha256s: Sequence[str],
    expected_targets: int = 16,
) -> dict[str, object]:
    hashes = list(checkpoint_sha256s)
    if len(hashes) != expected_targets:
        raise Phase12CheckpointError(
            f"batch receipt requires exactly {expected_targets} target checkpoints"
        )
    if len(set(hashes)) != len(hashes):
        raise Phase12CheckpointError("batch receipt contains duplicate target checkpoints")
    body = {
        "schema": PHASE12_BATCH_CHECKPOINT_RECEIPT_SCHEMA,
        "source_commit": source_commit,
        "selection_lock_sha256": selection_lock_sha256,
        "locked_input_set_sha256": locked_input_set_sha256,
        "batch_id": int(batch_id),
        "targets": int(expected_targets),
        "target_checkpoint_sha256s": hashes,
    }
    return {**body, "receipt_sha256": canonical_json_sha256(body)}


def validate_phase12_batch_checkpoint_receipt(
    payload: Mapping[str, Any],
    *,
    expected_batch_id: int | None = None,
    expected_targets: int = 16,
) -> dict[str, object]:
    receipt = dict(payload)
    recorded = receipt.pop("receipt_sha256", None)
    if receipt.get("schema") != PHASE12_BATCH_CHECKPOINT_RECEIPT_SCHEMA:
        raise Phase12CheckpointError("unexpected batch checkpoint receipt schema")
    if recorded != canonical_json_sha256(receipt):
        raise Phase12CheckpointError("batch checkpoint receipt SHA-256 mismatch")
    if expected_batch_id is not None and receipt.get("batch_id") != expected_batch_id:
        raise Phase12CheckpointError("batch checkpoint receipt identity mismatch")
    hashes = receipt.get("target_checkpoint_sha256s")
    if not isinstance(hashes, list) or len(hashes) != expected_targets:
        raise Phase12CheckpointError("batch checkpoint receipt target count mismatch")
    if receipt.get("targets") != expected_targets:
        raise Phase12CheckpointError("batch checkpoint receipt declared target count mismatch")
    if len(set(hashes)) != len(hashes):
        raise Phase12CheckpointError("batch checkpoint receipt contains duplicate checkpoints")
    return dict(payload)
