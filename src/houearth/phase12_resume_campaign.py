from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .candidate_campaign import PHASE09_SURROGATE_SEEDS, freeze_candidate_campaign_evidence
from .candidate_campaign_validation import validate_candidate_campaign_evidence
from .candidate_evidence import (
    freeze_candidate_evidence,
    validate_candidate_evidence,
    write_candidate_evidence,
)
from .candidate_protocol_validation import validate_frozen_candidate_table
from .phase12_locked_inputs import (
    Phase12LockedSelection,
    build_phase12_resumed_campaign_lock,
    load_phase12_locked_selection,
)
from .phase12_protocol import PHASE12_BATCH_COUNT, PHASE12_BATCH_SIZE, PHASE12_SELECTED_TARGETS
from .private_campaign import (
    Searcher,
    SurrogateRunner,
    _file_sha256,
    _target_calibration,
    _write_json,
)
from .private_campaign_protocol import (
    require_private_evidence_sink,
    utc_now_seconds,
    validate_utc,
)
from .provenance import canonical_json_sha256
from .search import search_single_transits
from .surrogates import run_surrogate_null_campaign

PHASE12_RESUMED_RECEIPT_SCHEMA = "houearth-phase12-locked-search-receipt-v0.12.1"
PHASE12_RESUMED_MANIFEST_SCHEMA = "houearth-phase12-locked-search-manifest-v0.12.1"
PHASE12_LOCKED_INPUT_MODE = "phase12-frozen-selection-csv-no-network"


@dataclass(frozen=True)
class Phase12ResumedCampaignResult:
    output_directory: str
    public_receipt: dict[str, object]
    private_manifest_sha256: str


def _build_private_manifest(root: Path, source_commit: str) -> dict[str, object]:
    entries: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "PRIVATE_EVIDENCE_MANIFEST.json":
            continue
        entries[path.relative_to(root).as_posix()] = {
            "size_bytes": path.stat().st_size,
            "sha256": _file_sha256(path),
        }
    payload = {
        "schema": PHASE12_RESUMED_MANIFEST_SCHEMA,
        "source_commit": source_commit,
        "files": entries,
    }
    return {**payload, "manifest_sha256": canonical_json_sha256(payload)}


def _locked_input_receipt(locked: Phase12LockedSelection) -> dict[str, object]:
    payload = {
        "schema": "houearth-phase12-locked-input-receipt-v0.12.1",
        "selection_source_commit": locked.selection_lock["source_commit"],
        "selection_lock_sha256": locked.selection_lock["selection_lock_sha256"],
        "selection_campaign_lock_sha256": locked.selection_campaign_lock[
            "campaign_lock_sha256"
        ],
        "selection_private_manifest_sha256": locked.private_manifest[
            "manifest_sha256"
        ],
        "locked_input_set_sha256": locked.locked_input_set_sha256,
        "input_mode": PHASE12_LOCKED_INPUT_MODE,
        "network_downloads_permitted": False,
        "targets": [
            {
                "target_id": item.target_id,
                "query": item.query,
                "intended_role": item.intended_role,
                "sector_label": item.sector_label,
                "batch_id": item.batch_id,
                "stratum_position": item.stratum_position,
                "products": item.products,
                "distinct_sectors": item.distinct_sectors,
                "csv_relative_path": item.csv_relative_path,
                "csv_sha256": item.csv_sha256,
                "campaign_input_combined_sha256": item.lightcurve.metadata[
                    "campaign_input_array_hashes"
                ]["combined_sha256"],
            }
            for item in locked.inputs
        ],
    }
    return {**payload, "receipt_sha256": canonical_json_sha256(payload)}


def run_phase12_locked_campaign(
    *,
    selection_directory: str | Path,
    output_directory: str | Path,
    source_commit: str,
    frozen_at_utc: str | None = None,
    environ: Mapping[str, str] | None = None,
    searcher: Searcher = search_single_transits,
    surrogate_runner: SurrogateRunner = run_surrogate_null_campaign,
) -> Phase12ResumedCampaignResult:
    """Search the exact 64 frozen Phase 0.12 inputs without any re-download."""
    output = require_private_evidence_sink(output_directory, environ=environ)
    frozen_at = utc_now_seconds() if frozen_at_utc is None else frozen_at_utc
    validate_utc(frozen_at)

    # Critical ordering: every byte, hash, identity, and batch must validate before
    # output creation or the first real search invocation.
    locked = load_phase12_locked_selection(selection_directory)
    search_campaign_lock = build_phase12_resumed_campaign_lock(
        locked,
        source_commit=source_commit,
        frozen_at_utc=frozen_at,
    )
    locked_receipt = _locked_input_receipt(locked)

    if len(locked.inputs) != PHASE12_SELECTED_TARGETS:
        raise RuntimeError("Phase 0.12 locked input count changed after validation")

    output.mkdir(parents=True, exist_ok=False)
    _write_json(
        output / "selection_reference" / "phase12_selection_lock.json",
        locked.selection_lock,
    )
    _write_json(
        output / "selection_reference" / "selection_campaign_lock.json",
        locked.selection_campaign_lock,
    )
    _write_json(
        output / "selection_reference" / "public_selection_receipt.json",
        locked.public_selection_receipt,
    )
    _write_json(
        output / "selection_reference" / "private_selection_manifest.json",
        locked.private_manifest,
    )
    _write_json(output / "locked_input_receipt.json", locked_receipt)
    _write_json(output / "search_campaign_lock.json", search_campaign_lock)

    all_rows: list[object] = []
    private_calibrations: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    batch_receipts: list[dict[str, object]] = []
    for batch_id in range(1, PHASE12_BATCH_COUNT + 1):
        batch_inputs = [item for item in locked.inputs if item.batch_id == batch_id]
        if len(batch_inputs) != PHASE12_BATCH_SIZE:
            raise RuntimeError("Phase 0.12 locked batch size changed after validation")
        before_rows = len(all_rows)
        for item in batch_inputs:
            rows, calibration, summary = _target_calibration(
                item,
                item.lightcurve,
                searcher=searcher,
                surrogate_runner=surrogate_runner,
            )
            calibration["phase12_batch_id"] = batch_id
            calibration["phase12_intended_role"] = item.intended_role
            calibration["phase12_locked_csv_sha256"] = item.csv_sha256
            all_rows.extend(rows)
            private_calibrations.append(calibration)
            summaries.append(summary)
        batch_receipts.append(
            {
                "batch_id": batch_id,
                "targets": len(batch_inputs),
                "surrogate_trials": len(batch_inputs) * len(PHASE09_SURROGATE_SEEDS),
                "machine_events": len(all_rows) - before_rows,
                "target_ids_sha256": canonical_json_sha256(
                    [item.target_id for item in batch_inputs]
                ),
                "locked_csv_hashes_sha256": canonical_json_sha256(
                    [item.csv_sha256 for item in batch_inputs]
                ),
            }
        )

    campaign_calibrations = [
        {
            key: value
            for key, value in row.items()
            if key
            not in {
                "phase12_batch_id",
                "phase12_intended_role",
                "phase12_locked_csv_sha256",
            }
        }
        for row in private_calibrations
    ]
    campaign_calibrations.sort(
        key=lambda row: (
            str(row["target_id"]),
            str(row["campaign_input_combined_sha256"]),
        )
    )
    private_calibrations.sort(
        key=lambda row: (
            int(row["phase12_batch_id"]),
            str(row["phase12_intended_role"]),
            str(row["target_id"]),
        )
    )
    summaries.sort(key=lambda row: (str(row["target"]), str(row["sector_label"])))

    # One global freeze and one global BH correction. Batches never become
    # independent statistical campaigns.
    evidence = freeze_candidate_evidence(
        all_rows,
        source_commit=source_commit,
        frozen_at_utc=frozen_at,
    )
    campaign = freeze_candidate_campaign_evidence(
        source_commit=source_commit,
        frozen_at_utc=frozen_at,
        campaign_lock=search_campaign_lock,
        target_calibrations=campaign_calibrations,
        candidate_evidence=evidence.to_dict(),
    )
    table_report = validate_frozen_candidate_table(evidence.candidate_table.to_dict())
    evidence_report = validate_candidate_evidence(evidence.to_dict())
    campaign_report = validate_candidate_campaign_evidence(campaign)

    _write_json(
        output / "private_raw" / "target_calibration_inputs.json",
        private_calibrations,
    )
    _write_json(output / "private_raw" / "surrogate_summaries.json", summaries)
    _write_json(output / "private_raw" / "batch_receipts.json", batch_receipts)
    write_candidate_evidence(evidence, output / "candidate_evidence")
    _write_json(output / "candidate_campaign_evidence.json", campaign)
    _write_json(
        output / "validation" / "candidate_table_validation.json",
        table_report.to_dict(),
    )
    _write_json(
        output / "validation" / "candidate_evidence_validation.json",
        evidence_report.to_dict(),
    )
    _write_json(
        output / "validation" / "candidate_campaign_validation.json",
        campaign_report.to_dict(),
    )

    candidates = evidence.candidate_table.candidates
    receipt = {
        "schema": PHASE12_RESUMED_RECEIPT_SCHEMA,
        "source_commit": source_commit,
        "frozen_at_utc": frozen_at,
        "selection_source_commit": locked.selection_lock["source_commit"],
        "input_mode": PHASE12_LOCKED_INPUT_MODE,
        "network_downloads_permitted": False,
        "locked_input_csv_files": len(locked.inputs),
        "locked_input_set_sha256": locked.locked_input_set_sha256,
        "selection_lock_sha256": locked.selection_lock["selection_lock_sha256"],
        "selection_campaign_lock_sha256": locked.selection_campaign_lock[
            "campaign_lock_sha256"
        ],
        "selection_private_manifest_sha256": locked.private_manifest[
            "manifest_sha256"
        ],
        "locked_input_receipt_sha256": locked_receipt["receipt_sha256"],
        "targets": len(locked.inputs),
        "batch_count": PHASE12_BATCH_COUNT,
        "batch_size": PHASE12_BATCH_SIZE,
        "surrogate_trials": len(locked.inputs) * len(PHASE09_SURROGATE_SEEDS),
        "machine_events": len(all_rows),
        "candidate_rows": len(candidates),
        "screened_in": sum(row.blind_status == "screened-in" for row in candidates),
        "all_unopened": all(
            row.manual_review_status == "unopened" for row in candidates
        ),
        "all_unclassified": all(
            row.astrophysical_status == "unclassified" for row in candidates
        ),
        "global_candidate_table": True,
        "global_multiple_testing_correction": True,
        "batchwise_candidate_tables": False,
        "batch_receipts_sha256": canonical_json_sha256(batch_receipts),
        "search_campaign_lock_sha256": search_campaign_lock["campaign_lock_sha256"],
        "candidate_table_sha256": evidence.candidate_table.table_sha256,
        "candidate_evidence_sha256": evidence.package_sha256,
        "candidate_campaign_evidence_sha256": campaign["package_sha256"],
        "all_validations_accepted": (
            table_report.accepted
            and evidence_report.accepted
            and campaign_report.accepted
        ),
        "candidate_details_disclosed": False,
        "astronomical_claim": "none",
    }
    _write_json(output / "PUBLIC_AGGREGATE_RECEIPT.json", receipt)
    manifest = _build_private_manifest(output, source_commit)
    _write_json(output / "PRIVATE_EVIDENCE_MANIFEST.json", manifest)
    return Phase12ResumedCampaignResult(
        output_directory=str(output),
        public_receipt=receipt,
        private_manifest_sha256=str(manifest["manifest_sha256"]),
    )
