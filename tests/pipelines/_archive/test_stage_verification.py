"""Tests for stage verification utilities."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.orchestrator.pipelines.utils.stage_verification import (
    StageVerificationError,
    build_source_count_query,
    count_source_rows,
    count_staging_rows,
    verify_cache_staging_match,
    verify_source_cache_match,
)


class TestStageVerification(unittest.TestCase):
    def test_build_source_count_query_wraps_extract(self):
        query = "SELECT col FROM t WHERE x = 1;"
        wrapped = build_source_count_query(query)
        self.assertIn("SELECT COUNT(*)", wrapped)
        self.assertIn("SELECT col FROM t WHERE x = 1", wrapped)
        self.assertIn("_extract_src", wrapped)

    def test_verify_source_cache_match(self):
        verify_source_cache_match(source_count=10, cache_count=10, step_label="test")
        with self.assertRaises(StageVerificationError):
            verify_source_cache_match(source_count=10, cache_count=9, step_label="test")

    def test_verify_cache_staging_match(self):
        verify_cache_staging_match(cache_count=5, staging_count=5, step_label="final")
        with self.assertRaises(StageVerificationError):
            verify_cache_staging_match(cache_count=5, staging_count=4, step_label="final")

    @patch("src.orchestrator.pipelines.utils.stage_verification.build_source_count_query")
    def test_count_source_rows(self, mock_build):
        mock_build.return_value = "SELECT COUNT(*) ..."
        factory = MagicMock()
        conn = MagicMock()
        cursor = MagicMock()
        factory.connection.return_value.__enter__ = MagicMock(return_value=conn)
        factory.connection.return_value.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = (42,)

        count = count_source_rows(factory, "SELECT 1")
        self.assertEqual(count, 42)
        factory.connection.assert_called_once_with("source")

    def test_count_staging_rows(self):
        factory = MagicMock()
        conn = MagicMock()
        cursor = MagicMock()
        factory.connection.return_value.__enter__ = MagicMock(return_value=conn)
        factory.connection.return_value.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = (7,)

        count = count_staging_rows(
            factory,
            "[Data].[stg_FactoryInventory]",
            123,
        )
        self.assertEqual(count, 7)
        cursor.execute.assert_called_once()
        self.assertEqual(cursor.execute.call_args[0][1], (123,))


if __name__ == "__main__":
    unittest.main()
