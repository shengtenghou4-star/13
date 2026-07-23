from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import tarfile
from collections import Counter
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from houearth.io import save_lightcurve_csv
from houearth.phase12_protocol import (
    PHASE12_BATCH_COUNT,
    PHASE12_BATCH_SIZE,
    PHASE12_POOL_SCHEMA,
    PHASE12_QUOTA_PER_STRATUM,
    PHASE12_SELECTED_TARGETS,
    PHASE12_STRATA,
    audit_nasa_transit_snapshot,
    fetch_nasa_ps_snapshot,
    load_phase12_pool,
    select_and_lock_phase12_inputs,
)
from houearth.private_campaign_protocol import utc_now_seconds
from houearth.provenance import canonical_json_sha256

ENVELOPE_SCHEMA = "houearth-phase12-selection-rsa-aesgcm-envelope-v1"
RECEIPT_SCHEMA = "houearth-phase12-selection-public-receipt-v1"
MANIFEST_SCHEMA = "houearth-phase12-selection-private-manifest-v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )


def build_manifest(root: Path, source_commit: str) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "PRIVATE_SELECTION_MANIFEST.json":
            files[path.relative_to(root).as_posix()] = {
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
    payload = {"schema": MANIFEST_SCHEMA, "source_commit": source_commit, "files": files}
    return {**payload, "manifest_sha256": canonical_json_sha256(payload)}


def reason_family(reason: str) -> str:
    if reason in {"nasa-confirmed-transiting-host", "stratum-quota-already-filled"}:
        return reason
    if reason.startswith("acquisition-or-quality:"):
        for token in (
            "products<", "products>", "distinct_sectors<", "cadences<",
            "baseline_days<", "median_cadence_days>",
        ):
            if token in reason:
                return "quality-" + token.rstrip("<>")
        return "acquisition-or-quality-other"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--sealed-output", type=Path, required=True)
    args = parser.parse_args()

    work = args.work_root.resolve()
    plaintext = work / "plaintext-selection-evidence"
    archive = work / "phase12-selection-evidence.tar.gz"
    sealed = args.sealed_output.resolve()
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(sealed, ignore_errors=True)
    work.mkdir(parents=True)
    sealed.mkdir(parents=True)

    public_key_bytes = args.public_key.read_bytes()
    public_key = serialization.load_pem_public_key(public_key_bytes)
    aad = f"{ENVELOPE_SCHEMA}:{args.source_commit}".encode("ascii")

    try:
        frozen_at = utc_now_seconds()
        pool, pool_sha = load_phase12_pool(args.pool)
        snapshot = fetch_nasa_ps_snapshot()
        audit = audit_nasa_transit_snapshot(pool, snapshot)
        selection = select_and_lock_phase12_inputs(
            pool,
            pool_sha256=pool_sha,
            nasa_audit=audit,
            nasa_snapshot=snapshot,
            source_commit=args.source_commit,
            frozen_at_utc=frozen_at,
        )

        plaintext.mkdir(parents=True, exist_ok=False)
        write_json(plaintext / "phase12_selection_lock.json", selection.selection_lock)
        write_json(plaintext / "campaign_lock.json", selection.campaign_lock)
        write_json(plaintext / "catalog_audit/nasa_transit_audit.json", audit)
        (plaintext / "catalog_audit/nasa_ps_snapshot.csv").write_bytes(snapshot)
        (plaintext / "catalog_audit/frozen_pool.csv").write_bytes(args.pool.read_bytes())
        for item in selection.selected:
            save_lightcurve_csv(
                item.lightcurve,
                plaintext / "campaign_inputs" / f"batch-{item.batch_id:02d}" / f"{item.target.target_id}.csv",
            )

        decisions = list(selection.selection_lock["decisions"])
        selected_products = [int(item.lightcurve.metadata["products"]) for item in selection.selected]
        selected_sectors = [
            len({int(value) for value in item.lightcurve.metadata["sectors"]})
            for item in selection.selected
        ]
        strata = {
            name: sum(item.target.stratum == name for item in selection.selected)
            for name in PHASE12_STRATA
        }
        batches = {
            str(index): sum(item.batch_id == index for item in selection.selected)
            for index in range(1, PHASE12_BATCH_COUNT + 1)
        }
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "source_commit": args.source_commit,
            "frozen_at_utc": frozen_at,
            "pool_schema": PHASE12_POOL_SCHEMA,
            "pool_rows": len(pool),
            "selected_targets": len(selection.selected),
            "selected_target_quota": PHASE12_SELECTED_TARGETS,
            "quota_per_stratum": PHASE12_QUOTA_PER_STRATUM,
            "selected_per_stratum": strata,
            "batch_count": PHASE12_BATCH_COUNT,
            "batch_size": PHASE12_BATCH_SIZE,
            "selected_per_batch": batches,
            "decision_counts": dict(sorted(Counter(str(row["decision"]) for row in decisions).items())),
            "nonselected_reason_counts": dict(sorted(Counter(
                reason_family(str(row["reason"])) for row in decisions if row["decision"] != "selected"
            ).items())),
            "total_downloaded_products": sum(selected_products),
            "minimum_products_per_selected_target": min(selected_products),
            "maximum_products_per_selected_target": max(selected_products),
            "total_distinct_sector_appearances": sum(selected_sectors),
            "minimum_distinct_sectors_per_selected_target": min(selected_sectors),
            "maximum_distinct_sectors_per_selected_target": max(selected_sectors),
            "pool_sha256": pool_sha,
            "nasa_snapshot_sha256": sha256_bytes(snapshot),
            "nasa_audit_sha256": audit["audit_sha256"],
            "selection_lock_sha256": selection.selection_lock["selection_lock_sha256"],
            "campaign_lock_sha256": selection.campaign_lock["campaign_lock_sha256"],
            "search_started": False,
            "surrogate_trials_executed": 0,
            "candidate_details_disclosed": False,
            "astronomical_claim": "none",
        }
        if len(selection.selected) != PHASE12_SELECTED_TARGETS:
            raise RuntimeError("selected-target quota changed after lock")
        if set(strata.values()) != {PHASE12_QUOTA_PER_STRATUM}:
            raise RuntimeError("stratum quotas changed after lock")
        if set(batches.values()) != {PHASE12_BATCH_SIZE}:
            raise RuntimeError("batch sizes changed after lock")
        write_json(plaintext / "PUBLIC_SELECTION_RECEIPT.json", receipt)
        manifest = build_manifest(plaintext, args.source_commit)
        write_json(plaintext / "PRIVATE_SELECTION_MANIFEST.json", manifest)

        with tarfile.open(archive, "w:gz") as handle:
            for path in sorted(plaintext.rglob("*")):
                if path.is_file():
                    handle.add(path, arcname=path.relative_to(plaintext))
        archive_bytes = archive.read_bytes()
        key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, archive_bytes, aad)
        wrapped_key = public_key.encrypt(
            key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        (sealed / "selection_evidence.aesgcm").write_bytes(ciphertext)
        (sealed / "wrapped_key.bin").write_bytes(wrapped_key)
        (sealed / "nonce.bin").write_bytes(nonce)
        write_json(sealed / "PUBLIC_SELECTION_RECEIPT.json", receipt)
        metadata = {
            "schema": ENVELOPE_SCHEMA,
            "source_commit": args.source_commit,
            "public_key_sha256": sha256_bytes(public_key_bytes),
            "aad_base64": base64.b64encode(aad).decode("ascii"),
            "plaintext_archive_sha256": sha256_bytes(archive_bytes),
            "plaintext_archive_size_bytes": len(archive_bytes),
            "ciphertext_sha256": sha256_bytes(ciphertext),
            "ciphertext_size_bytes": len(ciphertext),
            "wrapped_key_sha256": sha256_bytes(wrapped_key),
            "wrapped_key_size_bytes": len(wrapped_key),
            "nonce_sha256": sha256_bytes(nonce),
            "nonce_size_bytes": len(nonce),
            "private_manifest_sha256": manifest["manifest_sha256"],
            "candidate_details_in_public_artifact": False,
            "search_started": False,
            "astronomical_claim": "none",
        }
        write_json(sealed / "ENVELOPE_METADATA.json", metadata)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        print(json.dumps(metadata, indent=2, sort_keys=True))
    finally:
        shutil.rmtree(plaintext, ignore_errors=True)
        if archive.exists():
            archive.unlink()

    expected = {
        "ENVELOPE_METADATA.json", "PUBLIC_SELECTION_RECEIPT.json", "nonce.bin",
        "selection_evidence.aesgcm", "wrapped_key.bin",
    }
    actual = {path.name for path in sealed.iterdir() if path.is_file()}
    if actual != expected:
        raise RuntimeError(f"sealed artifact contains unexpected files: {sorted(actual)}")
    if plaintext.exists() or archive.exists():
        raise RuntimeError("plaintext selection evidence was not removed")


if __name__ == "__main__":
    main()
