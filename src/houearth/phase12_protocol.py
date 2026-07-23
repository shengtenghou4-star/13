from __future__ import annotations

import csv
import hashlib
import io
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .candidate_campaign import (
    PHASE09_CAMPAIGN_LOCK_SCHEMA,
    PHASE09_ELIGIBLE_TARGET_RULE,
    PHASE09_FLATTEN_WINDOW_DAYS,
    PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION,
    PHASE09_MINIMUM_SEARCH_SNR,
    PHASE09_SEARCH_DURATION_FAMILY_DAYS,
    PHASE09_SURROGATE_BLOCK_DAYS,
    PHASE09_SURROGATE_SEEDS,
    campaign_input_combined_sha256,
)
from .core import LightCurve
from .io import download_tess_lightcurve
from .private_campaign_protocol import (
    PrivateCampaignError,
    provenance_sha,
    sector_label,
    validate_utc,
)
from .provenance import canonical_json_sha256
from .surrogates import DEFAULT_GAP_FACTOR, GAP_AWARE_METHOD

PHASE12_POOL_SCHEMA = "houearth-batched-multisector-pool-v0.12.0"
PHASE12_SELECTION_LOCK_SCHEMA = "houearth-batched-multisector-selection-lock-v0.12.0"
PHASE12_POOL_SOURCE = "predeclared-nearby-multisector-pool-v1"
PHASE12_STRATA = ("solar-analog", "rv-host", "cool-dwarf", "harder-control")
PHASE12_QUOTA_PER_STRATUM = 16
PHASE12_POOL_PER_STRATUM = 24
PHASE12_SELECTED_TARGETS = len(PHASE12_STRATA) * PHASE12_QUOTA_PER_STRATUM
PHASE12_BATCH_COUNT = 4
PHASE12_BATCH_SIZE = PHASE12_SELECTED_TARGETS // PHASE12_BATCH_COUNT
PHASE12_PER_STRATUM_PER_BATCH = PHASE12_QUOTA_PER_STRATUM // PHASE12_BATCH_COUNT
PHASE12_MIN_PRODUCTS = 2
PHASE12_MIN_DISTINCT_SECTORS = 2
PHASE12_MAX_PRODUCTS = 4
PHASE12_MIN_CADENCES = 1000
PHASE12_MIN_BASELINE_DAYS = 20.0
PHASE12_MAX_MEDIAN_CADENCE_DAYS = 0.1
PHASE12_NASA_TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
PHASE12_NASA_QUERY = (
    "select hostname,hd_name,hip_name,tic_id,pl_name,tran_flag,default_flag,rowupdate "
    "from ps where default_flag=1"
)
_POOL_COLUMNS = (
    "target_id", "query", "author", "sectors", "max_products", "stratum",
    "pool_rank", "selection_source", "surrogate_policy", "archive_aliases", "notes",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Phase12PoolTarget:
    target_id: str
    query: str
    author: str | None
    sectors: tuple[int, ...]
    max_products: int
    stratum: str
    pool_rank: int
    selection_source: str
    surrogate_policy: str
    archive_aliases: tuple[str, ...]
    notes: str

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "sectors": list(self.sectors),
            "archive_aliases": list(self.archive_aliases),
        }


@dataclass(frozen=True)
class Phase12SelectedInput:
    target: Phase12PoolTarget
    lightcurve: LightCurve
    batch_id: int
    stratum_position: int


@dataclass(frozen=True)
class Phase12SelectionResult:
    selection_lock: dict[str, object]
    campaign_lock: dict[str, object]
    selected: tuple[Phase12SelectedInput, ...]
    nasa_snapshot: bytes


Downloader = Callable[..., LightCurve]
SnapshotFetcher = Callable[[], bytes]


def _parse_sectors(value: str) -> tuple[int, ...]:
    text = value.strip()
    if not text:
        return ()
    values = [int(token.strip()) for token in re.split(r"[;,]", text) if token.strip()]
    if any(value < 1 for value in values) or len(values) != len(set(values)):
        raise ValueError("TESS sectors must be unique positive integers")
    return tuple(sorted(values))


def _parse_aliases(value: str) -> tuple[str, ...]:
    aliases = tuple(token.strip() for token in value.split(";") if token.strip())
    if not aliases or len(aliases) != len(set(aliases)):
        raise ValueError("archive_aliases must contain unique non-empty aliases")
    return aliases


def load_phase12_pool(path: str | Path) -> tuple[tuple[Phase12PoolTarget, ...], str]:
    path = Path(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != _POOL_COLUMNS:
            raise ValueError("Phase 0.12 pool must use the exact frozen columns and order")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    expected_rows = len(PHASE12_STRATA) * PHASE12_POOL_PER_STRATUM
    if len(rows) != expected_rows:
        raise ValueError(f"Phase 0.12 requires exactly {expected_rows} ranked pool rows")
    if len({row["target_id"] for row in rows}) != len(rows):
        raise ValueError("Phase 0.12 pool contains duplicate target IDs")
    if len({row["query"] for row in rows}) != len(rows):
        raise ValueError("Phase 0.12 pool contains duplicate target queries")
    parsed: list[Phase12PoolTarget] = []
    for row in rows:
        if row["stratum"] not in PHASE12_STRATA:
            raise ValueError("Phase 0.12 pool contains an unknown stratum")
        if row["selection_source"] != PHASE12_POOL_SOURCE:
            raise ValueError("Phase 0.12 selection source is not frozen")
        if row["surrogate_policy"] != "unmasked-null":
            raise ValueError("Phase 0.12 pool must use unmasked-null for every row")
        try:
            max_products = int(row["max_products"])
            rank = int(row["pool_rank"])
        except ValueError as exc:
            raise ValueError("max_products and pool_rank must be exact integers") from exc
        if max_products != PHASE12_MAX_PRODUCTS or rank < 1:
            raise ValueError("Phase 0.12 max_products is frozen at four and ranks must be positive")
        parsed.append(
            Phase12PoolTarget(
                target_id=row["target_id"],
                query=row["query"],
                author=row["author"] or None,
                sectors=_parse_sectors(row["sectors"]),
                max_products=max_products,
                stratum=row["stratum"],
                pool_rank=rank,
                selection_source=row["selection_source"],
                surrogate_policy=row["surrogate_policy"],
                archive_aliases=_parse_aliases(row["archive_aliases"]),
                notes=row["notes"],
            )
        )
    stratum_index = {name: index for index, name in enumerate(PHASE12_STRATA)}
    parsed.sort(key=lambda item: (stratum_index[item.stratum], item.pool_rank, item.target_id))
    for stratum in PHASE12_STRATA:
        ranks = [item.pool_rank for item in parsed if item.stratum == stratum]
        if ranks != list(range(1, PHASE12_POOL_PER_STRATUM + 1)):
            raise ValueError(f"Phase 0.12 stratum {stratum} must use ranks 1..24 exactly")
    return tuple(parsed), digest


def fetch_nasa_ps_snapshot(timeout: float = 60.0) -> bytes:
    query = urllib.parse.urlencode({"query": PHASE12_NASA_QUERY, "format": "csv"})
    request = urllib.request.Request(
        f"{PHASE12_NASA_TAP_URL}?{query}",
        headers={"User-Agent": "HOU-EARTH/0.12 catalog-audit"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = response.read()
    if not payload:
        raise PrivateCampaignError("NASA Exoplanet Archive returned an empty snapshot")
    return payload


def _norm_alias(value: str) -> str:
    return " ".join(value.upper().replace("−", "-").split())


def audit_nasa_transit_snapshot(
    pool: Sequence[Phase12PoolTarget], snapshot: bytes
) -> dict[str, object]:
    snapshot_sha = hashlib.sha256(snapshot).hexdigest()
    try:
        text = snapshot.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PrivateCampaignError("NASA snapshot is not valid UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text))
    required = {
        "hostname", "hd_name", "hip_name", "tic_id", "pl_name",
        "tran_flag", "default_flag", "rowupdate",
    }
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise PrivateCampaignError("NASA snapshot columns are missing or inconsistent")
    alias_index: dict[str, list[dict[str, str]]] = {}
    archive_rows = 0
    for raw in reader:
        row = {key: (raw.get(key) or "").strip() for key in required}
        if row["default_flag"] not in {"1", "1.0"}:
            continue
        archive_rows += 1
        for field in ("hostname", "hd_name", "hip_name", "tic_id"):
            if row[field]:
                alias_index.setdefault(_norm_alias(row[field]), []).append(row)
    audits: list[dict[str, object]] = []
    blocked_ids: set[str] = set()
    for target in pool:
        matches: dict[tuple[str, str], dict[str, str]] = {}
        aliases = {_norm_alias(alias) for alias in target.archive_aliases}
        aliases.add(_norm_alias(target.query))
        for alias in aliases:
            for row in alias_index.get(alias, []):
                matches[(row["hostname"], row["pl_name"])] = row
        rows = sorted(matches.values(), key=lambda row: (row["hostname"], row["pl_name"]))
        transiting = [row for row in rows if row["tran_flag"] in {"1", "1.0"}]
        if transiting:
            blocked_ids.add(target.target_id)
        audits.append(
            {
                "target_id": target.target_id,
                "query": target.query,
                "archive_aliases": list(target.archive_aliases),
                "matched_confirmed_planets": len(rows),
                "matched_transiting_planets": len(transiting),
                "archive_status": (
                    "blocked-confirmed-transiting-host"
                    if transiting
                    else "eligible-no-confirmed-transiting-planet"
                ),
            }
        )
    audits.sort(key=lambda row: str(row["target_id"]))
    payload = {
        "schema": "houearth-nasa-transit-audit-v0.12.0",
        "tap_url": PHASE12_NASA_TAP_URL,
        "adql": PHASE12_NASA_QUERY,
        "snapshot_sha256": snapshot_sha,
        "snapshot_rows": archive_rows,
        "targets": audits,
        "blocked_target_ids": sorted(blocked_ids),
    }
    return {**payload, "audit_sha256": canonical_json_sha256(payload)}


def _sector_request(target: Phase12PoolTarget) -> int | list[int] | None:
    if not target.sectors:
        return None
    return target.sectors[0] if len(target.sectors) == 1 else list(target.sectors)


def _multisector_quality(lightcurve: LightCurve) -> tuple[str | None, dict[str, int]]:
    products = lightcurve.metadata.get("products")
    sectors = lightcurve.metadata.get("sectors")
    product_count = int(products) if isinstance(products, int) and not isinstance(products, bool) else 0
    sector_values = (
        sorted({int(value) for value in sectors})
        if isinstance(sectors, (list, tuple)) and sectors
        else []
    )
    metrics = {"products": product_count, "distinct_sectors": len(sector_values)}
    if product_count < PHASE12_MIN_PRODUCTS:
        return f"products<{PHASE12_MIN_PRODUCTS}", metrics
    if product_count > PHASE12_MAX_PRODUCTS:
        return f"products>{PHASE12_MAX_PRODUCTS}", metrics
    if len(sector_values) < PHASE12_MIN_DISTINCT_SECTORS:
        return f"distinct_sectors<{PHASE12_MIN_DISTINCT_SECTORS}", metrics
    if len(lightcurve.time) < PHASE12_MIN_CADENCES:
        return f"cadences<{PHASE12_MIN_CADENCES}", metrics
    if lightcurve.baseline < PHASE12_MIN_BASELINE_DAYS:
        return f"baseline_days<{PHASE12_MIN_BASELINE_DAYS}", metrics
    if lightcurve.cadence > PHASE12_MAX_MEDIAN_CADENCE_DAYS:
        return f"median_cadence_days>{PHASE12_MAX_MEDIAN_CADENCE_DAYS}", metrics
    return None, metrics


def select_and_lock_phase12_inputs(
    pool: Sequence[Phase12PoolTarget],
    *,
    pool_sha256: str,
    nasa_audit: Mapping[str, object],
    nasa_snapshot: bytes,
    source_commit: str,
    frozen_at_utc: str,
    downloader: Downloader = download_tess_lightcurve,
) -> Phase12SelectionResult:
    if not isinstance(source_commit, str) or _SHA40.fullmatch(source_commit) is None:
        raise ValueError("source_commit must be a lowercase 40-character Git SHA")
    validate_utc(frozen_at_utc)
    if _SHA256.fullmatch(pool_sha256) is None:
        raise ValueError("pool_sha256 must be a lowercase SHA-256")
    if nasa_audit.get("snapshot_sha256") != hashlib.sha256(nasa_snapshot).hexdigest():
        raise ValueError("NASA audit is not bound to the supplied snapshot")
    audit_hash = nasa_audit.get("audit_sha256")
    if not isinstance(audit_hash, str) or _SHA256.fullmatch(audit_hash) is None:
        raise ValueError("NASA audit SHA-256 is missing or invalid")
    expected_audit = canonical_json_sha256(
        {key: value for key, value in nasa_audit.items() if key != "audit_sha256"}
    )
    if audit_hash != expected_audit:
        raise ValueError("NASA audit SHA-256 does not match its payload")

    blocked = set(nasa_audit.get("blocked_target_ids", ()))
    selected: list[Phase12SelectedInput] = []
    decisions: list[dict[str, object]] = []
    selected_by_stratum = {stratum: 0 for stratum in PHASE12_STRATA}

    for target in pool:
        if target.target_id in blocked:
            decisions.append(
                {
                    "target_id": target.target_id,
                    "query": target.query,
                    "stratum": target.stratum,
                    "pool_rank": target.pool_rank,
                    "decision": "excluded",
                    "reason": "nasa-confirmed-transiting-host",
                }
            )
            continue
        if selected_by_stratum[target.stratum] >= PHASE12_QUOTA_PER_STRATUM:
            decisions.append(
                {
                    "target_id": target.target_id,
                    "query": target.query,
                    "stratum": target.stratum,
                    "pool_rank": target.pool_rank,
                    "decision": "not-needed",
                    "reason": "stratum-quota-already-filled",
                }
            )
            continue
        try:
            lightcurve = downloader(
                target.query,
                author=target.author,
                sector=_sector_request(target),
                max_products=target.max_products,
            )
            campaign_hash = campaign_input_combined_sha256(lightcurve)
            provenance_sha(lightcurve, "query_provenance_sha256")
            provenance_sha(lightcurve, "product_provenance_sha256")
            sector_label(lightcurve)
            reason, metrics = _multisector_quality(lightcurve)
            if reason is not None:
                raise PrivateCampaignError(reason)
        except Exception as exc:
            decisions.append(
                {
                    "target_id": target.target_id,
                    "query": target.query,
                    "stratum": target.stratum,
                    "pool_rank": target.pool_rank,
                    "decision": "excluded",
                    "reason": f"acquisition-or-quality:{type(exc).__name__}:{exc}",
                }
            )
            continue

        position = selected_by_stratum[target.stratum] + 1
        batch_id = ((position - 1) // PHASE12_PER_STRATUM_PER_BATCH) + 1
        selected_by_stratum[target.stratum] = position
        selected.append(
            Phase12SelectedInput(
                target=target,
                lightcurve=lightcurve,
                batch_id=batch_id,
                stratum_position=position,
            )
        )
        decisions.append(
            {
                "target_id": target.target_id,
                "query": target.query,
                "stratum": target.stratum,
                "pool_rank": target.pool_rank,
                "decision": "selected",
                "reason": "first-ranked-eligible-multisector-target-within-stratum",
                "campaign_input_combined_sha256": campaign_hash,
                "sector_label": sector_label(lightcurve),
                "cadences": len(lightcurve.time),
                "baseline_days": lightcurve.baseline,
                "median_cadence_days": lightcurve.cadence,
                "products": metrics["products"],
                "distinct_sectors": metrics["distinct_sectors"],
                "stratum_selected_position": position,
                "batch_id": batch_id,
            }
        )

    if any(value != PHASE12_QUOTA_PER_STRATUM for value in selected_by_stratum.values()):
        counts = ", ".join(f"{key}={value}" for key, value in selected_by_stratum.items())
        raise PrivateCampaignError(
            "Phase 0.12 ranked pool could not fill the frozen multisector quotas; " + counts
        )
    if len(selected) != PHASE12_SELECTED_TARGETS:
        raise PrivateCampaignError("Phase 0.12 selected-target count is inconsistent")

    batch_counts = {
        batch_id: sum(item.batch_id == batch_id for item in selected)
        for batch_id in range(1, PHASE12_BATCH_COUNT + 1)
    }
    if any(count != PHASE12_BATCH_SIZE for count in batch_counts.values()):
        raise PrivateCampaignError("Phase 0.12 deterministic batch sizes are inconsistent")
    for batch_id in range(1, PHASE12_BATCH_COUNT + 1):
        for stratum in PHASE12_STRATA:
            count = sum(
                item.batch_id == batch_id and item.target.stratum == stratum
                for item in selected
            )
            if count != PHASE12_PER_STRATUM_PER_BATCH:
                raise PrivateCampaignError(
                    "Phase 0.12 batch-stratum balance is inconsistent"
                )

    batch_plan = [
        {
            "batch_id": batch_id,
            "target_ids": [
                item.target.target_id for item in selected if item.batch_id == batch_id
            ],
        }
        for batch_id in range(1, PHASE12_BATCH_COUNT + 1)
    ]
    selection_payload = {
        "schema": PHASE12_SELECTION_LOCK_SCHEMA,
        "source_commit": source_commit,
        "frozen_at_utc": frozen_at_utc,
        "pool_schema": PHASE12_POOL_SCHEMA,
        "pool_sha256": pool_sha256,
        "pool_source": PHASE12_POOL_SOURCE,
        "nasa_snapshot_sha256": nasa_audit["snapshot_sha256"],
        "nasa_audit_sha256": audit_hash,
        "strata": list(PHASE12_STRATA),
        "pool_per_stratum": PHASE12_POOL_PER_STRATUM,
        "quota_per_stratum": PHASE12_QUOTA_PER_STRATUM,
        "selected_targets": PHASE12_SELECTED_TARGETS,
        "batch_count": PHASE12_BATCH_COUNT,
        "batch_size": PHASE12_BATCH_SIZE,
        "per_stratum_per_batch": PHASE12_PER_STRATUM_PER_BATCH,
        "minimum_products": PHASE12_MIN_PRODUCTS,
        "minimum_distinct_sectors": PHASE12_MIN_DISTINCT_SECTORS,
        "maximum_products": PHASE12_MAX_PRODUCTS,
        "minimum_cadences": PHASE12_MIN_CADENCES,
        "minimum_baseline_days": PHASE12_MIN_BASELINE_DAYS,
        "maximum_median_cadence_days": PHASE12_MAX_MEDIAN_CADENCE_DAYS,
        "decisions": decisions,
        "selected_target_ids_in_pool_order": [
            item.target.target_id for item in selected
        ],
        "batch_plan": batch_plan,
    }
    selection_lock = {
        **selection_payload,
        "selection_lock_sha256": canonical_json_sha256(selection_payload),
    }

    lock_targets = [
        {
            "target_id": item.target.target_id,
            "query": item.target.query,
            "intended_role": item.target.stratum,
            "sector_label": sector_label(item.lightcurve),
            "campaign_input_combined_sha256": campaign_input_combined_sha256(
                item.lightcurve
            ),
            "query_provenance_sha256": provenance_sha(
                item.lightcurve, "query_provenance_sha256"
            ),
            "product_provenance_sha256": provenance_sha(
                item.lightcurve, "product_provenance_sha256"
            ),
        }
        for item in selected
    ]
    lock_targets.sort(
        key=lambda row: (
            str(row["target_id"]),
            str(row["campaign_input_combined_sha256"]),
        )
    )
    selected_ids = {item.target.target_id for item in selected}
    exclusions = [
        {
            "target_id": str(row["target_id"]),
            "query": str(row["query"]),
            "reason": str(row["reason"]),
        }
        for row in decisions
        if row["target_id"] not in selected_ids
    ]
    exclusions.sort(key=lambda row: row["target_id"])
    campaign_payload = {
        "schema": PHASE09_CAMPAIGN_LOCK_SCHEMA,
        "source_commit": source_commit,
        "frozen_at_utc": frozen_at_utc,
        "manifest_sha256": selection_lock["selection_lock_sha256"],
        "eligible_target_rule": PHASE09_ELIGIBLE_TARGET_RULE,
        "excluded_targets": exclusions,
        "search_duration_family_days": list(PHASE09_SEARCH_DURATION_FAMILY_DAYS),
        "flatten_window_days": PHASE09_FLATTEN_WINDOW_DAYS,
        "minimum_search_snr": PHASE09_MINIMUM_SEARCH_SNR,
        "maximum_machine_events_per_direction": PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION,
        "surrogate_method": GAP_AWARE_METHOD,
        "surrogate_seeds": list(PHASE09_SURROGATE_SEEDS),
        "surrogate_block_days": PHASE09_SURROGATE_BLOCK_DAYS,
        "surrogate_gap_factor": DEFAULT_GAP_FACTOR,
        "targets": lock_targets,
    }
    campaign_lock = {
        **campaign_payload,
        "campaign_lock_sha256": canonical_json_sha256(campaign_payload),
    }
    return Phase12SelectionResult(
        selection_lock=selection_lock,
        campaign_lock=campaign_lock,
        selected=tuple(selected),
        nasa_snapshot=nasa_snapshot,
    )
