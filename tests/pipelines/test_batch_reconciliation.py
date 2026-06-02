"""Tests for batch reconciliation before cache load and publish."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.pipelines.utils.batch_reconciliation import (
    cleanup_batch_data,
    detect_batch_mismatches,
    reconcile_before_publish,
    reconcile_before_staging_load,
)
from src.orchestrator.pipelines.utils.extract_cache import ExtractCache, ExtractCacheError
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory


class TestDetectBatchMismatches(unittest.TestCase):
    def test_no_mismatch_when_aligned(self):
        reasons = detect_batch_mismatches(
            batch_id=10202,
            expected_batch_type="FACTORY_INVENTORY",
            batch_run={"batch_type": "FACTORY_INVENTORY", "status": "RUNNING"},
            staging_count=0,
            snapshot_count=0,
            manifest={
                "batch_id": 10202,
                "batch_type": "FACTORY_INVENTORY",
                "row_count": 100,
                "extract_query_hash": "abc",
            },
            current_query_hash="abc",
        )
        self.assertEqual(reasons, [])

    def test_staging_count_mismatch(self):
        reasons = detect_batch_mismatches(
            batch_id=10202,
            expected_batch_type="FACTORY_INVENTORY",
            batch_run={"batch_type": "FACTORY_INVENTORY", "status": "RUNNING"},
            staging_count=50,
            snapshot_count=0,
            manifest={"row_count": 100, "extract_query_hash": "abc"},
            current_query_hash="abc",
        )
        self.assertTrue(any("staging row count" in r for r in reasons))

    def test_query_hash_mismatch(self):
        reasons = detect_batch_mismatches(
            batch_id=10202,
            expected_batch_type="FACTORY_INVENTORY",
            batch_run={"batch_type": "FACTORY_INVENTORY", "status": "RUNNING"},
            staging_count=0,
            snapshot_count=0,
            manifest={"row_count": 100, "extract_query_hash": "old"},
            current_query_hash="new",
        )
        self.assertTrue(any("query hash" in r for r in reasons))

    def test_publish_requires_staging_rows(self):
        reasons = detect_batch_mismatches(
            batch_id=10202,
            expected_batch_type="FACTORY_INVENTORY",
            batch_run={"batch_type": "FACTORY_INVENTORY", "status": "RUNNING"},
            staging_count=0,
            snapshot_count=10,
            manifest={"row_count": 100, "extract_query_hash": "abc"},
            current_query_hash="abc",
            for_publish=True,
        )
        self.assertTrue(any("no staging rows" in r for r in reasons))


class TestReconcileBeforeStagingLoad(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_root = Path(self.temp_dir.name)
        self.batch_id = 10202
        self.connection_factory = MagicMock(spec=DBConnectionFactory)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("src.orchestrator.pipelines.utils.batch_reconciliation.cleanup_batch_data")
    @patch("src.orchestrator.pipelines.utils.batch_reconciliation.count_snapshot_rows", return_value=0)
    @patch("src.orchestrator.pipelines.utils.batch_reconciliation.count_staging_rows", return_value=50)
    @patch(
        "src.orchestrator.pipelines.utils.batch_reconciliation.get_batch_run",
        return_value={"batch_type": "FACTORY_INVENTORY", "status": "RUNNING"},
    )
    def test_staging_mismatch_triggers_cleanup(
        self,
        _mock_batch_run,
        _mock_staging_count,
        _mock_snapshot_count,
        mock_cleanup,
    ):
        cache = ExtractCache(self.cache_root, "FACTORY_INVENTORY", self.batch_id)
        cache.write_extract(pd.DataFrame({"factory_id": range(100)}), "hash")

        reconcile_before_staging_load(
            connection_factory=self.connection_factory,
            batch_id=self.batch_id,
            batch_type="FACTORY_INVENTORY",
            staging_table="[Data].[stg_FactoryInventory]",
            snapshot_table="[Data].[snp_FactoryInventorySnapshot]",
            cache=cache,
            query_hash="hash",
        )

        mock_cleanup.assert_called_once()

    @patch("src.orchestrator.pipelines.utils.batch_reconciliation.cleanup_batch_data")
    @patch("src.orchestrator.pipelines.utils.batch_reconciliation.count_snapshot_rows", return_value=0)
    @patch("src.orchestrator.pipelines.utils.batch_reconciliation.count_staging_rows", return_value=0)
    @patch(
        "src.orchestrator.pipelines.utils.batch_reconciliation.get_batch_run",
        return_value={"batch_type": "FACTORY_INVENTORY", "status": "RUNNING"},
    )
    def test_query_hash_mismatch_raises_after_cleanup(
        self,
        _mock_batch_run,
        _mock_staging_count,
        _mock_snapshot_count,
        mock_cleanup,
    ):
        cache = ExtractCache(self.cache_root, "FACTORY_INVENTORY", self.batch_id)
        cache.write_extract(pd.DataFrame({"factory_id": range(10)}), "old_hash")

        with self.assertRaises(ExtractCacheError):
            reconcile_before_staging_load(
                connection_factory=self.connection_factory,
                batch_id=self.batch_id,
                batch_type="FACTORY_INVENTORY",
                staging_table="[Data].[stg_FactoryInventory]",
                snapshot_table="[Data].[snp_FactoryInventorySnapshot]",
                cache=cache,
                query_hash="new_hash",
            )

        mock_cleanup.assert_called_once()
        self.assertFalse(cache.batch_cache_dir.exists())


class TestPipelineReconcileIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_root = Path(self.temp_dir.name)
        self.batch_id = 123
        self.snapshot_date = date(2024, 1, 15)
        self.connection_factory_mock = MagicMock(spec=DBConnectionFactory)
        self.pipeline = FactoryInventoryPipeline(
            batch_id=self.batch_id,
            snapshot_date=self.snapshot_date,
            connection_factory=self.connection_factory_mock,
            cache_dir=self.cache_root,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch(
        "src.orchestrator.pipelines.pipeline_template.reconcile_before_staging_load",
    )
    @patch(
        "src.orchestrator.pipelines.pipeline_template.count_staging_rows",
        return_value=10,
    )
    @patch.object(FactoryInventoryPipeline, "_load_rows_from_cache")
    @patch.object(FactoryInventoryPipeline, "_prepare_staging_table")
    def test_load_calls_reconcile(
        self,
        _mock_prepare,
        _mock_load_rows,
        _mock_staging_count,
        mock_reconcile,
    ):
        cache = ExtractCache(self.cache_root, self.pipeline.batch_type, self.batch_id)
        cache.write_extract(pd.DataFrame({"factory_id": range(10)}), "hash")
        cache.set_verified_step("source_cache", source_row_count=10)

        with patch.object(self.pipeline, "_compute_query_hash", return_value="hash"):
            self.pipeline._run_load_with_verification(
                extract_query="SELECT 1",
                batch_size=100,
                query_hash="hash",
                max_verification_retries=3,
            )

        mock_reconcile.assert_called_once()

    @patch("src.orchestrator.pipelines.pipeline_template.reconcile_before_publish")
    @patch.object(FactoryInventoryPipeline, "execute_procedure")
    def test_publish_calls_reconcile(self, mock_execute, mock_reconcile):
        self.pipeline.publish()
        mock_reconcile.assert_called_once()
        mock_execute.assert_called_once()


class TestCleanupBatchData(unittest.TestCase):
    def test_cleanup_executes_delete_statements(self):
        connection_factory = MagicMock(spec=DBConnectionFactory)
        conn = MagicMock()
        cursor = MagicMock()
        connection_factory.connection.return_value.__enter__.return_value = conn
        conn.cursor.return_value = cursor

        cleanup_batch_data(
            connection_factory,
            "[Data].[stg_FactoryInventory]",
            "[Data].[snp_FactoryInventorySnapshot]",
            10202,
        )

        self.assertEqual(cursor.execute.call_count, 2)
        conn.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
