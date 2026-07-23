from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from houearth.core import LightCurve, SingleTransitEvent
from houearth.io import save_lightcurve_csv
from houearth.phase12_locked_inputs import (
    PHASE12_SELECTION_PRIVATE_MANIFEST_SCHEMA,
    load_phase12_locked_selection,
)
from houearth.phase12_protocol import (
    audit_nasa_transit_snapshot,
    load_phase12_pool,
    select_and_lock_phase12_inputs,
)
from houearth.phase12_resume_campaign import run_phase12_locked_campaign
from houearth.private_campaign_protocol import PrivateCampaignError
from houearth.provenance import canonical_json_sha256, lightcurve_array_hashes
from houearth.surrogates import GAP_AWARE_METHOD, SurrogateSummary, SurrogateTrial

SELECTION_SOURCE = "a" * 40
SEARCH_SOURCE = "b" * 40
SELECTION_TIME = "2026-07-23T13:19:36Z"
SEARCH_TIME = "2026-07-23T14:00:00Z"
POOL_PATH = Path(__file__).parents[1] / "data" / "phase12_batched_multisector_pool.csv"
SNAPSHOT = (
    "hostname,hd_name,hip_name,tic_id,pl_name,tran_flag,default_flag,rowupdate\n"
).encode()


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _synthetic_lightcurve(query: str) -> LightCurve:
    time = np.linspace(0.0, 48.0, 1200)
    offset = (int(_digest(query)[:4], 16) % 100) * 1e-8
    flux = np.ones_like(time) + offset
    flux_error = np.full_like(time, 0.0002)
    base = LightCurve(
        time,
        flux,
        flux_error,
        target=query,
        metadata={"sectors": [1, 2], "products": 2},
    )
    hashes = lightcurve_array_hashes(base.time, base.flux, base.flux_err)
    return LightCurve(
        base.time,
        base.flux,
        base.flux_err,
        target=query,
        metadata={
            "sectors": [1, 2],
            "products": 2,
            "campaign_input_array_hashes": hashes,
            "query_provenance_sha256": _digest(query + "-query"),
            "product_provenance_sha256": _digest(query + "-products"),
        },
    )


def _rebuild_private_manifest(root: Path) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "PRIVATE_SELECTION_MANIFEST.json":
            continue
        files[path.relative_to(root).as_posix()] = {
            "size_bytes": path.stat().st_size,
            "sha256": _file_sha256(path),
        }
    payload = {
        "schema": PHASE12_SELECTION_PRIVATE_MANIFEST_SCHEMA,
        "source_commit": SELECTION_SOURCE,
        "files": files,
    }
    manifest = {**payload, "manifest_sha256": canonical_json_sha256(payload)}
    _write_json(root / "PRIVATE_SELECTION_MANIFEST.json", manifest)
    return manifest


def _build_locked_selection(root: Path) -> Path:
    pool, pool_sha = load_phase12_pool(POOL_PATH)
    audit = audit_nasa_transit_snapshot(pool, SNAPSHOT)
    selection = select_and_lock_phase12_inputs(
        pool,
        pool_sha256=pool_sha,
        nasa_audit=audit,
        nasa_snapshot=SNAPSHOT,
        source_commit=SELECTION_SOURCE,
        frozen_at_utc=SELECTION_TIME,
        downloader=lambda query, **_: _synthetic_lightcurve(query),
    )
    root.mkdir(parents=True)
    _write_json(root / "phase12_selection_lock.json", selection.selection_lock)
    _write_json(root / "campaign_lock.json", selection.campaign_lock)
    _write_json(root / "catalog_audit" / "nasa_transit_audit.json", audit)
    (root / "catalog_audit" / "nasa_ps_snapshot.csv").write_bytes(SNAPSHOT)
    (root / "catalog_audit" / "frozen_pool.csv").write_bytes(POOL_PATH.read_bytes())
    for item in selection.selected:
        save_lightcurve_csv(
            item.lightcurve,
            root
            / "campaign_inputs"
            / f"batch-{item.batch_id:02d}"
            / f"{item.target.target_id}.csv",
        )
    receipt = {
        "schema": "houearth-phase12-selection-public-receipt-v1",
        "source_commit": SELECTION_SOURCE,
        "selection_lock_sha256": selection.selection_lock["selection_lock_sha256"],
        "campaign_lock_sha256": selection.campaign_lock["campaign_lock_sha256"],
        "selected_targets": 64,
        "search_started": False,
        "surrogate_trials_executed": 0,
        "candidate_details_disclosed": False,
        "astronomical_claim": "none",
    }
    _write_json(root / "PUBLIC_SELECTION_RECEIPT.json", receipt)
    _rebuild_private_manifest(root)
    return root


def _rewrite_csv_with_tampered_flux(path: Path) -> None:
    values = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    values[0, 1] += 1e-4
    np.savetxt(
        path,
        values,
        delimiter=",",
        header="time_days,flux,flux_err",
        comments="",
    )


def _searcher(
    lightcurve: LightCurve, *, direction: str, **_: object
) -> list[SingleTransitEvent]:
    if direction == "dimming":
        return [
            SingleTransitEvent(
                target=lightcurve.target,
                center_time_days=15.0,
                duration_days=0.08,
                depth=0.0003,
                snr=10.0,
                local_points=6,
                direction="dimming",
            )
        ]
    return [
        SingleTransitEvent(
            target=lightcurve.target,
            center_time_days=28.0,
            duration_days=0.08,
            depth=0.0001,
            snr=6.0,
            local_points=6,
            direction="brightening",
        )
    ]


def _surrogate_runner(lightcurve: LightCurve, *, seeds, **_: object):
    sector_label = ";".join(str(value) for value in lightcurve.metadata["sectors"])
    trials = [
        SurrogateTrial(
            target=lightcurve.target,
            sector_label=sector_label,
            seed=int(seed),
            method=GAP_AWARE_METHOD,
            block_days=0.5,
            contiguous_segments=2,
            gap_factor=3.5,
            neutralized_events=0,
            neutralized_points=0,
            dimming_events=1,
            brightening_events=0,
            maximum_dimming_snr=5.0,
            maximum_brightening_snr=4.0,
            exceeded_dimming_threshold=True,
            exceeded_brightening_threshold=False,
        )
        for seed in seeds
    ]
    summary = SurrogateSummary(
        target=lightcurve.target,
        sector_label=sector_label,
        trials=len(trials),
        detection_threshold=5.0,
        minimum_segments=2,
        maximum_segments=2,
        gap_factor=3.5,
        neutralized_events=0,
        neutralized_points=0,
        trials_with_dimming_events=len(trials),
        trials_with_brightening_events=0,
        dimming_false_alarm_rate=1.0,
        brightening_false_alarm_rate=0.0,
        median_maximum_dimming_snr=5.0,
        p90_maximum_dimming_snr=5.0,
        p95_maximum_dimming_snr=5.0,
        maximum_dimming_snr=5.0,
        median_maximum_brightening_snr=4.0,
        p95_maximum_brightening_snr=4.0,
    )
    return trials, summary


def test_locked_selection_accepts_exact_frozen_bytes(tmp_path: Path) -> None:
    root = _build_locked_selection(tmp_path / "selection")
    locked = load_phase12_locked_selection(root)
    assert len(locked.inputs) == 64
    assert {item.batch_id for item in locked.inputs} == {1, 2, 3, 4}
    assert all(item.products == 2 and item.distinct_sectors == 2 for item in locked.inputs)
    assert len(locked.locked_input_set_sha256) == 64


def test_tampered_csv_is_rejected_even_after_manifest_is_resealed(tmp_path: Path) -> None:
    root = _build_locked_selection(tmp_path / "selection")
    csv_path = next((root / "campaign_inputs").glob("batch-*/*.csv"))
    _rewrite_csv_with_tampered_flux(csv_path)
    _rebuild_private_manifest(root)
    with pytest.raises(PrivateCampaignError, match="arrays do not match"):
        load_phase12_locked_selection(root)


def test_extra_csv_is_rejected_even_when_manifest_covers_it(tmp_path: Path) -> None:
    root = _build_locked_selection(tmp_path / "selection")
    source = next((root / "campaign_inputs").glob("batch-*/*.csv"))
    extra = root / "campaign_inputs" / "batch-01" / "unexpected.csv"
    shutil.copy2(source, extra)
    _rebuild_private_manifest(root)
    with pytest.raises(PrivateCampaignError, match="CSV set differs"):
        load_phase12_locked_selection(root)


def test_batch_reassignment_is_rejected_after_manifest_reseal(tmp_path: Path) -> None:
    root = _build_locked_selection(tmp_path / "selection")
    source = next((root / "campaign_inputs" / "batch-01").glob("*.csv"))
    destination = root / "campaign_inputs" / "batch-02" / source.name
    source.rename(destination)
    _rebuild_private_manifest(root)
    with pytest.raises(PrivateCampaignError, match="CSV set differs"):
        load_phase12_locked_selection(root)


def test_selection_lock_tamper_is_rejected_after_manifest_reseal(tmp_path: Path) -> None:
    root = _build_locked_selection(tmp_path / "selection")
    lock_path = root / "phase12_selection_lock.json"
    payload = json.loads(lock_path.read_text())
    payload["batch_size"] = 15
    _write_json(lock_path, payload)
    _rebuild_private_manifest(root)
    with pytest.raises(PrivateCampaignError, match="selection_lock_sha256"):
        load_phase12_locked_selection(root)


def test_campaign_lock_tamper_is_rejected_after_manifest_reseal(tmp_path: Path) -> None:
    root = _build_locked_selection(tmp_path / "selection")
    lock_path = root / "campaign_lock.json"
    payload = json.loads(lock_path.read_text())
    payload["minimum_search_snr"] = 4.9
    _write_json(lock_path, payload)
    _rebuild_private_manifest(root)
    with pytest.raises(PrivateCampaignError, match="campaign_lock_sha256"):
        load_phase12_locked_selection(root)


def test_resume_aborts_before_output_or_search_on_bad_input(tmp_path: Path) -> None:
    root = _build_locked_selection(tmp_path / "selection")
    csv_path = next((root / "campaign_inputs").glob("batch-*/*.csv"))
    _rewrite_csv_with_tampered_flux(csv_path)
    _rebuild_private_manifest(root)
    calls = 0

    def forbidden_search(*args, **kwargs):
        nonlocal calls
        calls += 1
        return []

    output = tmp_path / "output"
    with pytest.raises(PrivateCampaignError, match="arrays do not match"):
        run_phase12_locked_campaign(
            selection_directory=root,
            output_directory=output,
            source_commit=SEARCH_SOURCE,
            frozen_at_utc=SEARCH_TIME,
            environ={"HOU_PRIVATE_EVIDENCE_SINK": "1"},
            searcher=forbidden_search,
            surrogate_runner=_surrogate_runner,
        )
    assert calls == 0
    assert not output.exists()


def test_resume_uses_only_locked_inputs_and_one_global_evidence_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _build_locked_selection(tmp_path / "selection")

    def forbidden_download(*args, **kwargs):
        raise AssertionError("network downloader must never be called by locked resume")

    monkeypatch.setattr("houearth.io.download_tess_lightcurve", forbidden_download)
    monkeypatch.setattr("houearth.phase12_protocol.download_tess_lightcurve", forbidden_download)
    result = run_phase12_locked_campaign(
        selection_directory=root,
        output_directory=tmp_path / "output",
        source_commit=SEARCH_SOURCE,
        frozen_at_utc=SEARCH_TIME,
        environ={"HOU_PRIVATE_EVIDENCE_SINK": "1"},
        searcher=_searcher,
        surrogate_runner=_surrogate_runner,
    )
    receipt = result.public_receipt
    assert receipt["targets"] == 64
    assert receipt["locked_input_csv_files"] == 64
    assert receipt["surrogate_trials"] == 4096
    assert receipt["machine_events"] == 64
    assert receipt["candidate_rows"] == 64
    assert receipt["screened_in"] == 64
    assert receipt["network_downloads_permitted"] is False
    assert receipt["global_candidate_table"] is True
    assert receipt["global_multiple_testing_correction"] is True
    assert receipt["batchwise_candidate_tables"] is False
    assert receipt["all_unopened"] is True
    assert receipt["all_unclassified"] is True
    assert receipt["all_validations_accepted"] is True
    assert receipt["candidate_details_disclosed"] is False
    assert len(result.private_manifest_sha256) == 64
    output = Path(result.output_directory)
    assert (output / "locked_input_receipt.json").is_file()
    assert (output / "search_campaign_lock.json").is_file()
    assert (output / "candidate_campaign_evidence.json").is_file()
    assert not (output / "campaign_inputs").exists()
