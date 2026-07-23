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

PHASE11_POOL_SCHEMA = "houearth-expanded-target-pool-v0.11.0"
PHASE11_SELECTION_LOCK_SCHEMA = "houearth-expanded-selection-lock-v0.11.0"
PHASE11_POOL_SOURCE = "predeclared-bright-nearby-nontransit-pool-v1"
PHASE11_STRATA = ("solar-analog", "rv-host", "harder-control")
PHASE11_QUOTA_PER_STRATUM = 4
PHASE11_POOL_PER_STRATUM = 6
PHASE11_SELECTED_TARGETS = len(PHASE11_STRATA) * PHASE11_QUOTA_PER_STRATUM
PHASE11_MIN_CADENCES = 500
PHASE11_MIN_BASELINE_DAYS = 10.0
PHASE11_MAX_MEDIAN_CADENCE_DAYS = 0.1
PHASE11_NASA_TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
PHASE11_NASA_QUERY = (
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
class Phase11PoolTarget:
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
        return {**asdict(self), "sectors": list(self.sectors), "archive_aliases": list(self.archive_aliases)}


@dataclass(frozen=True)
class Phase11SelectionResult:
    selection_lock: dict[str, object]
    campaign_lock: dict[str, object]
    selected: tuple[tuple[Phase11PoolTarget, LightCurve], ...]
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


def load_phase11_pool(path: str | Path) -> tuple[tuple[Phase11PoolTarget, ...], str]:
    path = Path(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != _POOL_COLUMNS:
            raise ValueError("Phase 0.11 pool must use the exact frozen columns and order")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    expected_rows = len(PHASE11_STRATA) * PHASE11_POOL_PER_STRATUM
    if len(rows) != expected_rows:
        raise ValueError(f"Phase 0.11 requires exactly {expected_rows} ranked pool rows")
    if len({row["target_id"] for row in rows}) != len(rows):
        raise ValueError("Phase 0.11 pool contains duplicate target IDs")
    if len({row["query"] for row in rows}) != len(rows):
        raise ValueError("Phase 0.11 pool contains duplicate target queries")
    parsed: list[Phase11PoolTarget] = []
    for row in rows:
        if row["stratum"] not in PHASE11_STRATA:
            raise ValueError("Phase 0.11 pool contains an unknown stratum")
        if row["selection_source"] != PHASE11_POOL_SOURCE:
            raise ValueError("Phase 0.11 selection source is not frozen")
        if row["surrogate_policy"] != "unmasked-null":
            raise ValueError("Phase 0.11 pool must use unmasked-null for every row")
        try:
            max_products = int(row["max_products"])
            rank = int(row["pool_rank"])
        except ValueError as exc:
            raise ValueError("max_products and pool_rank must be exact integers") from exc
        if max_products < 1 or rank < 1:
            raise ValueError("max_products and pool_rank must be positive")
        parsed.append(Phase11PoolTarget(
            target_id=row["target_id"], query=row["query"], author=row["author"] or None,
            sectors=_parse_sectors(row["sectors"]), max_products=max_products,
            stratum=row["stratum"], pool_rank=rank, selection_source=row["selection_source"],
            surrogate_policy=row["surrogate_policy"], archive_aliases=_parse_aliases(row["archive_aliases"]),
            notes=row["notes"],
        ))
    stratum_index = {name: index for index, name in enumerate(PHASE11_STRATA)}
    parsed.sort(key=lambda item: (stratum_index[item.stratum], item.pool_rank, item.target_id))
    for stratum in PHASE11_STRATA:
        ranks = [item.pool_rank for item in parsed if item.stratum == stratum]
        if ranks != list(range(1, PHASE11_POOL_PER_STRATUM + 1)):
            raise ValueError(f"Phase 0.11 stratum {stratum} must use ranks 1..6 exactly")
    return tuple(parsed), digest


def fetch_nasa_ps_snapshot(timeout: float = 60.0) -> bytes:
    query = urllib.parse.urlencode({"query": PHASE11_NASA_QUERY, "format": "csv"})
    request = urllib.request.Request(
        f"{PHASE11_NASA_TAP_URL}?{query}",
        headers={"User-Agent": "HOU-EARTH/0.11 catalog-audit"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = response.read()
    if not payload:
        raise PrivateCampaignError("NASA Exoplanet Archive returned an empty snapshot")
    return payload


def _norm_alias(value: str) -> str:
    return " ".join(value.upper().replace("−", "-").split())


def audit_nasa_transit_snapshot(pool: Sequence[Phase11PoolTarget], snapshot: bytes) -> dict[str, object]:
    snapshot_sha = hashlib.sha256(snapshot).hexdigest()
    try:
        text = snapshot.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PrivateCampaignError("NASA snapshot is not valid UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text))
    required = {"hostname", "hd_name", "hip_name", "tic_id", "pl_name", "tran_flag", "default_flag", "rowupdate"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise PrivateCampaignError("NASA snapshot columns are missing or inconsistent")
    archive_rows: list[dict[str, str]] = []
    alias_index: dict[str, list[dict[str, str]]] = {}
    for raw in reader:
        row = {key: (raw.get(key) or "").strip() for key in required}
        if row["default_flag"] not in {"1", "1.0"}:
            continue
        archive_rows.append(row)
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
        audits.append({
            "target_id": target.target_id, "query": target.query,
            "archive_aliases": list(target.archive_aliases),
            "matched_confirmed_planets": len(rows), "matched_transiting_planets": len(transiting),
            "archive_status": "blocked-confirmed-transiting-host" if transiting else "eligible-no-confirmed-transiting-planet",
        })
    audits.sort(key=lambda row: str(row["target_id"]))
    payload = {
        "schema": "houearth-nasa-transit-audit-v0.11.0", "tap_url": PHASE11_NASA_TAP_URL,
        "adql": PHASE11_NASA_QUERY, "snapshot_sha256": snapshot_sha,
        "snapshot_rows": len(archive_rows), "targets": audits,
        "blocked_target_ids": sorted(blocked_ids),
    }
    return {**payload, "audit_sha256": canonical_json_sha256(payload)}


def _sector_request(target: Phase11PoolTarget) -> int | list[int] | None:
    if not target.sectors:
        return None
    return target.sectors[0] if len(target.sectors) == 1 else list(target.sectors)


def _quality_reason(lightcurve: LightCurve) -> str | None:
    if len(lightcurve.time) < PHASE11_MIN_CADENCES:
        return f"cadences<{PHASE11_MIN_CADENCES}"
    if lightcurve.baseline < PHASE11_MIN_BASELINE_DAYS:
        return f"baseline_days<{PHASE11_MIN_BASELINE_DAYS}"
    if lightcurve.cadence > PHASE11_MAX_MEDIAN_CADENCE_DAYS:
        return f"median_cadence_days>{PHASE11_MAX_MEDIAN_CADENCE_DAYS}"
    return None


def select_and_lock_phase11_inputs(
    pool: Sequence[Phase11PoolTarget], *, pool_sha256: str,
    nasa_audit: Mapping[str, object], nasa_snapshot: bytes,
    source_commit: str, frozen_at_utc: str,
    downloader: Downloader = download_tess_lightcurve,
) -> Phase11SelectionResult:
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
    if audit_hash != canonical_json_sha256({key: value for key, value in nasa_audit.items() if key != "audit_sha256"}):
        raise ValueError("NASA audit SHA-256 does not match its payload")
    blocked = set(nasa_audit.get("blocked_target_ids", ()))
    selected: list[tuple[Phase11PoolTarget, LightCurve]] = []
    decisions: list[dict[str, object]] = []
    selected_by_stratum = {stratum: 0 for stratum in PHASE11_STRATA}
    for target in pool:
        if target.target_id in blocked:
            decisions.append({"target_id": target.target_id, "query": target.query, "stratum": target.stratum,
                              "pool_rank": target.pool_rank, "decision": "excluded", "reason": "nasa-confirmed-transiting-host"})
            continue
        if selected_by_stratum[target.stratum] >= PHASE11_QUOTA_PER_STRATUM:
            decisions.append({"target_id": target.target_id, "query": target.query, "stratum": target.stratum,
                              "pool_rank": target.pool_rank, "decision": "not-needed", "reason": "stratum-quota-already-filled"})
            continue
        try:
            lightcurve = downloader(target.query, author=target.author, sector=_sector_request(target), max_products=target.max_products)
            campaign_hash = campaign_input_combined_sha256(lightcurve)
            provenance_sha(lightcurve, "query_provenance_sha256")
            provenance_sha(lightcurve, "product_provenance_sha256")
            sector_label(lightcurve)
            reason = _quality_reason(lightcurve)
            if reason is not None:
                raise PrivateCampaignError(reason)
        except Exception as exc:
            decisions.append({"target_id": target.target_id, "query": target.query, "stratum": target.stratum,
                              "pool_rank": target.pool_rank, "decision": "excluded",
                              "reason": f"acquisition-or-quality:{type(exc).__name__}:{exc}"})
            continue
        selected.append((target, lightcurve))
        selected_by_stratum[target.stratum] += 1
        decisions.append({
            "target_id": target.target_id, "query": target.query, "stratum": target.stratum,
            "pool_rank": target.pool_rank, "decision": "selected",
            "reason": "first-ranked-eligible-target-within-stratum",
            "campaign_input_combined_sha256": campaign_hash, "sector_label": sector_label(lightcurve),
            "cadences": len(lightcurve.time), "baseline_days": lightcurve.baseline,
            "median_cadence_days": lightcurve.cadence,
        })
    if any(value != PHASE11_QUOTA_PER_STRATUM for value in selected_by_stratum.values()):
        counts = ", ".join(f"{key}={value}" for key, value in selected_by_stratum.items())
        raise PrivateCampaignError("Phase 0.11 ranked pool could not fill the frozen stratum quotas; " + counts)
    if len(selected) != PHASE11_SELECTED_TARGETS:
        raise PrivateCampaignError("Phase 0.11 selected-target count is inconsistent")
    selection_payload = {
        "schema": PHASE11_SELECTION_LOCK_SCHEMA, "source_commit": source_commit,
        "frozen_at_utc": frozen_at_utc, "pool_schema": PHASE11_POOL_SCHEMA,
        "pool_sha256": pool_sha256, "pool_source": PHASE11_POOL_SOURCE,
        "nasa_snapshot_sha256": nasa_audit["snapshot_sha256"], "nasa_audit_sha256": audit_hash,
        "strata": list(PHASE11_STRATA), "quota_per_stratum": PHASE11_QUOTA_PER_STRATUM,
        "minimum_cadences": PHASE11_MIN_CADENCES, "minimum_baseline_days": PHASE11_MIN_BASELINE_DAYS,
        "maximum_median_cadence_days": PHASE11_MAX_MEDIAN_CADENCE_DAYS,
        "decisions": decisions,
        "selected_target_ids_in_pool_order": [target.target_id for target, _ in selected],
    }
    selection_lock = {**selection_payload, "selection_lock_sha256": canonical_json_sha256(selection_payload)}
    lock_targets = [{
        "target_id": target.target_id, "query": target.query, "intended_role": target.stratum,
        "sector_label": sector_label(lightcurve),
        "campaign_input_combined_sha256": campaign_input_combined_sha256(lightcurve),
        "query_provenance_sha256": provenance_sha(lightcurve, "query_provenance_sha256"),
        "product_provenance_sha256": provenance_sha(lightcurve, "product_provenance_sha256"),
    } for target, lightcurve in selected]
    lock_targets.sort(key=lambda row: (str(row["target_id"]), str(row["campaign_input_combined_sha256"])))
    selected_ids = {target.target_id for target, _ in selected}
    exclusions = [{"target_id": str(row["target_id"]), "query": str(row["query"]), "reason": str(row["reason"])}
                  for row in decisions if row["target_id"] not in selected_ids]
    exclusions.sort(key=lambda row: row["target_id"])
    campaign_payload = {
        "schema": PHASE09_CAMPAIGN_LOCK_SCHEMA, "source_commit": source_commit,
        "frozen_at_utc": frozen_at_utc, "manifest_sha256": selection_lock["selection_lock_sha256"],
        "eligible_target_rule": PHASE09_ELIGIBLE_TARGET_RULE, "excluded_targets": exclusions,
        "search_duration_family_days": list(PHASE09_SEARCH_DURATION_FAMILY_DAYS),
        "flatten_window_days": PHASE09_FLATTEN_WINDOW_DAYS,
        "minimum_search_snr": PHASE09_MINIMUM_SEARCH_SNR,
        "maximum_machine_events_per_direction": PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION,
        "surrogate_method": GAP_AWARE_METHOD, "surrogate_seeds": list(PHASE09_SURROGATE_SEEDS),
        "surrogate_block_days": PHASE09_SURROGATE_BLOCK_DAYS,
        "surrogate_gap_factor": DEFAULT_GAP_FACTOR, "targets": lock_targets,
    }
    campaign_lock = {**campaign_payload, "campaign_lock_sha256": canonical_json_sha256(campaign_payload)}
    return Phase11SelectionResult(selection_lock=selection_lock, campaign_lock=campaign_lock,
                                  selected=tuple(selected), nasa_snapshot=nasa_snapshot)
