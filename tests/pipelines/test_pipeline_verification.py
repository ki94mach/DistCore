"""Tests for TemplatePipeline verification and cache deletion."""

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
from src.orchestrator.pipelines.utils.extract_cache import ExtractCache
from src.orchestrator.pipelines.utils.stage_verification import StageVerificationError
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory


class TestPipelineVerification(unittest.TestCase):
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
        "src.orchestrator.pipelines.pipeline_template.count_staging_rows",
        return_value=10,
    )
    @patch.object(FactoryInventoryPipeline, "_load_rows_from_cache")
    @patch.object(FactoryInventoryPipeline, "_prepare_staging_table")
    def test_successful_load_deletes_cache(
        self,
        mock_prepare,
        mock_load_rows,
        mock_staging_count,
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

        self.assertFalse(cache.batch_cache_dir.exists())
        mock_load_rows.assert_called_once()

    @patch(
        "src.orchestrator.pipelines.pipeline_template.count_source_rows",
        return_value=10,
    )
    def test_source_cache_mismatch_retries_extract(self, mock_source_count):
        cache = ExtractCache(self.cache_root, self.pipeline.batch_type, self.batch_id)
        extract_calls = [0]

        def extract_side_effect(*_args, **_kwargs):
            extract_calls[0] += 1
            row_count = 5 if extract_calls[0] == 1 else 10
            cache.write_extract(
                pd.DataFrame({"factory_id": range(row_count)}),
                "hash",
            )

        with patch.object(
            self.pipeline, "_extract_to_cache", side_effect=extract_side_effect
        ):
            with patch.object(self.pipeline, "_compute_query_hash", return_value="hash"):
                self.pipeline._run_extract_with_verification(
                    extract_query="SELECT 1",
                    batch_size=100,
                    query_hash="hash",
                    force_extract=False,
                    max_verification_retries=3,
                )

        self.assertEqual(extract_calls[0], 2)
        self.assertTrue(cache.is_source_cache_verified("hash"))

    @patch(
        "src.orchestrator.pipelines.pipeline_template.count_staging_rows",
        side_effect=[8, 10],
    )
    @patch.object(FactoryInventoryPipeline, "_load_rows_from_cache")
    @patch.object(FactoryInventoryPipeline, "_prepare_staging_table")
    @patch.object(FactoryInventoryPipeline, "_cleanup_partial_staging_data")
    def test_staging_mismatch_retries_load(
        self,
        mock_cleanup,
        mock_prepare,
        mock_load_rows,
        mock_staging_count,
    ):
        cache = ExtractCache(self.cache_root, self.pipeline.batch_type, self.batch_id)
        cache.write_extract(pd.DataFrame({"factory_id": range(10)}), "hash")
        cache.set_verified_step("source_cache", source_row_count=10)

        with patch.object(self.pipeline, "_compute_query_hash", return_value="hash"):
            with patch(
                "src.orchestrator.pipelines.pipeline_template.count_source_rows"
            ) as mock_source_count:
                self.pipeline._run_load_with_verification(
                    extract_query="SELECT 1",
                    batch_size=100,
                    query_hash="hash",
                    max_verification_retries=3,
                )
                mock_source_count.assert_not_called()

        self.assertEqual(mock_load_rows.call_count, 2)
        self.assertFalse(cache.batch_cache_dir.exists())


if __name__ == "__main__":
    unittest.main()
