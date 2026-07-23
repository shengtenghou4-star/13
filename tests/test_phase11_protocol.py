from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from houearth.core import LightCurve
from houearth.phase11_protocol import (
    PHASE11_QUOTA_PER_STRATUM,
    PHASE11_SELECTED_TARGETS,
    PHASE11_STRATA,
    PrivateCampaignError,
    audit_nasa_transit_snapshot,
    load_phase11_pool,
    select_and_lock_phase11_inputs,
)

SOURCE_COMMIT = "b" * 40
FROZEN_AT = "2026-07-23T10:30:00Z"
POOL_PATH = Path(__file__).parents[1] / "data" / "phase11_expanded_target_pool.csv"
SNAPSHOT_HEADER = "hostname,hd_name,hip_name,tic_id,pl_name,tran_flag,default_flag,rowupdate\n"


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _lightcurve(query: str, *, cadences: int = 1200, baseline: float = 20.0) -> LightCurve:
    time = np.linspace(0.0, baseline, cadences)
    return LightCurve(
        time,
        np.ones_like(time),
        np.full_like(time, 0.0002),
        target=query,
        metadata={
            "sectors": [1],
            "campaign_input_array_hashes": {
                "time_sha256": _digest(query + "-time"),
                "flux_sha256": _digest(query + "-flux"),
                "flux_err_sha256": _digest(query + "-err"),
                "combined_sha256": _digest(query + "-combined"),
            },
            "query_provenance_sha256": _digest(query + "-query"),
            "product_provenance_sha256": _digest(query + "-product"),
        },
    )


def test_pool_is_exact_ranked_three_stratum_design() -> None:
    pool, digest = load_phase11_pool(POOL_PATH)
    assert len(pool) == 18
    assert len(digest) == 64
    for stratum in PHASE11_STRATA:
        assert [row.pool_rank for row in pool if row.stratum == stratum] == list(range(1, 7))


def test_nasa_snapshot_blocks_confirmed_transiting_alias() -> None:
    pool, _ = load_phase11_pool(POOL_PATH)
    snapshot = (
        SNAPSHOT_HEADER
        + "61 Vir,HD 115617,,,61 Vir b,1,1,2026-07-01\n"
        + "HD 40307,HD 40307,,,HD 40307 b,0,1,2026-07-01\n"
    ).encode()
    audit = audit_nasa_transit_snapshot(pool, snapshot)
    assert audit["blocked_target_ids"] == ["hd-115617"]
    row = next(item for item in audit["targets"] if item["target_id"] == "hd-40307")
    assert row["matched_confirmed_planets"] == 1
    assert row["matched_transiting_planets"] == 0


def test_ranked_selection_uses_predeclared_fallbacks_without_search() -> None:
    pool, pool_sha = load_phase11_pool(POOL_PATH)
    snapshot = SNAPSHOT_HEADER.encode()
    audit = audit_nasa_transit_snapshot(pool, snapshot)
    failed_queries = {"HD 102365", "HD 85512", "HD 26965"}

    def downloader(query: str, **_: object) -> LightCurve:
        if query in failed_queries:
            raise RuntimeError("simulated unavailable product")
        return _lightcurve(query)

    result = select_and_lock_phase11_inputs(
        pool,
        pool_sha256=pool_sha,
        nasa_audit=audit,
        nasa_snapshot=snapshot,
        source_commit=SOURCE_COMMIT,
        frozen_at_utc=FROZEN_AT,
        downloader=downloader,
    )
    assert len(result.selected) == PHASE11_SELECTED_TARGETS
    counts = {
        stratum: sum(target.stratum == stratum for target, _ in result.selected)
        for stratum in PHASE11_STRATA
    }
    assert counts == {stratum: PHASE11_QUOTA_PER_STRATUM for stratum in PHASE11_STRATA}
    selected_ids = [target.target_id for target, _ in result.selected]
    assert "hd-76151" in selected_ids
    assert "hd-190360" in selected_ids
    assert "hd-10647" in selected_ids
    assert result.campaign_lock["manifest_sha256"] == result.selection_lock["selection_lock_sha256"]


def test_selection_aborts_when_quota_cannot_be_filled() -> None:
    pool, pool_sha = load_phase11_pool(POOL_PATH)
    snapshot = SNAPSHOT_HEADER.encode()
    audit = audit_nasa_transit_snapshot(pool, snapshot)

    def downloader(query: str, **_: object) -> LightCurve:
        if query in {"HD 146233", "HD 102365", "HD 207129", "HD 38858", "HD 76151", "HD 30495"}:
            raise RuntimeError("simulated solar-stratum collapse")
        return _lightcurve(query)

    with pytest.raises(PrivateCampaignError, match="could not fill"):
        select_and_lock_phase11_inputs(
            pool,
            pool_sha256=pool_sha,
            nasa_audit=audit,
            nasa_snapshot=snapshot,
            source_commit=SOURCE_COMMIT,
            frozen_at_utc=FROZEN_AT,
            downloader=downloader,
        )
