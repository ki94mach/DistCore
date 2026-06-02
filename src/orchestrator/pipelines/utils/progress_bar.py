"""Simple terminal progress bar (no external dependencies)."""

from __future__ import annotations

import sys
import time
from typing import Optional


class RowProgressBar:
    """In-place progress bar for row-based ETL steps."""

    def __init__(
        self,
        label: str,
        total: Optional[int] = None,
        *,
        width: int = 36,
        min_interval_s: float = 0.15,
    ) -> None:
        self.label = label
        self.total = total if total and total > 0 else None
        self.width = width
        self.min_interval_s = min_interval_s
        self.current = 0
        self._last_render_at = 0.0
        self._active = True

    def update(self, current: int, message: str = "") -> None:
        if not self._active:
            return
        self.current = max(0, current)
        now = time.monotonic()
        if (
            self.current < (self.total or current)
            and now - self._last_render_at < self.min_interval_s
        ):
            return
        self._last_render_at = now
        self._render(message)

    def close(self, message: str = "") -> None:
        if not self._active:
            return
        if self.total is not None:
            self.current = self.total
        self._render(message)
        sys.stderr.write("\n")
        sys.stderr.flush()
        self._active = False

    def _render(self, message: str = "") -> None:
        suffix = f" {message}" if message else ""
        if self.total is not None:
            ratio = min(1.0, self.current / self.total)
            filled = int(self.width * ratio)
            bar = "=" * filled + "-" * (self.width - filled)
            pct = ratio * 100
            line = (
                f"\r{self.label} [{bar}] "
                f"{self.current:,}/{self.total:,} ({pct:5.1f}%){suffix}"
            )
        else:
            marker_pos = self.current % self.width if self.width else 0
            chars = list("-" * self.width)
            span = max(1, self.width // 6)
            for offset in range(span):
                idx = (marker_pos + offset * 2) % self.width
                chars[idx] = "="
            bar = "".join(chars)
            line = f"\r{self.label} [{bar}] {self.current:,} rows{suffix}"

        sys.stderr.write(line.ljust(100))
        sys.stderr.flush()
