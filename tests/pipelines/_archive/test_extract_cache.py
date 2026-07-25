"""Tests for extract cache utilities."""

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.orchestrator.pipelines.utils.extract_cache import (
    EXTRACT_FILENAME,
    STATUS_EXTRACT_COMPLETE,
    STATUS_EXTRACTING,
    VERIFIED_SOURCE_CACHE,
    VERIFIED_STAGING,
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

    def test_write_and_read_extract_single_file(self):
        df = pd.DataFrame(
            [(1, "A", 10)],
            columns=["factory_id", "product_batch_no", "on_hand_qty"],
        )
        self.cache.write_extract(df, self.query_hash)

        self.assertTrue(self.cache.extract_path.is_file())
        self.assertFalse((self.cache.batch_cache_dir / "chunk_0001.pkl").exists())

        read_back = self.cache.read_extract(self.query_hash)
        self.assertEqual(len(read_back), 1)
        self.assertEqual(list(read_back.columns), list(df.columns))

    def test_set_verified_step_and_is_source_cache_verified(self):
        df = pd.DataFrame({"factory_id": [1]})
        self.cache.write_extract(df, self.query_hash)
        self.assertFalse(self.cache.is_source_cache_verified(self.query_hash))

        self.cache.set_verified_step(VERIFIED_SOURCE_CACHE, source_row_count=1)
        self.assertTrue(self.cache.is_source_cache_verified(self.query_hash))
        self.assertFalse(self.cache.is_staging_verified(self.query_hash))

        self.cache.set_verified_step(VERIFIED_STAGING)
        self.assertTrue(self.cache.is_staging_verified(self.query_hash))

    def test_delete_cache_removes_directory(self):
        df = pd.DataFrame({"factory_id": [1]})
        self.cache.write_extract(df, self.query_hash)
        self.assertTrue(self.cache.batch_cache_dir.exists())
        self.cache.delete_cache()
        self.assertFalse(self.cache.batch_cache_dir.exists())

    def test_read_extract_raises_on_row_count_mismatch(self):
        df = pd.DataFrame({"factory_id": [1, 2]})
        self.cache.write_extract(df, self.query_hash)
        manifest = self.cache.read_manifest()
        manifest["row_count"] = 99
        with self.cache.manifest_path().open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle)

        with self.assertRaises(ExtractCacheError):
            self.cache.read_extract(self.query_hash)

    def test_require_extract_complete_raises_when_missing(self):
        with self.assertRaises(ExtractCacheError):
            self.cache.require_extract_complete()

    def test_begin_extract_creates_extracting_manifest(self):
        self.cache.begin_extract(self.query_hash)
        with self.cache.manifest_path().open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["status"], STATUS_EXTRACTING)
        self.assertIsNone(manifest.get("last_verified_step"))

    def test_is_extract_complete_without_verification(self):
        df = pd.DataFrame({"factory_id": [1]})
        self.cache.write_extract(df, self.query_hash)
        self.assertTrue(self.cache.is_extract_complete(self.query_hash))
        self.assertFalse(self.cache.is_source_cache_verified(self.query_hash))


if __name__ == "__main__":
    unittest.main()
