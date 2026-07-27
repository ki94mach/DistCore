"""Tests for snapshot freshness query and readiness classification."""

from __future__ import annotations

import unittest
from datetime import date, datetime
from unittest.mock import Mock

from src.orchestrator.pipelines.freshness import SnapshotFreshnessRepository


class _FakeCursor:
    def __init__(self, queue):
        self._queue = queue
        self.last_query = ""

    def execute(self, query, _params=()):
        self.last_query = query
        return self

    def fetchone(self):
        if not self._queue:
            return None
        return self._queue.pop(0)


class _FakeConnection:
    def __init__(self, queue):
        self._cursor = _FakeCursor(queue)

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeFactory:
    def __init__(self, rows):
        self._rows = rows

    def qualify(self, object_name, _database_type="prod"):
        return f"[Sale].[{object_name}]"

    def qualify_cross_db(self, object_name, _database_type="source"):
        return f"[DWOrchid].[Data].[{object_name}]"

    def connection(self, _database_type="prod"):
        return _FakeConnection(self._rows)


def _summary(row_count, loaded_key, batch_id, distinct_batch_ids=1):
    return (row_count, loaded_key, datetime(2026, 7, 27, 10, 0, 0), batch_id, distinct_batch_ids)


def _batch(batch_id, batch_type, status):
    return (batch_id, batch_type, status, datetime(2026, 7, 27, 9, 0, 0), datetime(2026, 7, 27, 9, 30, 0), None, "WEB_UI")


class TestSnapshotFreshnessRepository(unittest.TestCase):
    def _repo_for_rows(self, rows):
        return SnapshotFreshnessRepository(_FakeFactory(list(rows)))

    def test_ready_when_required_pipelines_match(self):
        rows = [
            (date(2026, 7, 1),),  # sales month
            (1405, 5),  # jalali
            _summary(1, date(2026, 7, 27), 10), _batch(10, "FACTORY_INVENTORY", "SUCCESS"),
            _summary(2, date(2026, 7, 27), 11), _batch(11, "DISTRIBUTOR_INVENTORY", "SUCCESS"),
            _summary(3, date(2026, 7, 1), 12), _batch(12, "SALES_SNAPSHOT", "SUCCESS"),
            _summary(4, date(2026, 7, 27), 13), _batch(13, "TARGET", "SUCCESS"),
            _summary(0, None, None, 0), None,
        ]
        report = self._repo_for_rows(rows).get_freshness(date(2026, 7, 27))
        self.assertEqual(report.state, "ready")
        deliveries = [p for p in report.pipelines if p.optional_for_optimize][0]
        self.assertEqual(deliveries.state, "missing")

    def test_missing_when_required_snapshot_empty(self):
        rows = [
            (date(2026, 7, 1),), (1405, 5),
            _summary(0, None, None, 0), None,
            _summary(2, date(2026, 7, 27), 11), _batch(11, "DISTRIBUTOR_INVENTORY", "SUCCESS"),
            _summary(3, date(2026, 7, 1), 12), _batch(12, "SALES_SNAPSHOT", "SUCCESS"),
            _summary(4, date(2026, 7, 27), 13), _batch(13, "TARGET", "SUCCESS"),
            _summary(1, date(2026, 7, 27), 14), _batch(14, "DISTRIBUTOR_DELIVERIES", "SUCCESS"),
        ]
        report = self._repo_for_rows(rows).get_freshness(date(2026, 7, 27))
        self.assertEqual(report.state, "missing")

    def test_partial_for_stale_or_mixed_lineage(self):
        rows = [
            (date(2026, 7, 1),), (1405, 5),
            _summary(1, date(2026, 7, 26), 10), _batch(10, "FACTORY_INVENTORY", "SUCCESS"),
            _summary(2, date(2026, 7, 27), 11, 2), _batch(11, "DISTRIBUTOR_INVENTORY", "SUCCESS"),
            _summary(3, date(2026, 7, 1), 12), _batch(12, "SALES_SNAPSHOT", "FAILED"),
            _summary(4, date(2026, 7, 27), 13), _batch(13, "TARGET", "SUCCESS"),
            _summary(1, date(2026, 7, 27), 14), _batch(14, "DISTRIBUTOR_DELIVERIES", "SUCCESS"),
        ]
        report = self._repo_for_rows(rows).get_freshness(date(2026, 7, 27))
        self.assertEqual(report.state, "partial")

    def test_refreshing_when_newer_running_batch_exists(self):
        rows = [
            (date(2026, 7, 1),), (1405, 5),
            _summary(1, date(2026, 7, 27), 10), _batch(11, "FACTORY_INVENTORY", "RUNNING"),
            _summary(2, date(2026, 7, 27), 11), _batch(11, "DISTRIBUTOR_INVENTORY", "SUCCESS"),
            _summary(3, date(2026, 7, 1), 12), _batch(12, "SALES_SNAPSHOT", "SUCCESS"),
            _summary(4, date(2026, 7, 27), 13), _batch(13, "TARGET", "SUCCESS"),
            _summary(1, date(2026, 7, 27), 14), _batch(14, "DISTRIBUTOR_DELIVERIES", "SUCCESS"),
        ]
        report = self._repo_for_rows(rows).get_freshness(date(2026, 7, 27))
        self.assertEqual(report.state, "refreshing")

    def test_sales_and_target_resolution_used(self):
        rows = [
            (date(2026, 7, 1),), (1405, 5),
            _summary(1, date(2026, 7, 27), 10), _batch(10, "FACTORY_INVENTORY", "SUCCESS"),
            _summary(1, date(2026, 7, 27), 11), _batch(11, "DISTRIBUTOR_INVENTORY", "SUCCESS"),
            _summary(1, date(2026, 7, 1), 12), _batch(12, "SALES_SNAPSHOT", "SUCCESS"),
            _summary(1, date(2026, 7, 27), 13), _batch(13, "TARGET", "SUCCESS"),
            _summary(1, date(2026, 7, 27), 14), _batch(14, "DISTRIBUTOR_DELIVERIES", "SUCCESS"),
        ]
        report = self._repo_for_rows(rows).get_freshness(date(2026, 7, 27))
        sales = [p for p in report.pipelines if p.pipeline.value == "sales"][0]
        self.assertEqual(sales.expected_key, date(2026, 7, 1))
        target = [p for p in report.pipelines if p.pipeline.value == "target"][0]
        self.assertEqual(target.expected_key, date(2026, 7, 27))


if __name__ == "__main__":
    unittest.main()
