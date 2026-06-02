"""Row-count verification between source DB, extract cache, and staging DB."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory


class StageVerificationError(Exception):
    """Row-count mismatch between source, cache, and staging after retries."""


def build_source_count_query(extract_query: str) -> str:
    trimmed = extract_query.strip().rstrip(";")
    return f"SELECT COUNT(*) AS row_count FROM ({trimmed}) AS _extract_src"


def count_source_rows(connection_factory: "DBConnectionFactory", extract_query: str) -> int:
    count_query = build_source_count_query(extract_query)
    with connection_factory.connection("source") as source_conn:
        cursor = source_conn.cursor()
        cursor.execute(count_query)
        result = cursor.fetchone()
        if result is None:
            raise StageVerificationError("Source count query returned no rows.")
        return int(result[0])


def count_staging_rows(
    connection_factory: "DBConnectionFactory",
    staging_table: str,
    batch_id: int,
) -> int:
    query = f"SELECT COUNT(*) AS row_count FROM {staging_table} WHERE batch_id = ?"
    with connection_factory.connection("test") as test_conn:
        cursor = test_conn.cursor()
        cursor.execute(query, (batch_id,))
        result = cursor.fetchone()
        if result is None:
            raise StageVerificationError("Staging count query returned no rows.")
        return int(result[0])


def verify_source_cache_match(
    *,
    source_count: int,
    cache_count: int,
    step_label: str,
) -> None:
    if source_count != cache_count:
        raise StageVerificationError(
            f"{step_label}: source row count ({source_count}) != "
            f"cache row count ({cache_count})."
        )


def verify_cache_staging_match(
    *,
    cache_count: int,
    staging_count: int,
    step_label: str,
) -> None:
    if cache_count != staging_count:
        raise StageVerificationError(
            f"{step_label}: cache row count ({cache_count}) != "
            f"staging row count ({staging_count})."
        )
