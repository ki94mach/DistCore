"""Tests for database schema configuration and object name qualification."""

import sys
import unittest
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory
from src.orchestrator.services.sql_server_db.schema import (
    DEFAULT_SCHEMA,
    get_schema_from_config,
    qualify_cross_db,
    qualify_object,
)


class TestSchemaHelpers(unittest.TestCase):
    def test_qualify_object(self):
        self.assertEqual(qualify_object("Data", "ctl_BatchRun"), "[Data].[ctl_BatchRun]")

    def test_qualify_cross_db(self):
        self.assertEqual(
            qualify_cross_db("DWOrchid", "Data", "DimDate"),
            "[DWOrchid].[Data].[DimDate]",
        )

    def test_default_schema_when_omitted(self):
        self.assertEqual(
            get_schema_from_config({"server": "localhost", "database": "MyDb"}),
            DEFAULT_SCHEMA,
        )


class TestDBConnectionFactorySchema(unittest.TestCase):
    """Uses db.yml (schema from source and prod connections)."""

    @classmethod
    def setUpClass(cls):
        cls.factory = DBConnectionFactory()

    def test_get_schema_from_config(self):
        source_schema = self.factory.get_schema("source")
        prod_schema = self.factory.get_schema("prod")
        self.assertTrue(source_schema)
        self.assertTrue(prod_schema)
        # Live DWOrchid dims are under dbo; keep this as a soft check when configured.
        self.assertEqual(
            source_schema,
            self.factory.get_database_config("source").get("schema", DEFAULT_SCHEMA),
        )

    def test_qualify_uses_configured_schema(self):
        prod_schema = self.factory.get_schema("prod")
        self.assertEqual(
            self.factory.qualify("snp_SalesSnapshot", "prod"),
            f"[{prod_schema}].[snp_SalesSnapshot]",
        )

    def test_qualify_cross_db_uses_source_config(self):
        source_db = self.factory.get_database_config("source")["database"]
        source_schema = self.factory.get_schema("source")
        qualified = self.factory.qualify_cross_db("DimProduct", "source")
        self.assertEqual(qualified, f"[{source_db}].[{source_schema}].[DimProduct]")
        # DimDate must follow the same centralized source.schema (not a hardcoded dbo).
        self.assertEqual(
            self.factory.qualify_cross_db("DimDate", "source"),
            f"[{source_db}].[{source_schema}].[DimDate]",
        )

if __name__ == "__main__":
    unittest.main()
