"""Reconcile batch_id state in the test DB before cache load or publish."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from src.orchestrator.pipelines.utils.extract_cache import ExtractCache, ExtractCacheError
from src.orchestrator.pipelines.utils.stage_verification import count_staging_rows

if TYPE_CHECKING:
    from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory

LogFn = Optional[Callable[[str], None]]


def _log(log_fn: LogFn, message: str) -> None:
    if log_fn is not None:
        log_fn(message)


def get_batch_run(
    connection_factory: "DBConnectionFactory",
    batch_id: int,
    *,
    database_type: str = "test",
) -> Optional[Dict[str, Any]]:
    query = """
        SELECT batch_type, status
        FROM [Data].[ctl_BatchRun]
        WHERE batch_id = ?
    """
    with connection_factory.connection(database_type) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (batch_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return {"batch_type": row[0], "status": row[1]}


def count_snapshot_rows(
    connection_factory: "DBConnectionFactory",
    snapshot_table: Optional[str],
    batch_id: int,
    *,
    database_type: str = "test",
) -> int:
    if not snapshot_table:
        return 0
    query = f"SELECT COUNT(*) FROM {snapshot_table} WHERE batch_id = ?"
    with connection_factory.connection(database_type) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (batch_id,))
        result = cursor.fetchone()
        if result is None:
            return 0
        return int(result[0])


def cleanup_batch_data(
    connection_factory: "DBConnectionFactory",
    staging_table: str,
    snapshot_table: Optional[str],
    batch_id: int,
    *,
    database_type: str = "test",
) -> None:
    with connection_factory.connection(database_type) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM {staging_table} WHERE batch_id = ?",
            (batch_id,),
        )
        if snapshot_table:
            cursor.execute(
                f"DELETE FROM {snapshot_table} WHERE batch_id = ?",
                (batch_id,),
            )
        conn.commit()


def detect_batch_mismatches(
    *,
    batch_id: int,
    expected_batch_type: str,
    batch_run: Optional[Dict[str, Any]],
    staging_count: int,
    snapshot_count: int,
    manifest: Optional[Dict[str, Any]],
    current_query_hash: Optional[str],
    for_publish: bool = False,
) -> List[str]:
    """Return human-readable mismatch reasons; empty list means OK to proceed."""
    reasons: List[str] = []

    if batch_run is None:
        reasons.append(f"batch_id {batch_id} not found in [Data].[ctl_BatchRun]")
    elif batch_run.get("batch_type") != expected_batch_type:
        reasons.append(
            f"ctl_BatchRun batch_type is {batch_run.get('batch_type')!r}, "
            f"expected {expected_batch_type!r}"
        )

    cache_row_count: Optional[int] = None
    manifest_hash: Optional[str] = None
    if manifest:
        if manifest.get("batch_id") not in (None, batch_id):
            reasons.append(
                f"cache manifest batch_id is {manifest.get('batch_id')}, "
                f"expected {batch_id}"
            )
        if manifest.get("batch_type") not in (None, expected_batch_type):
            reasons.append(
                f"cache manifest batch_type is {manifest.get('batch_type')!r}, "
                f"expected {expected_batch_type!r}"
            )
        cache_row_count = manifest.get("row_count")
        if cache_row_count is not None:
            cache_row_count = int(cache_row_count)
        manifest_hash = manifest.get("extract_query_hash")

    query_hash_mismatch = bool(
        current_query_hash
        and manifest_hash
        and manifest_hash != current_query_hash
    )
    if query_hash_mismatch:
        reasons.append(
            "extract cache query hash does not match current run parameters "
            "(snapshot date or load mode may have changed)"
        )

    staging_cache_mismatch = (
        cache_row_count is not None
        and staging_count > 0
        and staging_count != cache_row_count
    )
    if staging_cache_mismatch:
        reasons.append(
            f"staging row count ({staging_count:,}) != cache manifest row_count "
            f"({cache_row_count:,})"
        )

    if for_publish:
        if staging_count == 0:
            reasons.append("no staging rows for batch_id (cannot publish)")
        elif cache_row_count is not None and staging_count != cache_row_count:
            reasons.append(
                f"staging row count ({staging_count:,}) != cache manifest row_count "
                f"({cache_row_count:,})"
            )

    if snapshot_count > 0 and (
        staging_cache_mismatch
        or (for_publish and staging_count == 0)
        or (for_publish and cache_row_count is not None and staging_count != cache_row_count)
    ):
        reasons.append(
            f"snapshot has {snapshot_count:,} row(s) for batch_id {batch_id} "
            "inconsistent with staging/cache"
        )

    return reasons


def _query_hash_mismatch(reasons: List[str]) -> bool:
    return any("query hash" in reason for reason in reasons)


def reconcile_before_staging_load(
    *,
    connection_factory: "DBConnectionFactory",
    batch_id: int,
    batch_type: str,
    staging_table: str,
    snapshot_table: Optional[str],
    cache: ExtractCache,
    query_hash: str,
    log_fn: LogFn = None,
    database_type: str = "test",
) -> None:
    """Validate batch state; on mismatch delete staging/snapshot rows for batch_id."""
    manifest = cache.read_manifest()
    batch_run = get_batch_run(connection_factory, batch_id, database_type=database_type)
    staging_count = count_staging_rows(
        connection_factory, staging_table, batch_id
    )
    snapshot_count = count_snapshot_rows(
        connection_factory, snapshot_table, batch_id, database_type=database_type
    )

    reasons = detect_batch_mismatches(
        batch_id=batch_id,
        expected_batch_type=batch_type,
        batch_run=batch_run,
        staging_count=staging_count,
        snapshot_count=snapshot_count,
        manifest=manifest,
        current_query_hash=query_hash,
        for_publish=False,
    )

    if not reasons:
        _log(log_fn, f"Batch reconcile: batch {batch_id} OK (staging={staging_count:,}).")
        return

    for reason in reasons:
        _log(log_fn, f"Batch reconcile: mismatch — {reason}")
    _log(
        log_fn,
        f"Batch reconcile: deleting staging"
        + (f" + snapshot" if snapshot_table else "")
        + f" rows for batch_id {batch_id}...",
    )
    cleanup_batch_data(
        connection_factory,
        staging_table,
        snapshot_table,
        batch_id,
        database_type=database_type,
    )
    _log(log_fn, f"Batch reconcile: cleanup complete for batch_id {batch_id}.")

    if _query_hash_mismatch(reasons):
        raise ExtractCacheError(
            f"Extract cache for {batch_type} batch {batch_id} does not match the "
            "current run parameters (snapshot date or load mode). "
            "Use the same staging options as extract, or re-run extract to cache."
        )


def reconcile_before_publish(
    *,
    connection_factory: "DBConnectionFactory",
    batch_id: int,
    batch_type: str,
    staging_table: str,
    snapshot_table: Optional[str],
    cache: Optional[ExtractCache] = None,
    query_hash: Optional[str] = None,
    log_fn: LogFn = None,
    database_type: str = "test",
) -> None:
    """Validate batch state before publish; clean mismatched staging/snapshot data."""
    manifest = cache.read_manifest() if cache is not None else None
    batch_run = get_batch_run(connection_factory, batch_id, database_type=database_type)
    staging_count = count_staging_rows(
        connection_factory, staging_table, batch_id
    )
    snapshot_count = count_snapshot_rows(
        connection_factory, snapshot_table, batch_id, database_type=database_type
    )

    reasons = detect_batch_mismatches(
        batch_id=batch_id,
        expected_batch_type=batch_type,
        batch_run=batch_run,
        staging_count=staging_count,
        snapshot_count=snapshot_count,
        manifest=manifest,
        current_query_hash=query_hash,
        for_publish=True,
    )

    if not reasons:
        _log(
            log_fn,
            f"Batch reconcile: batch {batch_id} OK for publish "
            f"(staging={staging_count:,}).",
        )
        return

    for reason in reasons:
        _log(log_fn, f"Batch reconcile: mismatch — {reason}")
    _log(
        log_fn,
        f"Batch reconcile: deleting staging"
        + (f" + snapshot" if snapshot_table else "")
        + f" rows for batch_id {batch_id}...",
    )
    cleanup_batch_data(
        connection_factory,
        staging_table,
        snapshot_table,
        batch_id,
        database_type=database_type,
    )
    _log(log_fn, f"Batch reconcile: cleanup complete for batch_id {batch_id}.")

    if _query_hash_mismatch(reasons):
        raise ExtractCacheError(
            f"Cannot publish {batch_type} batch {batch_id}: cache parameters changed. "
            "Re-run extract and load staging before publishing."
        )

    staging_after = count_staging_rows(
        connection_factory, staging_table, batch_id
    )
    if staging_after == 0:
        raise ExtractCacheError(
            f"Cannot publish {batch_type} batch {batch_id}: no staging data after "
            "reconciliation. Load staging from cache or run full staging first."
        )
