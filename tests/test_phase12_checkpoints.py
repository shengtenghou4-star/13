from __future__ import annotations

from pathlib import Path

import pytest

from houearth.phase12_checkpoints import (
    Phase12CheckpointError,
    Phase12CheckpointIdentity,
    build_phase12_batch_checkpoint_receipt,
    build_phase12_target_checkpoint,
    read_phase12_target_checkpoint,
    validate_phase12_batch_checkpoint_receipt,
    validate_phase12_target_checkpoint,
    write_phase12_json_atomic,
)


def identity(*, ordinal: int = 1) -> Phase12CheckpointIdentity:
    return Phase12CheckpointIdentity(
        source_commit="a" * 40,
        selection_lock_sha256="b" * 64,
        selection_campaign_lock_sha256="c" * 64,
        selection_private_manifest_sha256="d" * 64,
        locked_input_set_sha256="e" * 64,
        batch_id=2,
        ordinal_in_batch=ordinal,
        target_id=f"target-{ordinal}",
        query=f"query-{ordinal}",
        intended_role="quiet-star",
        sector_label="1;2",
        stratum_position=ordinal,
        csv_relative_path=f"campaign_inputs/batch-02/target-{ordinal}.csv",
        csv_sha256=(f"{ordinal:02x}" * 32)[:64],
        campaign_input_combined_sha256=(f"{ordinal + 32:02x}" * 32)[:64],
    )


def checkpoint(*, ordinal: int = 1) -> dict[str, object]:
    return build_phase12_target_checkpoint(
        identity=identity(ordinal=ordinal),
        rows=[{"event": ordinal}],
        calibration={"surrogate_trials": 64},
        summary={"trials": 64},
        elapsed_seconds=12.5,
    )


def test_atomic_round_trip_and_identity_binding(tmp_path: Path) -> None:
    payload = checkpoint()
    path = tmp_path / "batch-02" / "target-01.json"
    write_phase12_json_atomic(path, payload)
    assert read_phase12_target_checkpoint(path, expected_identity=identity()) == payload
    assert not list(path.parent.glob("*.tmp-*"))


def test_resealed_body_tampering_is_rejected() -> None:
    payload = checkpoint()
    payload["rows"][0]["event"] = 99
    with pytest.raises(Phase12CheckpointError, match="SHA-256"):
        validate_phase12_target_checkpoint(payload, expected_identity=identity())


def test_foreign_identity_is_rejected_even_with_valid_hash() -> None:
    payload = checkpoint(ordinal=1)
    with pytest.raises(Phase12CheckpointError, match="identity mismatch"):
        validate_phase12_target_checkpoint(payload, expected_identity=identity(ordinal=2))


def test_partial_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "partial.json"
    path.write_text('{"schema":', encoding="utf-8")
    with pytest.raises(Phase12CheckpointError, match="unreadable"):
        read_phase12_target_checkpoint(path)


def test_batch_receipt_requires_exact_unique_ordered_set() -> None:
    hashes = [f"{value:064x}" for value in range(16)]
    receipt = build_phase12_batch_checkpoint_receipt(
        source_commit="a" * 40,
        selection_lock_sha256="b" * 64,
        locked_input_set_sha256="c" * 64,
        batch_id=3,
        checkpoint_sha256s=hashes,
    )
    assert validate_phase12_batch_checkpoint_receipt(
        receipt, expected_batch_id=3
    ) == receipt
    with pytest.raises(Phase12CheckpointError, match="exactly 16"):
        build_phase12_batch_checkpoint_receipt(
            source_commit="a" * 40,
            selection_lock_sha256="b" * 64,
            locked_input_set_sha256="c" * 64,
            batch_id=3,
            checkpoint_sha256s=hashes[:-1],
        )
    with pytest.raises(Phase12CheckpointError, match="duplicate"):
        build_phase12_batch_checkpoint_receipt(
            source_commit="a" * 40,
            selection_lock_sha256="b" * 64,
            locked_input_set_sha256="c" * 64,
            batch_id=3,
            checkpoint_sha256s=[hashes[0]] * 16,
        )


def test_batch_receipt_rejects_tampering() -> None:
    hashes = [f"{value:064x}" for value in range(16)]
    receipt = build_phase12_batch_checkpoint_receipt(
        source_commit="a" * 40,
        selection_lock_sha256="b" * 64,
        locked_input_set_sha256="c" * 64,
        batch_id=1,
        checkpoint_sha256s=hashes,
    )
    receipt["target_checkpoint_sha256s"] = list(reversed(hashes))
    with pytest.raises(Phase12CheckpointError, match="SHA-256"):
        validate_phase12_batch_checkpoint_receipt(receipt, expected_batch_id=1)
