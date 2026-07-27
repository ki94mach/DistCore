"""Tests for filesystem job store lifecycle."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.web.jobs.store import JobStore


class TestJobStore(unittest.TestCase):
    def test_create_and_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job_id = store.create("refresh", {"snapshot_date": "2026-07-27"})
            meta = store.read_meta(job_id)
            self.assertEqual(meta["status"], "queued")
            store.mark_running(job_id)
            self.assertEqual(store.read_meta(job_id)["status"], "running")
            store.write_result(job_id, {"ok": True})
            store.mark_succeeded(job_id)
            done = store.read_meta(job_id)
            self.assertEqual(done["status"], "succeeded")
            self.assertEqual(store.read_result(job_id), {"ok": True})

    def test_mark_stale_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            queued = store.create("refresh", {})
            running = store.create("optimize", {})
            store.mark_running(running)
            count = store.mark_stale_on_startup()
            self.assertEqual(count, 2)
            self.assertEqual(store.read_meta(queued)["error"], "Process restarted")
            self.assertEqual(store.read_meta(running)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
