from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .candidate_campaign import (
    PHASE09_FLATTEN_WINDOW_DAYS,
    PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION,
    PHASE09_MINIMUM_SEARCH_SNR,
    PHASE09_SEARCH_DURATION_FAMILY_DAYS,
    PHASE09_SURROGATE_BLOCK_DAYS,
    PHASE09_SURROGATE_SEEDS,
    build_blind_candidate_inputs,
    campaign_input_combined_sha256,
    freeze_candidate_campaign_evidence,
)
from .candidate_campaign_validation import validate_candidate_campaign_evidence
from .candidate_evidence import (
    freeze_candidate_evidence,
    validate_candidate_evidence,
    write_candidate_evidence,
)
from .candidate_protocol_validation import validate_frozen_candidate_table
from .core import LightCurve, SingleTransitEvent
from .io import download_tess_lightcurve, save_lightcurve_csv
from .private_campaign_protocol import (
    PHASE10_PRIVATE_MANIFEST_SCHEMA,
    PHASE10_PRIVATE_RECEIPT_SCHEMA,
    PrivateCampaignTarget,
    acquire_and_lock_inputs,
    load_phase10_manifest,
    require_private_evidence_sink,
    sector_label,
    utc_now_seconds,
    validate_utc,
)
from .provenance import canonical_json_sha256
from .search import search_single_transits
from .surrogates import (
    DEFAULT_GAP_FACTOR,
    SurrogateSummary,
    SurrogateTrial,
    run_surrogate_null_campaign,
)


@dataclass(frozen=True)
class PrivateCampaignResult:
    output_directory: str
    public_receipt: dict[str, object]
    private_manifest_sha256: str


Downloader = Callable[..., LightCurve]
Searcher = Callable[..., list[SingleTransitEvent]]
SurrogateRunner = Callable[..., tuple[list[SurrogateTrial], SurrogateSummary]]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
        "schema": PHASE10_PRIVATE_MANIFEST_SCHEMA,
        "source_commit": source_commit,
        "files": entries,
    }
    return {**payload, "manifest_sha256": canonical_json_sha256(payload)}


def _target_calibration(
    target: PrivateCampaignTarget,
    lightcurve: LightCurve,
    *,
    searcher: Searcher,
    surrogate_runner: SurrogateRunner,
) -> tuple[list[object], dict[str, object], dict[str, object]]:
    dimming = searcher(
        lightcurve,
        durations=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        flatten_window_days=PHASE09_FLATTEN_WINDOW_DAYS,
        min_snr=PHASE09_MINIMUM_SEARCH_SNR,
        max_events=PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION,
        direction="dimming",
    )
    brightening = searcher(
        lightcurve,
        durations=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        flatten_window_days=PHASE09_FLATTEN_WINDOW_DAYS,
        min_snr=PHASE09_MINIMUM_SEARCH_SNR,
        max_events=PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION,
        direction="brightening",
    )
    trials, summary = surrogate_runner(
        lightcurve,
        seeds=PHASE09_SURROGATE_SEEDS,
        block_days=PHASE09_SURROGATE_BLOCK_DAYS,
        durations=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        min_snr=PHASE09_MINIMUM_SEARCH_SNR,
        flatten_window_days=PHASE09_FLATTEN_WINDOW_DAYS,
        excluded_events=(),
        gap_factor=DEFAULT_GAP_FACTOR,
    )
    rows, receipt = build_blind_candidate_inputs(
        target_id=target.target_id,
        target_name=target.query,
        sector_label=sector_label(lightcurve),
        campaign_input_sha256=campaign_input_combined_sha256(lightcurve),
        search_duration_family_days=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        dimming_events=dimming,
        brightening_control_events=brightening,
        surrogate_trials=trials,
    )
    calibration = {
        "target_id": target.target_id,
        "target_name": target.query,
        "sector_label": sector_label(lightcurve),
        "campaign_input_combined_sha256": campaign_input_combined_sha256(lightcurve),
        "search_duration_family_days": list(PHASE09_SEARCH_DURATION_FAMILY_DAYS),
        "dimming_events": [event.to_dict() for event in dimming],
        "brightening_control_events": [event.to_dict() for event in brightening],
        "surrogate_trials": [trial.to_dict() for trial in trials],
        "calibration_receipt": receipt.to_dict(),
    }
    return rows, calibration, summary.to_dict()


def run_phase10_private_campaign(
    *,
    manifest_path: str | Path,
    output_directory: str | Path,
    source_commit: str,
    frozen_at_utc: str | None = None,
    environ: Mapping[str, str] | None = None,
    downloader: Downloader = download_tess_lightcurve,
    searcher: Searcher = search_single_transits,
    surrogate_runner: SurrogateRunner = run_surrogate_null_campaign,
) -> PrivateCampaignResult:
    """Run the three-target blind campaign and disclose only aggregate metadata."""
    output = require_private_evidence_sink(output_directory, environ=environ)
    frozen_at = utc_now_seconds() if frozen_at_utc is None else frozen_at_utc
    validate_utc(frozen_at)
    targets, excluded, manifest_sha256 = load_phase10_manifest(manifest_path)

    # Critical ordering: all three downloads and hashes must succeed before output or search.
    campaign_lock, acquired = acquire_and_lock_inputs(
        targets,
        excluded_targets=excluded,
        manifest_sha256=manifest_sha256,
        source_commit=source_commit,
        frozen_at_utc=frozen_at,
        downloader=downloader,
    )
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "campaign_lock.json", campaign_lock)
    for target, lightcurve in acquired:
        save_lightcurve_csv(
            lightcurve,
            output / "campaign_inputs" / f"{target.target_id}.csv",
        )

    all_rows: list[object] = []
    calibrations: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for target, lightcurve in acquired:
        rows, calibration, summary = _target_calibration(
            target,
            lightcurve,
            searcher=searcher,
            surrogate_runner=surrogate_runner,
        )
        all_rows.extend(rows)
        calibrations.append(calibration)
        summaries.append(summary)
    calibrations.sort(
        key=lambda row: (
            str(row["target_id"]),
            str(row["campaign_input_combined_sha256"]),
        )
    )
    summaries.sort(key=lambda row: (str(row["target"]), str(row["sector_label"])))

    evidence = freeze_candidate_evidence(
        all_rows,
        source_commit=source_commit,
        frozen_at_utc=frozen_at,
    )
    campaign = freeze_candidate_campaign_evidence(
        source_commit=source_commit,
        frozen_at_utc=frozen_at,
        campaign_lock=campaign_lock,
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
        "schema": PHASE10_PRIVATE_RECEIPT_SCHEMA,
        "source_commit": source_commit,
        "frozen_at_utc": frozen_at,
        "targets": len(acquired),
        "surrogate_trials": len(acquired) * len(PHASE09_SURROGATE_SEEDS),
        "machine_events": len(all_rows),
        "candidate_rows": len(candidates),
        "screened_in": sum(row.blind_status == "screened-in" for row in candidates),
        "all_unopened": all(
            row.manual_review_status == "unopened" for row in candidates
        ),
        "all_unclassified": all(
            row.astrophysical_status == "unclassified" for row in candidates
        ),
        "campaign_lock_sha256": campaign_lock["campaign_lock_sha256"],
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
    return PrivateCampaignResult(
        output_directory=str(output),
        public_receipt=receipt,
        private_manifest_sha256=str(manifest["manifest_sha256"]),
    )
