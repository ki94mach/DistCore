"""Tests for terminal progress bar."""

import sys
import unittest
from io import StringIO
from unittest.mock import patch

from src.orchestrator.pipelines.utils.progress_bar import RowProgressBar


class TestRowProgressBar(unittest.TestCase):
    @patch("sys.stderr", new_callable=StringIO)
    def test_render_with_total(self, mock_stderr):
        bar = RowProgressBar("Test", total=100, min_interval_s=0)
        bar.update(50)
        bar.close()
        output = mock_stderr.getvalue()
        self.assertIn("Test", output)
        self.assertIn("50/100", output)
        self.assertIn("50.0%", output)

    @patch("sys.stderr", new_callable=StringIO)
    def test_render_without_total(self, mock_stderr):
        bar = RowProgressBar("Extract", min_interval_s=0)
        bar.update(1000)
        bar.close("done")
        output = mock_stderr.getvalue()
        self.assertIn("1,000 rows", output)


if __name__ == "__main__":
    unittest.main()
