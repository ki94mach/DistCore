"""Helpers for building qualified SQL Server object names from config."""

from typing import Any, Dict

DEFAULT_SCHEMA = "Data"


def get_schema_from_config(database_config: Dict[str, Any]) -> str:
    """Return schema name for a database entry, defaulting to Data."""
    schema = database_config.get("schema", DEFAULT_SCHEMA)
    if not schema or not isinstance(schema, str):
        raise ValueError("Database configuration 'schema' must be a non-empty string")
    return schema


def qualify_object(schema: str, object_name: str) -> str:
    """Return [schema].[object_name]."""
    return f"[{schema}].[{object_name}]"


def qualify_cross_db(database: str, schema: str, object_name: str) -> str:
    """Return [database].[schema].[object_name]."""
    return f"[{database}].[{schema}].[{object_name}]"
