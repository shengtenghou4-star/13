from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from houearth.core import LightCurve
from houearth.phase12_protocol import (
    PHASE12_BATCH_COUNT,
    PHASE12_BATCH_SIZE,
    PHASE12_POOL_PER_STRATUM,
    PHASE12_QUOTA_PER_STRATUM,
    PHASE12_SELECTED_TARGETS,
    PHASE12_STRATA,
    PrivateCampaignError,
    audit_nasa_transit_snapshot,
    load_phase12_pool,
    select_and_lock_phase12_inputs,
)

SOURCE_COMMIT = "d" * 40
FROZEN_AT = "2026-07-23T11:15:00Z"
POOL_PATH = Path(__file__).parents[1] / "data" / "phase12_batched_multisector_pool.csv"
SNAPSHOT_HEADER = (
    "hostname,hd_name,hip_name,tic_id,pl_name,tran_flag,default_flag,rowupdate\n"
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _lightcurve(
    query: str,
    *,
    sectors: tuple[int, ...] = (1, 2),
    products: int = 2,
    cadences: int = 1800,
    baseline: float = 48.0,
) -> LightCurve:
    time = np.linspace(0.0, baseline, cadences)
    return LightCurve(
        time,
        np.ones_like(time),
        np.full_like(time, 0.0002),
        target=query,
        metadata={
            "sectors": list(sectors),
            "products": products,
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


def test_pool_is_exact_ranked_four_stratum_design() -> None:
    pool, digest = load_phase12_pool(POOL_PATH)
    assert len(pool) == 96
    assert len(digest) == 64
    for stratum in PHASE12_STRATA:
        rows = [row for row in pool if row.stratum == stratum]
        assert len(rows) == PHASE12_POOL_PER_STRATUM
        assert [row.pool_rank for row in rows] == list(
            range(1, PHASE12_POOL_PER_STRATUM + 1)
        )
        assert all(row.max_products == 4 for row in rows)


def test_nasa_snapshot_blocks_confirmed_transiting_alias() -> None:
    pool, _ = load_phase12_pool(POOL_PATH)
    snapshot = (
        SNAPSHOT_HEADER
        + "pi Mensae,HD 39091,,,pi Men c,1,1,2026-07-01\n"
        + "HD 1461,HD 1461,,,HD 1461 b,0,1,2026-07-01\n"
    ).encode()
    audit = audit_nasa_transit_snapshot(pool, snapshot)
    assert audit["blocked_target_ids"] == ["hd-39091"]
    row = next(item for item in audit["targets"] if item["target_id"] == "hd-1461")
    assert row["matched_confirmed_planets"] == 1
    assert row["matched_transiting_planets"] == 0


def test_selection_requires_multisector_input_and_uses_ranked_fallback() -> None:
    pool, pool_sha = load_phase12_pool(POOL_PATH)
    snapshot = SNAPSHOT_HEADER.encode()
    audit = audit_nasa_transit_snapshot(pool, snapshot)
    first_solar = next(row for row in pool if row.stratum == "solar-analog")

    def downloader(query: str, **_: object) -> LightCurve:
        if query == first_solar.query:
            return _lightcurve(query, sectors=(1,), products=1)
        return _lightcurve(query)

    result = select_and_lock_phase12_inputs(
        pool,
        pool_sha256=pool_sha,
        nasa_audit=audit,
        nasa_snapshot=snapshot,
        source_commit=SOURCE_COMMIT,
        frozen_at_utc=FROZEN_AT,
        downloader=downloader,
    )
    assert len(result.selected) == PHASE12_SELECTED_TARGETS
    assert first_solar.target_id not in {
        item.target.target_id for item in result.selected
    }
    counts = {
        stratum: sum(item.target.stratum == stratum for item in result.selected)
        for stratum in PHASE12_STRATA
    }
    assert counts == {
        stratum: PHASE12_QUOTA_PER_STRATUM for stratum in PHASE12_STRATA
    }
    batch_counts = {
        batch_id: sum(item.batch_id == batch_id for item in result.selected)
        for batch_id in range(1, PHASE12_BATCH_COUNT + 1)
    }
    assert batch_counts == {
        batch_id: PHASE12_BATCH_SIZE
        for batch_id in range(1, PHASE12_BATCH_COUNT + 1)
    }
    for batch_id in range(1, PHASE12_BATCH_COUNT + 1):
        for stratum in PHASE12_STRATA:
            assert sum(
                item.batch_id == batch_id and item.target.stratum == stratum
                for item in result.selected
            ) == 4
    assert (
        result.campaign_lock["manifest_sha256"]
        == result.selection_lock["selection_lock_sha256"]
    )


def test_selection_aborts_when_one_multisector_quota_cannot_be_filled() -> None:
    pool, pool_sha = load_phase12_pool(POOL_PATH)
    snapshot = SNAPSHOT_HEADER.encode()
    audit = audit_nasa_transit_snapshot(pool, snapshot)
    solar_queries = {
        row.query for row in pool if row.stratum == "solar-analog"
    }

    def downloader(query: str, **_: object) -> LightCurve:
        if query in solar_queries:
            return _lightcurve(query, sectors=(1,), products=1)
        return _lightcurve(query)

    with pytest.raises(PrivateCampaignError, match="could not fill"):
        select_and_lock_phase12_inputs(
            pool,
            pool_sha256=pool_sha,
            nasa_audit=audit,
            nasa_snapshot=snapshot,
            source_commit=SOURCE_COMMIT,
            frozen_at_utc=FROZEN_AT,
            downloader=downloader,
        )
