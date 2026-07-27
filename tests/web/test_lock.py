"""Tests for the single-flight lock."""

from __future__ import annotations

import unittest

from src.web.jobs.lock import SingleFlightLock


class TestSingleFlightLock(unittest.TestCase):
    def test_acquire_and_release(self) -> None:
        lock = SingleFlightLock()
        self.assertIsNone(lock.try_acquire("a", "refresh"))
        holder = lock.try_acquire("b", "optimize")
        self.assertIsNotNone(holder)
        self.assertEqual(holder.job_id, "a")
        self.assertEqual(holder.kind, "refresh")
        lock.release("a")
        self.assertIsNone(lock.try_acquire("b", "optimize"))
        lock.release("b")
        self.assertIsNone(lock.current())

    def test_release_ignores_other_job(self) -> None:
        lock = SingleFlightLock()
        lock.try_acquire("a", "refresh")
        lock.release("other")
        self.assertEqual(lock.current().job_id, "a")


if __name__ == "__main__":
    unittest.main()
