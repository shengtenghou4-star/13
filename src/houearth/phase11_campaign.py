from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .candidate_campaign import PHASE09_SURROGATE_SEEDS, freeze_candidate_campaign_evidence
from .candidate_campaign_validation import validate_candidate_campaign_evidence
from .candidate_evidence import freeze_candidate_evidence, validate_candidate_evidence, write_candidate_evidence
from .candidate_protocol_validation import validate_frozen_candidate_table
from .io import download_tess_lightcurve, save_lightcurve_csv
from .phase11_protocol import (
    PHASE11_POOL_SCHEMA,
    PHASE11_SELECTED_TARGETS,
    Downloader,
    SnapshotFetcher,
    audit_nasa_transit_snapshot,
    fetch_nasa_ps_snapshot,
    load_phase11_pool,
    select_and_lock_phase11_inputs,
)
from .private_campaign import Searcher, SurrogateRunner, _file_sha256, _target_calibration, _write_json
from .private_campaign_protocol import require_private_evidence_sink, utc_now_seconds, validate_utc
from .provenance import canonical_json_sha256
from .search import search_single_transits
from .surrogates import run_surrogate_null_campaign

PHASE11_PRIVATE_RECEIPT_SCHEMA = "houearth-expanded-private-receipt-v0.11.0"
PHASE11_PRIVATE_MANIFEST_SCHEMA = "houearth-expanded-private-manifest-v0.11.0"


@dataclass(frozen=True)
class Phase11CampaignResult:
    output_directory: str
    public_receipt: dict[str, object]
    private_manifest_sha256: str


def _build_phase11_private_manifest(root: Path, source_commit: str) -> dict[str, object]:
    entries: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "PRIVATE_EVIDENCE_MANIFEST.json":
            continue
        entries[path.relative_to(root).as_posix()] = {
            "size_bytes": path.stat().st_size,
            "sha256": _file_sha256(path),
        }
    payload = {"schema": PHASE11_PRIVATE_MANIFEST_SCHEMA, "source_commit": source_commit, "files": entries}
    return {**payload, "manifest_sha256": canonical_json_sha256(payload)}


def run_phase11_private_campaign(
    *,
    pool_path: str | Path,
    output_directory: str | Path,
    source_commit: str,
    frozen_at_utc: str | None = None,
    environ: Mapping[str, str] | None = None,
    snapshot_fetcher: SnapshotFetcher = fetch_nasa_ps_snapshot,
    downloader: Downloader = download_tess_lightcurve,
    searcher: Searcher = search_single_transits,
    surrogate_runner: SurrogateRunner = run_surrogate_null_campaign,
) -> Phase11CampaignResult:
    """Run the ranked-pool Phase 0.11 blind expansion without public candidate details."""
    output = require_private_evidence_sink(output_directory, environ=environ)
    frozen_at = utc_now_seconds() if frozen_at_utc is None else frozen_at_utc
    validate_utc(frozen_at)
    pool, pool_sha256 = load_phase11_pool(pool_path)
    nasa_snapshot = snapshot_fetcher()
    nasa_audit = audit_nasa_transit_snapshot(pool, nasa_snapshot)
    selection = select_and_lock_phase11_inputs(
        pool,
        pool_sha256=pool_sha256,
        nasa_audit=nasa_audit,
        nasa_snapshot=nasa_snapshot,
        source_commit=source_commit,
        frozen_at_utc=frozen_at,
        downloader=downloader,
    )

    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "phase11_selection_lock.json", selection.selection_lock)
    _write_json(output / "campaign_lock.json", selection.campaign_lock)
    _write_json(output / "catalog_audit" / "nasa_transit_audit.json", nasa_audit)
    (output / "catalog_audit" / "nasa_ps_snapshot.csv").write_bytes(nasa_snapshot)
    (output / "catalog_audit" / "frozen_pool.csv").write_bytes(Path(pool_path).read_bytes())
    for target, lightcurve in selection.selected:
        save_lightcurve_csv(lightcurve, output / "campaign_inputs" / f"{target.target_id}.csv")

    all_rows: list[object] = []
    calibrations: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for target, lightcurve in selection.selected:
        rows, calibration, summary = _target_calibration(
            target, lightcurve, searcher=searcher, surrogate_runner=surrogate_runner
        )
        all_rows.extend(rows)
        calibrations.append(calibration)
        summaries.append(summary)
    calibrations.sort(key=lambda row: (str(row["target_id"]), str(row["campaign_input_combined_sha256"])))
    summaries.sort(key=lambda row: (str(row["target"]), str(row["sector_label"])))

    evidence = freeze_candidate_evidence(all_rows, source_commit=source_commit, frozen_at_utc=frozen_at)
    campaign = freeze_candidate_campaign_evidence(
        source_commit=source_commit,
        frozen_at_utc=frozen_at,
        campaign_lock=selection.campaign_lock,
        target_calibrations=calibrations,
        candidate_evidence=evidence.to_dict(),
    )
    table_report = validate_frozen_candidate_table(evidence.candidate_table.to_dict())
    evidence_report = validate_candidate_evidence(evidence.to_dict())
    campaign_report = validate_candidate_campaign_evidence(campaign)

    _write_json(output / "private_raw" / "target_calibration_inputs.json", calibrations)
    _write_json(output / "private_raw" / "surrogate_summaries.json", summaries)
    write_candidate_evidence(evidence, output / "candidate_evidence")
    _write_json(output / "candidate_campaign_evidence.json", campaign)
    _write_json(output / "validation" / "candidate_table_validation.json", table_report.to_dict())
    _write_json(output / "validation" / "candidate_evidence_validation.json", evidence_report.to_dict())
    _write_json(output / "validation" / "candidate_campaign_validation.json", campaign_report.to_dict())

    candidates = evidence.candidate_table.candidates
    receipt = {
        "schema": PHASE11_PRIVATE_RECEIPT_SCHEMA,
        "source_commit": source_commit,
        "frozen_at_utc": frozen_at,
        "pool_schema": PHASE11_POOL_SCHEMA,
        "pool_rows": len(pool),
        "selected_targets": len(selection.selected),
        "selected_target_quota": PHASE11_SELECTED_TARGETS,
        "excluded_or_unused_pool_rows": len(pool) - len(selection.selected),
        "surrogate_trials": len(selection.selected) * len(PHASE09_SURROGATE_SEEDS),
        "machine_events": len(all_rows),
        "candidate_rows": len(candidates),
        "screened_in": sum(row.blind_status == "screened-in" for row in candidates),
        "all_unopened": all(row.manual_review_status == "unopened" for row in candidates),
        "all_unclassified": all(row.astrophysical_status == "unclassified" for row in candidates),
        "pool_sha256": pool_sha256,
        "nasa_snapshot_sha256": hashlib.sha256(nasa_snapshot).hexdigest(),
        "nasa_audit_sha256": nasa_audit["audit_sha256"],
        "selection_lock_sha256": selection.selection_lock["selection_lock_sha256"],
        "campaign_lock_sha256": selection.campaign_lock["campaign_lock_sha256"],
        "candidate_table_sha256": evidence.candidate_table.table_sha256,
        "candidate_evidence_sha256": evidence.package_sha256,
        "candidate_campaign_evidence_sha256": campaign["package_sha256"],
        "all_validations_accepted": table_report.accepted and evidence_report.accepted and campaign_report.accepted,
        "candidate_details_disclosed": False,
        "astronomical_claim": "none",
    }
    _write_json(output / "PUBLIC_AGGREGATE_RECEIPT.json", receipt)
    manifest = _build_phase11_private_manifest(output, source_commit)
    _write_json(output / "PRIVATE_EVIDENCE_MANIFEST.json", manifest)
    return Phase11CampaignResult(
        output_directory=str(output),
        public_receipt=receipt,
        private_manifest_sha256=str(manifest["manifest_sha256"]),
    )
