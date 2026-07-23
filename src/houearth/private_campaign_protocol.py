from __future__ import annotations

import csv
import hashlib
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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
from .provenance import canonical_json_sha256
from .surrogates import DEFAULT_GAP_FACTOR, GAP_AWARE_METHOD


PHASE10_PRIVATE_RECEIPT_SCHEMA = "houearth-private-real-campaign-receipt-v0.10.0"
PHASE10_PRIVATE_MANIFEST_SCHEMA = "houearth-private-evidence-manifest-v0.10.0"
PHASE10_REQUIRED_TARGET_IDS = ("hd-10700", "hd-20794", "hd-69830")
PHASE10_PRIVATE_GUARD_ENV = "HOU_PRIVATE_EVIDENCE_SINK"
PHASE10_VISIBILITY_ENV = "HOU_PRIVATE_REPOSITORY_VISIBILITY"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class PrivateCampaignError(RuntimeError):
    """Raised when a real blind campaign cannot preserve its frozen protocol."""


@dataclass(frozen=True)
class PrivateCampaignTarget:
    target_id: str
    query: str
    author: str | None
    sectors: tuple[int, ...]
    max_products: int
    intended_role: str
    surrogate_policy: str
    notes: str

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "sectors": list(self.sectors)}


Downloader = Callable[..., LightCurve]


def utc_now_seconds() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_utc(value: str) -> None:
    if _UTC.fullmatch(value) is None:
        raise ValueError("frozen_at_utc must use YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("frozen_at_utc is not a valid UTC timestamp") from exc


def _parse_sectors(value: str) -> tuple[int, ...]:
    text = value.strip()
    if not text:
        return ()
    values = [int(token.strip()) for token in re.split(r"[;,]", text) if token.strip()]
    if any(value < 1 for value in values):
        raise ValueError("TESS sectors must be positive integers")
    result = tuple(sorted(set(values)))
    if len(result) != len(values):
        raise ValueError("TESS sector list contains duplicates")
    return result


def load_phase10_manifest(
    path: str | Path,
) -> tuple[list[PrivateCampaignTarget], list[dict[str, str]], str]:
    """Load the frozen six-target manifest and select exactly three null targets."""
    path = Path(path)
    raw = path.read_bytes()
    file_sha256 = hashlib.sha256(raw).hexdigest()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "target_id",
            "query",
            "author",
            "sectors",
            "max_products",
            "intended_role",
            "surrogate_policy",
            "notes",
        }
        if reader.fieldnames is None or set(reader.fieldnames) != required:
            raise ValueError("Phase 0.10 manifest must use the exact frozen columns")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if not rows:
        raise ValueError("Phase 0.10 manifest is empty")
    ids = [row["target_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Phase 0.10 manifest contains duplicate target IDs")

    eligible: list[PrivateCampaignTarget] = []
    excluded: list[dict[str, str]] = []
    for row in rows:
        if not row["target_id"] or not row["query"] or not row["intended_role"]:
            raise ValueError("Phase 0.10 manifest contains an incomplete target identity")
        try:
            max_products = int(row["max_products"])
        except ValueError as exc:
            raise ValueError("max_products must be an exact positive integer") from exc
        if max_products < 1:
            raise ValueError("max_products must be positive")
        if row["surrogate_policy"] == "unmasked-null":
            eligible.append(
                PrivateCampaignTarget(
                    target_id=row["target_id"],
                    query=row["query"],
                    author=row["author"] or None,
                    sectors=_parse_sectors(row["sectors"]),
                    max_products=max_products,
                    intended_role=row["intended_role"],
                    surrogate_policy=row["surrogate_policy"],
                    notes=row["notes"],
                )
            )
        else:
            excluded.append(
                {
                    "target_id": row["target_id"],
                    "query": row["query"],
                    "reason": row["notes"] or row["surrogate_policy"],
                }
            )
    eligible.sort(key=lambda item: item.target_id)
    excluded.sort(key=lambda item: item["target_id"])
    if tuple(item.target_id for item in eligible) != PHASE10_REQUIRED_TARGET_IDS:
        raise ValueError("Phase 0.10 requires exactly the three frozen null targets")
    if len(excluded) != len(rows) - len(eligible):
        raise ValueError("Phase 0.10 exclusion accounting is inconsistent")
    return eligible, excluded, file_sha256


def require_private_evidence_sink(
    output_directory: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Reject a real run unless the caller explicitly attests a private sink."""
    env = os.environ if environ is None else environ
    if env.get(PHASE10_PRIVATE_GUARD_ENV) != "1":
        raise PrivateCampaignError(
            f"{PHASE10_PRIVATE_GUARD_ENV}=1 is required for a real Phase 0.10 run"
        )
    if env.get("GITHUB_ACTIONS") == "true" and env.get(PHASE10_VISIBILITY_ENV) != "private":
        raise PrivateCampaignError(
            "GitHub Actions execution requires HOU_PRIVATE_REPOSITORY_VISIBILITY=private"
        )
    output = Path(output_directory).expanduser().resolve()
    if output == Path.cwd().resolve():
        raise PrivateCampaignError("private evidence sink cannot be the repository root")
    if output.exists() and any(output.iterdir()):
        raise PrivateCampaignError("private evidence sink must be absent or empty")
    return output


def _sector_request(target: PrivateCampaignTarget) -> int | list[int] | None:
    if not target.sectors:
        return None
    return target.sectors[0] if len(target.sectors) == 1 else list(target.sectors)


def sector_label(lightcurve: LightCurve) -> str:
    sectors = lightcurve.metadata.get("sectors")
    if not isinstance(sectors, (list, tuple)) or not sectors:
        raise PrivateCampaignError("downloaded light curve is missing sector provenance")
    values = tuple(sorted({int(value) for value in sectors}))
    if not values or any(value < 1 for value in values):
        raise PrivateCampaignError("downloaded light curve has invalid sector provenance")
    return ";".join(str(value) for value in values)


def provenance_sha(lightcurve: LightCurve, field: str) -> str:
    value = lightcurve.metadata.get(field)
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PrivateCampaignError(f"downloaded light curve is missing valid {field}")
    return value


def acquire_and_lock_inputs(
    targets: Sequence[PrivateCampaignTarget],
    *,
    excluded_targets: Sequence[Mapping[str, str]],
    manifest_sha256: str,
    source_commit: str,
    frozen_at_utc: str,
    downloader: Downloader = download_tess_lightcurve,
) -> tuple[dict[str, object], list[tuple[PrivateCampaignTarget, LightCurve]]]:
    """Download and fingerprint every target before any search is allowed."""
    if not isinstance(source_commit, str) or _SHA40.fullmatch(source_commit) is None:
        raise ValueError("source_commit must be a lowercase 40-character Git SHA")
    validate_utc(frozen_at_utc)
    if _SHA256.fullmatch(manifest_sha256) is None:
        raise ValueError("manifest_sha256 must be a lowercase SHA-256")
    if tuple(item.target_id for item in targets) != PHASE10_REQUIRED_TARGET_IDS:
        raise ValueError("Phase 0.10 target order or identity is not frozen")

    acquired: list[tuple[PrivateCampaignTarget, LightCurve]] = []
    failures: list[str] = []
    for target in targets:
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
            if _SHA256.fullmatch(campaign_hash) is None:
                raise PrivateCampaignError("campaign input hash is invalid")
            acquired.append((target, lightcurve))
        except Exception as exc:
            failures.append(f"{target.target_id}: {type(exc).__name__}: {exc}")
    if failures:
        raise PrivateCampaignError(
            "all-or-nothing acquisition failed; search was not started: "
            + " | ".join(failures)
        )
    if len(acquired) != len(targets):
        raise PrivateCampaignError("all-or-nothing acquisition count is inconsistent")

    lock_targets = [
        {
            "target_id": target.target_id,
            "query": target.query,
            "intended_role": target.intended_role,
            "sector_label": sector_label(lightcurve),
            "campaign_input_combined_sha256": campaign_input_combined_sha256(lightcurve),
            "query_provenance_sha256": provenance_sha(
                lightcurve, "query_provenance_sha256"
            ),
            "product_provenance_sha256": provenance_sha(
                lightcurve, "product_provenance_sha256"
            ),
        }
        for target, lightcurve in acquired
    ]
    lock_targets.sort(
        key=lambda row: (
            str(row["target_id"]),
            str(row["campaign_input_combined_sha256"]),
        )
    )
    exclusions = [
        {
            "target_id": str(row["target_id"]),
            "query": str(row["query"]),
            "reason": str(row["reason"]),
        }
        for row in excluded_targets
    ]
    exclusions.sort(key=lambda row: row["target_id"])
    payload = {
        "schema": PHASE09_CAMPAIGN_LOCK_SCHEMA,
        "source_commit": source_commit,
        "frozen_at_utc": frozen_at_utc,
        "manifest_sha256": manifest_sha256,
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
    return {**payload, "campaign_lock_sha256": canonical_json_sha256(payload)}, acquired
