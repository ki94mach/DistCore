"""Tests for extract cache utilities."""

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.orchestrator.pipelines.utils.extract_cache import (
    STATUS_EXTRACT_COMPLETE,
    STATUS_EXTRACTING,
    ExtractCache,
    ExtractCacheError,
    compute_extract_query_hash,
)


class TestExtractCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_root = Path(self.temp_dir.name)
        self.cache = ExtractCache(self.cache_root, "FACTORY_INVENTORY", 42)
        self.query_hash = compute_extract_query_hash(
            extract_query="SELECT 1",
            batch_type="FACTORY_INVENTORY",
            since_date=date(2024, 1, 1),
            snapshot_date=date(2024, 1, 15),
            single_date_only=False,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compute_extract_query_hash_is_stable(self):
        hash_a = compute_extract_query_hash(
            extract_query="SELECT 1",
            batch_type="FACTORY_INVENTORY",
            since_date=None,
            snapshot_date=date(2024, 1, 15),
            single_date_only=False,
        )
        hash_b = compute_extract_query_hash(
            extract_query="SELECT 1",
            batch_type="FACTORY_INVENTORY",
            since_date=None,
            snapshot_date=date(2024, 1, 15),
            single_date_only=False,
        )
        self.assertEqual(hash_a, hash_b)
        self.assertNotEqual(
            hash_a,
            compute_extract_query_hash(
                extract_query="SELECT 2",
                batch_type="FACTORY_INVENTORY",
                since_date=None,
                snapshot_date=date(2024, 1, 15),
                single_date_only=False,
            ),
        )

    def test_extract_and_finalize_writes_manifest_and_chunks(self):
        self.cache.begin_extract(self.query_hash)
        chunk_file = self.cache.write_chunk(
            1,
            [(1, "A", 10)],
            ["factory_id", "product_batch_no", "on_hand_qty"],
        )
        self.cache.finalize_extract(
            query_hash=self.query_hash,
            chunk_files=[chunk_file],
            row_count=1,
            column_names=["factory_id", "product_batch_no", "on_hand_qty"],
        )

        manifest = self.cache.read_manifest()
        self.assertEqual(manifest["status"], STATUS_EXTRACT_COMPLETE)
        self.assertEqual(manifest["row_count"], 1)
        self.assertTrue(self.cache.is_extract_complete(self.query_hash))

    def test_iter_chunks_yields_rows(self):
        self.cache.begin_extract(self.query_hash)
        chunk_file = self.cache.write_chunk(
            1,
            [(1, 100), (2, 200)],
            ["factory_id", "on_hand_qty"],
        )
        self.cache.finalize_extract(
            query_hash=self.query_hash,
            chunk_files=[chunk_file],
            row_count=2,
            column_names=["factory_id", "on_hand_qty"],
        )

        chunks = list(self.cache.iter_chunks(self.query_hash))
        self.assertEqual(len(chunks), 1)
        columns, rows = chunks[0]
        self.assertEqual(columns, ["factory_id", "on_hand_qty"])
        self.assertEqual(rows, [(1, 100), (2, 200)])

    def test_delete_cache_removes_directory(self):
        self.cache.begin_extract(self.query_hash)
        self.cache.finalize_extract(
            query_hash=self.query_hash,
            chunk_files=[],
            row_count=0,
            column_names=[],
        )
        self.assertTrue(self.cache.batch_cache_dir.exists())
        self.cache.delete_cache()
        self.assertFalse(self.cache.batch_cache_dir.exists())

    def test_require_extract_complete_raises_when_missing(self):
        with self.assertRaises(ExtractCacheError):
            self.cache.require_extract_complete()

    def test_require_extract_complete_raises_on_hash_mismatch(self):
        self.cache.begin_extract(self.query_hash)
        self.cache.finalize_extract(
            query_hash=self.query_hash,
            chunk_files=[],
            row_count=0,
            column_names=[],
        )
        with self.assertRaises(ExtractCacheError):
            self.cache.require_extract_complete("different-hash")

    def test_clear_removes_incomplete_extract(self):
        self.cache.begin_extract(self.query_hash)
        manifest_path = self.cache.manifest_path()
        self.assertTrue(manifest_path.exists())
        with manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["status"], STATUS_EXTRACTING)
        self.cache.clear()
        self.assertFalse(self.cache.batch_cache_dir.exists())


if __name__ == "__main__":
    unittest.main()
