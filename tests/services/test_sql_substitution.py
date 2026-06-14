"""Tests for SQL $(variable) substitution from db.yml."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.orchestrator.services.sql_server_db.executors.sql_utils import (
    find_unsubstituted_variables,
    substitute_parameters,
)
from src.orchestrator.services.sql_server_db.sql_config import build_sql_substitution_vars


class TestSqlSubstitution(unittest.TestCase):
    def setUp(self):
        self.factory = Mock()
        self.factory.get_database_config.side_effect = lambda key: {
            "source": {"database": "DWOrchid", "schema": "Data"},
            "prod": {"database": "Iris_DW", "schema": "Sale"},
        }[key]

    def test_build_sql_substitution_vars(self):
        vars_ = build_sql_substitution_vars(self.factory, "prod")
        self.assertEqual(vars_["source_database"], "DWOrchid")
        self.assertEqual(vars_["source_schema"], "Data")
        self.assertEqual(vars_["prod_database"], "Iris_DW")
        self.assertEqual(vars_["prod_schema"], "Sale")
        self.assertEqual(vars_["schema"], "Sale")
        self.assertEqual(vars_["database"], "Iris_DW")

    def test_substitute_prod_schema_in_procedure(self):
        sql = "CREATE PROCEDURE [$(prod_schema)].[etl_usp_build_sales_snapshot] AS SELECT 1;"
        result = substitute_parameters(sql, {"prod_schema": "Sale"})
        self.assertIn("[Sale].[etl_usp_build_sales_snapshot]", result)

    def test_substitute_cross_db_reference(self):
        sql = "FROM [$(source_database)].[$(source_schema)].[DimDate]"
        result = substitute_parameters(
            sql,
            {"source_database": "DWOrchid", "source_schema": "Data"},
        )
        self.assertEqual(result, "FROM [DWOrchid].[Data].[DimDate]")

    def test_find_unsubstituted_variables(self):
        sql = "FROM [$(prod_schema)].[snp_SalesSnapshot] JOIN [$(missing_var)].x"
        found = find_unsubstituted_variables(sql)
        self.assertEqual(found, ["missing_var", "prod_schema"])


if __name__ == "__main__":
    unittest.main()
