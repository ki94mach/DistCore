"""Process-wide single-flight lock for ETL / optimize jobs."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LockHolder:
    job_id: str
    kind: str


class SingleFlightLock:
    """Allow at most one refresh or optimize job in the process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._holder: Optional[LockHolder] = None

    def try_acquire(self, job_id: str, kind: str) -> Optional[LockHolder]:
        """Acquire the lock or return the current holder if busy."""
        with self._lock:
            if self._holder is not None:
                return self._holder
            self._holder = LockHolder(job_id=job_id, kind=kind)
            return None

    def release(self, job_id: str) -> None:
        with self._lock:
            if self._holder is not None and self._holder.job_id == job_id:
                self._holder = None

    def current(self) -> Optional[LockHolder]:
        with self._lock:
            return self._holder
