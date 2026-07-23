from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .candidate_campaign import PHASE09_CAMPAIGN_LOCK_SCHEMA
from .core import LightCurve
from .phase12_protocol import (
    PHASE12_BATCH_COUNT,
    PHASE12_BATCH_SIZE,
    PHASE12_PER_STRATUM_PER_BATCH,
    PHASE12_QUOTA_PER_STRATUM,
    PHASE12_SELECTED_TARGETS,
    PHASE12_SELECTION_LOCK_SCHEMA,
    PHASE12_STRATA,
)
from .private_campaign_protocol import PrivateCampaignError, validate_utc
from .provenance import canonical_json_sha256, lightcurve_array_hashes

PHASE12_SELECTION_PRIVATE_MANIFEST_SCHEMA = (
    "houearth-phase12-selection-private-manifest-v1"
)
PHASE12_LOCKED_INPUT_SET_SCHEMA = "houearth-phase12-locked-input-set-v0.12.1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_CSV_HEADER = "time_days,flux,flux_err"
_SELECTION_FIELDS = {
    "schema",
    "source_commit",
    "frozen_at_utc",
    "pool_schema",
    "pool_sha256",
    "pool_source",
    "nasa_snapshot_sha256",
    "nasa_audit_sha256",
    "strata",
    "pool_per_stratum",
    "quota_per_stratum",
    "selected_targets",
    "batch_count",
    "batch_size",
    "per_stratum_per_batch",
    "minimum_products",
    "minimum_distinct_sectors",
    "maximum_products",
    "minimum_cadences",
    "minimum_baseline_days",
    "maximum_median_cadence_days",
    "decisions",
    "selected_target_ids_in_pool_order",
    "batch_plan",
    "selection_lock_sha256",
}
_CAMPAIGN_LOCK_FIELDS = {
    "schema",
    "source_commit",
    "frozen_at_utc",
    "manifest_sha256",
    "eligible_target_rule",
    "excluded_targets",
    "search_duration_family_days",
    "flatten_window_days",
    "minimum_search_snr",
    "maximum_machine_events_per_direction",
    "surrogate_method",
    "surrogate_seeds",
    "surrogate_block_days",
    "surrogate_gap_factor",
    "targets",
    "campaign_lock_sha256",
}
_LOCK_TARGET_FIELDS = {
    "target_id",
    "query",
    "intended_role",
    "sector_label",
    "campaign_input_combined_sha256",
    "query_provenance_sha256",
    "product_provenance_sha256",
}


@dataclass(frozen=True)
class Phase12LockedInput:
    target_id: str
    query: str
    intended_role: str
    sector_label: str
    batch_id: int
    stratum_position: int
    products: int
    distinct_sectors: int
    csv_relative_path: str
    csv_sha256: str
    lightcurve: LightCurve


@dataclass(frozen=True)
class Phase12LockedSelection:
    root: str
    selection_lock: dict[str, object]
    selection_campaign_lock: dict[str, object]
    public_selection_receipt: dict[str, object]
    private_manifest: dict[str, object]
    inputs: tuple[Phase12LockedInput, ...]
    locked_input_set_sha256: str


def _load_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrivateCampaignError(f"{label} is not readable JSON") from exc
    if not isinstance(payload, dict):
        raise PrivateCampaignError(f"{label} must be a JSON object")
    return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _exact_fields(payload: Mapping[object, object], expected: set[str], label: str) -> None:
    keys = {key for key in payload if isinstance(key, str)}
    if keys != expected or any(not isinstance(key, str) for key in payload):
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        raise PrivateCampaignError(
            f"{label} fields are not closed; missing={missing}, extra={extra}"
        )


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _safe_relative(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise PrivateCampaignError(f"{label} path is invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise PrivateCampaignError(f"{label} path is unsafe")
    return path


def _verify_private_manifest(root: Path) -> dict[str, object]:
    manifest_path = root / "PRIVATE_SELECTION_MANIFEST.json"
    manifest = _load_object(manifest_path, "private selection manifest")
    if set(manifest) != {"schema", "source_commit", "files", "manifest_sha256"}:
        raise PrivateCampaignError("private selection manifest fields are not closed")
    if manifest.get("schema") != PHASE12_SELECTION_PRIVATE_MANIFEST_SCHEMA:
        raise PrivateCampaignError("private selection manifest schema is inconsistent")
    if not isinstance(manifest.get("source_commit"), str) or _SHA40.fullmatch(
        str(manifest.get("source_commit"))
    ) is None:
        raise PrivateCampaignError("private selection manifest source commit is invalid")
    recorded_hash = manifest.get("manifest_sha256")
    expected_hash = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    if not _valid_sha(recorded_hash) or recorded_hash != expected_hash:
        raise PrivateCampaignError("private selection manifest SHA-256 is inconsistent")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise PrivateCampaignError("private selection manifest file map is missing")

    listed: set[str] = set()
    for relative_value, identity in files.items():
        relative = _safe_relative(relative_value, "private manifest")
        relative_text = relative.as_posix()
        if relative_text in listed:
            raise PrivateCampaignError("private selection manifest repeats a path")
        listed.add(relative_text)
        if not isinstance(identity, dict) or set(identity) != {"size_bytes", "sha256"}:
            raise PrivateCampaignError(
                f"private selection manifest identity is invalid: {relative_text}"
            )
        size = identity.get("size_bytes")
        digest = identity.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise PrivateCampaignError(
                f"private selection manifest size is invalid: {relative_text}"
            )
        if not _valid_sha(digest):
            raise PrivateCampaignError(
                f"private selection manifest hash is invalid: {relative_text}"
            )
        path = root / relative
        if not path.is_file():
            raise PrivateCampaignError(
                f"private selection manifest file is missing: {relative_text}"
            )
        if path.stat().st_size != size:
            raise PrivateCampaignError(
                f"private selection manifest size mismatch: {relative_text}"
            )
        if _file_sha256(path) != digest:
            raise PrivateCampaignError(
                f"private selection manifest SHA-256 mismatch: {relative_text}"
            )

    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "PRIVATE_SELECTION_MANIFEST.json"
    }
    if actual != listed:
        missing = sorted(listed - actual)
        extra = sorted(actual - listed)
        raise PrivateCampaignError(
            f"private selection directory differs from manifest; missing={missing}, extra={extra}"
        )
    return manifest


def _verify_hashed_object(
    payload: dict[str, object],
    *,
    hash_field: str,
    expected_fields: set[str],
    label: str,
) -> str:
    _exact_fields(payload, expected_fields, label)
    recorded = payload.get(hash_field)
    expected = canonical_json_sha256(
        {key: value for key, value in payload.items() if key != hash_field}
    )
    if not _valid_sha(recorded) or recorded != expected:
        raise PrivateCampaignError(f"{label} {hash_field} is inconsistent")
    return str(recorded)


def _parse_sector_label(value: object) -> tuple[int, ...]:
    if not isinstance(value, str) or not value:
        raise PrivateCampaignError("locked input sector label is invalid")
    try:
        sectors = tuple(int(token) for token in value.split(";"))
    except ValueError as exc:
        raise PrivateCampaignError("locked input sector label is invalid") from exc
    if not sectors or any(item < 1 for item in sectors):
        raise PrivateCampaignError("locked input sector label is invalid")
    if sectors != tuple(sorted(set(sectors))):
        raise PrivateCampaignError("locked input sector label is not canonical")
    return sectors


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PrivateCampaignError(f"{label} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise PrivateCampaignError(f"{label} must be finite")
    return parsed


def _read_locked_csv(
    path: Path,
    *,
    query: str,
    decision: Mapping[str, object],
    lock_target: Mapping[str, object],
    selection_source_commit: str,
    selection_lock_sha256: str,
) -> tuple[LightCurve, str]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            header = handle.readline().rstrip("\r\n")
    except (OSError, UnicodeDecodeError) as exc:
        raise PrivateCampaignError("locked input CSV is not readable UTF-8") from exc
    if header != _CSV_HEADER:
        raise PrivateCampaignError("locked input CSV header is not exact")
    try:
        data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    except (OSError, ValueError) as exc:
        raise PrivateCampaignError("locked input CSV numeric body is invalid") from exc
    if data.ndim != 2 or data.shape[1] != 3 or data.shape[0] < 20:
        raise PrivateCampaignError("locked input CSV must contain exactly three columns")
    time = np.asarray(data[:, 0], dtype=float)
    flux = np.asarray(data[:, 1], dtype=float)
    raw_error = np.asarray(data[:, 2], dtype=float)
    if not np.all(np.isfinite(time)) or not np.all(np.isfinite(flux)):
        raise PrivateCampaignError("locked input CSV time/flux contains non-finite values")
    if np.any(np.diff(time) < 0):
        raise PrivateCampaignError("locked input CSV time is not sorted")
    if np.all(np.isnan(raw_error)):
        flux_error: np.ndarray | None = None
    elif np.all(np.isfinite(raw_error) & (raw_error > 0)):
        flux_error = raw_error
    else:
        raise PrivateCampaignError("locked input CSV flux_err is partially invalid")

    array_hashes = lightcurve_array_hashes(time, flux, flux_error)
    expected_hashes = {
        decision.get("campaign_input_combined_sha256"),
        lock_target.get("campaign_input_combined_sha256"),
    }
    if len(expected_hashes) != 1 or array_hashes["combined_sha256"] not in expected_hashes:
        raise PrivateCampaignError("locked input CSV arrays do not match the selection lock")
    sector_label = decision.get("sector_label")
    if sector_label != lock_target.get("sector_label"):
        raise PrivateCampaignError("locked input sector labels differ across locks")
    sectors = _parse_sector_label(sector_label)
    products = decision.get("products")
    distinct_sectors = decision.get("distinct_sectors")
    if isinstance(products, bool) or not isinstance(products, int) or products < 1:
        raise PrivateCampaignError("locked input product count is invalid")
    if (
        isinstance(distinct_sectors, bool)
        or not isinstance(distinct_sectors, int)
        or distinct_sectors != len(sectors)
    ):
        raise PrivateCampaignError("locked input distinct-sector count is inconsistent")
    query_hash = lock_target.get("query_provenance_sha256")
    product_hash = lock_target.get("product_provenance_sha256")
    if not _valid_sha(query_hash) or not _valid_sha(product_hash):
        raise PrivateCampaignError("locked input provenance hashes are invalid")

    csv_sha = _file_sha256(path)
    lightcurve = LightCurve(
        time,
        flux,
        flux_error,
        target=query,
        metadata={
            "source": "HOU-EARTH Phase 0.12 frozen selection lock",
            "sectors": list(sectors),
            "products": products,
            "campaign_input_array_hashes": array_hashes,
            "query_provenance_sha256": query_hash,
            "product_provenance_sha256": product_hash,
            "selection_source_commit": selection_source_commit,
            "selection_lock_sha256": selection_lock_sha256,
            "selection_input_csv_sha256": csv_sha,
            "locked_input_resume": True,
        },
    )
    if not np.array_equal(lightcurve.time, time) or not np.array_equal(
        lightcurve.flux, flux
    ):
        raise PrivateCampaignError("LightCurve construction changed locked input arrays")
    if flux_error is None:
        if lightcurve.flux_err is not None:
            raise PrivateCampaignError("LightCurve construction changed locked flux errors")
    elif lightcurve.flux_err is None or not np.array_equal(
        lightcurve.flux_err, flux_error
    ):
        raise PrivateCampaignError("LightCurve construction changed locked flux errors")

    cadences = decision.get("cadences")
    if isinstance(cadences, bool) or not isinstance(cadences, int) or cadences != len(time):
        raise PrivateCampaignError("locked input cadence count differs from selection lock")
    baseline = _finite_number(decision.get("baseline_days"), "locked input baseline")
    cadence = _finite_number(
        decision.get("median_cadence_days"), "locked input median cadence"
    )
    if not math.isclose(lightcurve.baseline, baseline, rel_tol=0.0, abs_tol=1e-10):
        raise PrivateCampaignError("locked input baseline differs from selection lock")
    if not math.isclose(lightcurve.cadence, cadence, rel_tol=0.0, abs_tol=1e-12):
        raise PrivateCampaignError("locked input cadence differs from selection lock")
    return lightcurve, csv_sha


def load_phase12_locked_selection(
    selection_directory: str | Path,
) -> Phase12LockedSelection:
    root = Path(selection_directory).expanduser().resolve()
    if not root.is_dir():
        raise PrivateCampaignError("Phase 0.12 locked selection directory is missing")
    private_manifest = _verify_private_manifest(root)
    selection_lock = _load_object(root / "phase12_selection_lock.json", "selection lock")
    campaign_lock = _load_object(root / "campaign_lock.json", "selection campaign lock")
    public_receipt = _load_object(
        root / "PUBLIC_SELECTION_RECEIPT.json", "public selection receipt"
    )

    selection_hash = _verify_hashed_object(
        selection_lock,
        hash_field="selection_lock_sha256",
        expected_fields=_SELECTION_FIELDS,
        label="selection lock",
    )
    campaign_hash = _verify_hashed_object(
        campaign_lock,
        hash_field="campaign_lock_sha256",
        expected_fields=_CAMPAIGN_LOCK_FIELDS,
        label="selection campaign lock",
    )
    if selection_lock.get("schema") != PHASE12_SELECTION_LOCK_SCHEMA:
        raise PrivateCampaignError("selection lock schema is inconsistent")
    if campaign_lock.get("schema") != PHASE09_CAMPAIGN_LOCK_SCHEMA:
        raise PrivateCampaignError("selection campaign lock schema is inconsistent")
    selection_source = selection_lock.get("source_commit")
    if not isinstance(selection_source, str) or _SHA40.fullmatch(selection_source) is None:
        raise PrivateCampaignError("selection lock source commit is invalid")
    if campaign_lock.get("source_commit") != selection_source:
        raise PrivateCampaignError("selection and campaign lock source commits differ")
    if private_manifest.get("source_commit") != selection_source:
        raise PrivateCampaignError("private manifest and selection source commits differ")
    if campaign_lock.get("manifest_sha256") != selection_hash:
        raise PrivateCampaignError("selection campaign lock is not bound to selection lock")
    if campaign_lock.get("frozen_at_utc") != selection_lock.get("frozen_at_utc"):
        raise PrivateCampaignError("selection and campaign lock timestamps differ")
    validate_utc(str(selection_lock.get("frozen_at_utc")))

    if selection_lock.get("selected_targets") != PHASE12_SELECTED_TARGETS:
        raise PrivateCampaignError("selection lock target quota is inconsistent")
    if selection_lock.get("quota_per_stratum") != PHASE12_QUOTA_PER_STRATUM:
        raise PrivateCampaignError("selection lock stratum quota is inconsistent")
    if selection_lock.get("batch_count") != PHASE12_BATCH_COUNT:
        raise PrivateCampaignError("selection lock batch count is inconsistent")
    if selection_lock.get("batch_size") != PHASE12_BATCH_SIZE:
        raise PrivateCampaignError("selection lock batch size is inconsistent")
    if selection_lock.get("per_stratum_per_batch") != PHASE12_PER_STRATUM_PER_BATCH:
        raise PrivateCampaignError("selection lock batch-stratum quota is inconsistent")
    if selection_lock.get("strata") != list(PHASE12_STRATA):
        raise PrivateCampaignError("selection lock strata are inconsistent")

    decisions_value = selection_lock.get("decisions")
    if not isinstance(decisions_value, list) or len(decisions_value) < PHASE12_SELECTED_TARGETS:
        raise PrivateCampaignError("selection lock decisions are malformed")
    selected_decisions: list[dict[str, object]] = []
    selected_map: dict[str, dict[str, object]] = {}
    for index, row in enumerate(decisions_value):
        if not isinstance(row, dict):
            raise PrivateCampaignError(f"selection decision {index} is not an object")
        if row.get("decision") != "selected":
            continue
        target_id = row.get("target_id")
        if not isinstance(target_id, str) or not target_id or target_id in selected_map:
            raise PrivateCampaignError("selection lock contains duplicate/invalid selected target")
        selected_map[target_id] = row
        selected_decisions.append(row)
    if len(selected_decisions) != PHASE12_SELECTED_TARGETS:
        raise PrivateCampaignError("selection lock does not contain exactly 64 selections")
    pool_order = selection_lock.get("selected_target_ids_in_pool_order")
    if pool_order != [row["target_id"] for row in selected_decisions]:
        raise PrivateCampaignError("selected target pool order is inconsistent")

    lock_targets_value = campaign_lock.get("targets")
    if not isinstance(lock_targets_value, list) or len(lock_targets_value) != PHASE12_SELECTED_TARGETS:
        raise PrivateCampaignError("selection campaign lock targets are malformed")
    lock_targets: dict[str, dict[str, object]] = {}
    canonical_keys: list[tuple[str, str]] = []
    for index, row in enumerate(lock_targets_value):
        if not isinstance(row, dict):
            raise PrivateCampaignError(f"selection campaign target {index} is not an object")
        _exact_fields(row, _LOCK_TARGET_FIELDS, f"selection campaign target {index}")
        target_id = row.get("target_id")
        query = row.get("query")
        role = row.get("intended_role")
        campaign_input_hash = row.get("campaign_input_combined_sha256")
        if not all(isinstance(value, str) and value for value in (target_id, query, role)):
            raise PrivateCampaignError("selection campaign target identity is invalid")
        if target_id in lock_targets or not _valid_sha(campaign_input_hash):
            raise PrivateCampaignError("selection campaign target is duplicate or unhashed")
        lock_targets[str(target_id)] = row
        canonical_keys.append((str(target_id), str(campaign_input_hash)))
    if canonical_keys != sorted(canonical_keys):
        raise PrivateCampaignError("selection campaign targets are not canonical")
    if set(lock_targets) != set(selected_map):
        raise PrivateCampaignError("selection decisions and campaign targets differ")

    batch_plan_value = selection_lock.get("batch_plan")
    if not isinstance(batch_plan_value, list) or len(batch_plan_value) != PHASE12_BATCH_COUNT:
        raise PrivateCampaignError("selection batch plan is malformed")
    planned_batch_by_target: dict[str, int] = {}
    expected_csv_paths: dict[str, str] = {}
    for expected_batch, row in enumerate(batch_plan_value, start=1):
        if not isinstance(row, dict) or set(row) != {"batch_id", "target_ids"}:
            raise PrivateCampaignError("selection batch-plan row is malformed")
        if row.get("batch_id") != expected_batch:
            raise PrivateCampaignError("selection batch IDs are not canonical")
        target_ids = row.get("target_ids")
        if not isinstance(target_ids, list) or len(target_ids) != PHASE12_BATCH_SIZE:
            raise PrivateCampaignError("selection batch target count is inconsistent")
        for target_id in target_ids:
            if (
                not isinstance(target_id, str)
                or target_id not in selected_map
                or target_id in planned_batch_by_target
            ):
                raise PrivateCampaignError("selection batch plan repeats/unknown target")
            planned_batch_by_target[target_id] = expected_batch
            expected_csv_paths[target_id] = (
                f"campaign_inputs/batch-{expected_batch:02d}/{target_id}.csv"
            )
    if set(planned_batch_by_target) != set(selected_map):
        raise PrivateCampaignError("selection batch plan does not cover every selected target")

    stratum_counts = {name: 0 for name in PHASE12_STRATA}
    batch_stratum_counts = {
        (batch, name): 0
        for batch in range(1, PHASE12_BATCH_COUNT + 1)
        for name in PHASE12_STRATA
    }
    for target_id, decision in selected_map.items():
        stratum = decision.get("stratum")
        batch_id = decision.get("batch_id")
        position = decision.get("stratum_selected_position")
        if stratum not in PHASE12_STRATA:
            raise PrivateCampaignError("selected target stratum is invalid")
        if batch_id != planned_batch_by_target[target_id]:
            raise PrivateCampaignError("selected target batch differs from batch plan")
        if isinstance(position, bool) or not isinstance(position, int) or not 1 <= position <= 16:
            raise PrivateCampaignError("selected target stratum position is invalid")
        expected_batch = ((position - 1) // PHASE12_PER_STRATUM_PER_BATCH) + 1
        if batch_id != expected_batch:
            raise PrivateCampaignError("selected target batch differs from frozen position rule")
        stratum_counts[str(stratum)] += 1
        batch_stratum_counts[(int(batch_id), str(stratum))] += 1
    if set(stratum_counts.values()) != {PHASE12_QUOTA_PER_STRATUM}:
        raise PrivateCampaignError("selection lock stratum counts are inconsistent")
    if set(batch_stratum_counts.values()) != {PHASE12_PER_STRATUM_PER_BATCH}:
        raise PrivateCampaignError("selection lock batch-stratum balance is inconsistent")

    actual_csv_paths = {
        path.relative_to(root).as_posix()
        for path in (root / "campaign_inputs").rglob("*")
        if path.is_file()
    }
    if actual_csv_paths != set(expected_csv_paths.values()):
        missing = sorted(set(expected_csv_paths.values()) - actual_csv_paths)
        extra = sorted(actual_csv_paths - set(expected_csv_paths.values()))
        raise PrivateCampaignError(
            f"locked input CSV set differs from batch plan; missing={missing}, extra={extra}"
        )

    ordered_inputs: list[Phase12LockedInput] = []
    for batch_id in range(1, PHASE12_BATCH_COUNT + 1):
        target_ids = batch_plan_value[batch_id - 1]["target_ids"]
        for target_id in target_ids:
            decision = selected_map[target_id]
            lock_target = lock_targets[target_id]
            if decision.get("query") != lock_target.get("query"):
                raise PrivateCampaignError("locked input query differs across locks")
            if decision.get("stratum") != lock_target.get("intended_role"):
                raise PrivateCampaignError("locked input stratum differs across locks")
            csv_relative_path = expected_csv_paths[target_id]
            lightcurve, csv_sha = _read_locked_csv(
                root / csv_relative_path,
                query=str(decision["query"]),
                decision=decision,
                lock_target=lock_target,
                selection_source_commit=selection_source,
                selection_lock_sha256=selection_hash,
            )
            ordered_inputs.append(
                Phase12LockedInput(
                    target_id=target_id,
                    query=str(decision["query"]),
                    intended_role=str(decision["stratum"]),
                    sector_label=str(decision["sector_label"]),
                    batch_id=batch_id,
                    stratum_position=int(decision["stratum_selected_position"]),
                    products=int(decision["products"]),
                    distinct_sectors=int(decision["distinct_sectors"]),
                    csv_relative_path=csv_relative_path,
                    csv_sha256=csv_sha,
                    lightcurve=lightcurve,
                )
            )
    if len(ordered_inputs) != PHASE12_SELECTED_TARGETS:
        raise PrivateCampaignError("locked input count is inconsistent")

    if public_receipt.get("source_commit") != selection_source:
        raise PrivateCampaignError("public selection receipt source commit is inconsistent")
    if public_receipt.get("selection_lock_sha256") != selection_hash:
        raise PrivateCampaignError("public selection receipt selection hash is inconsistent")
    if public_receipt.get("campaign_lock_sha256") != campaign_hash:
        raise PrivateCampaignError("public selection receipt campaign hash is inconsistent")
    if public_receipt.get("selected_targets") != PHASE12_SELECTED_TARGETS:
        raise PrivateCampaignError("public selection receipt target count is inconsistent")
    if public_receipt.get("search_started") is not False:
        raise PrivateCampaignError("locked selection receipt unexpectedly reports search")
    if public_receipt.get("surrogate_trials_executed") != 0:
        raise PrivateCampaignError("locked selection receipt unexpectedly reports surrogates")
    if public_receipt.get("candidate_details_disclosed") is not False:
        raise PrivateCampaignError("locked selection receipt disclosure flag is unsafe")

    input_identity = {
        "schema": PHASE12_LOCKED_INPUT_SET_SCHEMA,
        "selection_source_commit": selection_source,
        "selection_lock_sha256": selection_hash,
        "selection_campaign_lock_sha256": campaign_hash,
        "selection_private_manifest_sha256": private_manifest["manifest_sha256"],
        "inputs": [
            {
                "target_id": item.target_id,
                "batch_id": item.batch_id,
                "csv_relative_path": item.csv_relative_path,
                "csv_sha256": item.csv_sha256,
                "campaign_input_combined_sha256": item.lightcurve.metadata[
                    "campaign_input_array_hashes"
                ]["combined_sha256"],
            }
            for item in ordered_inputs
        ],
    }
    return Phase12LockedSelection(
        root=str(root),
        selection_lock=selection_lock,
        selection_campaign_lock=campaign_lock,
        public_selection_receipt=public_receipt,
        private_manifest=private_manifest,
        inputs=tuple(ordered_inputs),
        locked_input_set_sha256=canonical_json_sha256(input_identity),
    )


def build_phase12_resumed_campaign_lock(
    locked: Phase12LockedSelection,
    *,
    source_commit: str,
    frozen_at_utc: str,
) -> dict[str, object]:
    if not isinstance(source_commit, str) or _SHA40.fullmatch(source_commit) is None:
        raise ValueError("source_commit must be a lowercase 40-character Git SHA")
    validate_utc(frozen_at_utc)
    original = locked.selection_campaign_lock
    payload = {
        key: value
        for key, value in original.items()
        if key != "campaign_lock_sha256"
    }
    payload["source_commit"] = source_commit
    payload["frozen_at_utc"] = frozen_at_utc
    payload["manifest_sha256"] = locked.selection_lock["selection_lock_sha256"]
    return {**payload, "campaign_lock_sha256": canonical_json_sha256(payload)}
