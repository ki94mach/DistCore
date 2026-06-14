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
    """Uses db.yml (schema: Data on source and test connections)."""

    @classmethod
    def setUpClass(cls):
        cls.factory = DBConnectionFactory()

    def test_get_schema_from_config(self):
        self.assertEqual(self.factory.get_schema("source"), "Data")
        self.assertEqual(self.factory.get_schema("test"), "Data")

    def test_qualify_uses_configured_schema(self):
        self.assertEqual(
            self.factory.qualify("snp_SalesSnapshot", "test"),
            "[Data].[snp_SalesSnapshot]",
        )

    def test_qualify_cross_db_uses_source_config(self):
        qualified = self.factory.qualify_cross_db("DimProduct", "source")
        self.assertEqual(qualified, "[DWOrchid].[Data].[DimProduct]")


if __name__ == "__main__":
    unittest.main()
