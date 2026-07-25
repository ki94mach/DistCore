"""Tests for FactoryInventoryPipeline."""

import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from datetime import date

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory


class TestFactoryInventoryPipeline(unittest.TestCase):
    """Test cases for FactoryInventoryPipeline."""

    def setUp(self):
        self.batch_id = 123
        self.snapshot_date = date(2024, 1, 15)
        self.connection_factory_mock = Mock(spec=DBConnectionFactory)
        self.connection_factory_mock.qualify = (
            lambda object_name, database_type="test": f"[Data].[{object_name}]"
        )
        self.pipeline = FactoryInventoryPipeline(
            batch_id=self.batch_id,
            snapshot_date=self.snapshot_date,
            connection_factory=self.connection_factory_mock,
        )

    def test_init(self):
        self.assertEqual(self.pipeline.batch_id, self.batch_id)
        self.assertEqual(self.pipeline.snapshot_date, self.snapshot_date)
        self.assertIsNotNone(self.pipeline._sql_executor)

    @patch.object(FactoryInventoryPipeline, "finish_batch")
    @patch.object(FactoryInventoryPipeline, "_ensure_batch_created")
    @patch.object(FactoryInventoryPipeline, "_ensure_snapshot_date")
    def test_load_stage_prepares_batch(self, mock_ensure_date, mock_ensure_batch, mock_finish):
        self.pipeline.load_stage()
        mock_ensure_date.assert_called_once()
        mock_ensure_batch.assert_called_once()
        mock_finish.assert_called_once_with(self.batch_id, "SUCCESS", "Batch prepared")

    @patch.object(FactoryInventoryPipeline, "finish_batch")
    @patch.object(FactoryInventoryPipeline, "execute_procedure")
    def test_publish(self, mock_execute, mock_finish):
        self.pipeline.publish()

        mock_execute.assert_called_once_with(
            "[Data].[etl_usp_build_factory_inventory_snapshot]",
            parameters={
                "batch_id": self.batch_id,
                "snapshot_date": self.snapshot_date,
            },
            database_type="test",
        )
        mock_finish.assert_called_once_with(
            self.batch_id, "SUCCESS", "Snapshot publish complete"
        )

    def test_finish_batch(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        self.connection_factory_mock.get_connection.return_value = mock_conn

        self.pipeline.finish_batch(
            batch_id=456,
            status="SUCCESS",
            message="Test completed",
        )

        self.connection_factory_mock.get_connection.assert_called_once_with(
            "test",
            use_pool=False,
        )
        mock_cursor.execute.assert_called_once()
        exec_sql, param_values = mock_cursor.execute.call_args[0]
        self.assertIn("ctl_usp_finish_batch", exec_sql)
        self.assertEqual(param_values, [456, "SUCCESS", "Test completed"])
        mock_conn.close.assert_called_once()

    @patch.object(FactoryInventoryPipeline, "load_stage")
    @patch.object(FactoryInventoryPipeline, "publish")
    @patch.object(FactoryInventoryPipeline, "finish_batch")
    def test_run_success(self, mock_finish, mock_publish, mock_load):
        self.pipeline.run()

        mock_load.assert_called_once()
        mock_publish.assert_called_once()
        mock_finish.assert_called_once_with(self.batch_id, "SUCCESS", "OK")

    @patch.object(FactoryInventoryPipeline, "load_stage")
    @patch.object(FactoryInventoryPipeline, "publish")
    @patch.object(FactoryInventoryPipeline, "finish_batch")
    def test_run_failure(self, mock_finish, mock_publish, mock_load):
        mock_publish.side_effect = Exception("Publish failed")

        with self.assertRaises(Exception):
            self.pipeline.run()

        mock_finish.assert_called_once_with(
            self.batch_id,
            "FAILED",
            "Publish failed",
        )


if __name__ == "__main__":
    unittest.main()
