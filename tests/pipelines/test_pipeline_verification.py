"""Tests for SqlSnapshotPipeline publish flow."""

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory


class TestSqlSnapshotPipeline(unittest.TestCase):
    def setUp(self):
        factory = Mock(spec=DBConnectionFactory)
        factory.qualify = lambda object_name, database_type="prod": f"[Data].[{object_name}]"
        self.pipeline = FactoryInventoryPipeline(
            batch_id=123,
            snapshot_date=date(2024, 1, 15),
            connection_factory=factory,
        )

    @patch.object(FactoryInventoryPipeline, "execute_procedure")
    def test_publish_calls_snapshot_proc(self, mock_execute):
        self.pipeline.publish()
        mock_execute.assert_called_once()
        args, kwargs = mock_execute.call_args
        self.assertEqual(args[0], "[Data].[etl_usp_build_factory_inventory_snapshot]")
        self.assertEqual(kwargs["parameters"]["batch_id"], 123)


if __name__ == "__main__":
    unittest.main()
