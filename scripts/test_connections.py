"""Connectivity smoke test for the DistCore data sources.

Checks, in order:
  1. VPN tunnel (Cisco AnyConnect) — brings it up if needed.
  2. SQL Server databases (source + test) — runs a lightweight query.
  3. DMS SharePoint folders (distributor deliveries) — lists files.

Every line is also written to a UTF-8 report file. Persian (Farsi) DMS
filenames cannot be rendered by the legacy Windows console (conhost, used by
Anaconda Prompt / cmd), which shows them as boxes — open the report file in
Cursor, VS Code, Notepad, or Windows Terminal to read them correctly.

Usage:
    python scripts/test_connections.py                 # test everything
    python scripts/test_connections.py --no-vpn        # skip VPN handling
    python scripts/test_connections.py --sql-only
    python scripts/test_connections.py --dms-only
    python scripts/test_connections.py --open-report   # open the report after
    python scripts/test_connections.py --report PATH   # custom report path
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Force UTF-8 stdout so writing never crashes (rendering is a separate concern).
if sys.platform == 'win32':
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, 'reconfigure'):
            try:
                _stream.reconfigure(encoding='utf-8')
            except Exception:
                pass
    os.environ['PYTHONIOENCODING'] = 'utf-8'

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestrator.services.sql_server_db import DBConnectionFactory
from src.orchestrator.services.dms import DmsClient, DmsConfigLoader
from src.orchestrator.ui.terminal_ui import (
    Colors,
    colorize,
    print_header,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_action,
)


class Reporter:
    """Routes output to the colored console AND a plain UTF-8 report buffer."""

    def __init__(self) -> None:
        self._lines: List[str] = []

    def header(self, text: str, color: str = Colors.BRIGHT_CYAN) -> None:
        print_header(text, color)
        self._lines.append("")
        self._lines.append("=" * 60)
        self._lines.append(text)
        self._lines.append("=" * 60)

    def ok(self, text: str) -> None:
        print_success(text)
        self._lines.append(f"[OK]   {text}")

    def fail(self, text: str) -> None:
        print_error(text)
        self._lines.append(f"[FAIL] {text}")

    def warn(self, text: str) -> None:
        print_warning(text)
        self._lines.append(f"[WARN] {text}")

    def info(self, text: str) -> None:
        print_info(text)
        self._lines.append(f"[INFO] {text}")

    def action(self, text: str) -> None:
        print_action(text)
        self._lines.append(f"->     {text}")

    def kv(self, label: str, value: str, indent: int = 4) -> None:
        prefix = " " * indent
        print(colorize(f"{prefix}{label}: ", Colors.DIM)
              + colorize(str(value), Colors.WHITE))
        self._lines.append(f"{prefix}{label}: {value}")

    def report_only(self, text: str) -> None:
        """Write a line to the report file without printing to the console."""
        self._lines.append(text)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = [
            "DistCore Connection Test Report",
            f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
            "",
        ]
        path.write_text("\n".join(header + self._lines) + "\n", encoding='utf-8')


def ensure_vpn(out: Reporter, skip: bool) -> bool:
    """Make sure the VPN tunnel is up. Returns True if usable (or skipped)."""
    out.header("VPN")
    if skip:
        out.warn("Skipping VPN check (--no-vpn).")
        return True
    from src.orchestrator.services.vpn import ensure_vpn_connected
    return ensure_vpn_connected(log_fn=out.info)


def test_sql_database(out: Reporter, factory: DBConnectionFactory, database_type: str) -> bool:
    """Run a lightweight query against one database and report details."""
    out.action(f"Testing SQL '{database_type}' database...")
    started = time.monotonic()
    try:
        with factory.connection(database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT @@SERVERNAME, DB_NAME(), "
                "CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128))"
            )
            server_name, db_name, version = cursor.fetchone()
        elapsed_ms = (time.monotonic() - started) * 1000
        out.ok(f"SQL '{database_type}' OK ({elapsed_ms:.0f} ms)")
        out.kv("Server", server_name)
        out.kv("Database", db_name)
        out.kv("Version", version)
        return True
    except Exception as exc:
        out.fail(f"SQL '{database_type}' FAILED: {exc}")
        return False


def test_sql(out: Reporter, database_types) -> bool:
    out.header("SQL Server")
    try:
        factory = DBConnectionFactory()
    except Exception as exc:
        out.fail(f"Could not load DB configuration: {exc}")
        return False

    results = [test_sql_database(out, factory, db_type) for db_type in database_types]
    return all(results)


def _resolve_sql_database_types() -> list:
    """Database types present in db.yml (excludes non-db config keys)."""
    try:
        config = DBConnectionFactory().get_config() or {}
        databases = config.get('databases', {})
        excluded = {'driver', 'username', 'password', 'use_windows_auth'}
        types = [key for key in databases if key not in excluded]
        return types or ['source', 'test']
    except Exception:
        return ['source', 'test']


def test_dms_folder(out: Reporter, client: DmsClient, label: str, folder_url: str) -> bool:
    out.action(f"Testing DMS folder '{label}'...")
    started = time.monotonic()
    try:
        files = client.list_files(folder_url)
        elapsed_ms = (time.monotonic() - started) * 1000
        out.ok(f"DMS '{label}' OK — {len(files)} file(s) ({elapsed_ms:.0f} ms)")
        # Console shows a sample (may render as boxes); the report gets them all.
        for file_info in files[:5]:
            out.kv("file", file_info['name'])
        if len(files) > 5:
            out.kv("...", f"and {len(files) - 5} more (full list in report file)")
        out.report_only(f"    --- all {len(files)} file(s) in '{label}' ---")
        for index, file_info in enumerate(files, start=1):
            out.report_only(f"    {index:>2}. {file_info['name']}")
        return True
    except Exception as exc:
        out.fail(f"DMS '{label}' FAILED: {exc}")
        return False


def test_dms(out: Reporter) -> bool:
    out.header("DMS (SharePoint)")
    try:
        config = DmsConfigLoader.get_distributor_deliveries_config()
    except Exception as exc:
        out.fail(f"Could not load DMS configuration: {exc}")
        return False

    try:
        client = DmsClient()
    except Exception as exc:
        out.fail(f"Could not initialize DMS client: {exc}")
        return False

    historical = test_dms_folder(out, client, "historical (1404)", config['historical_folder_url'])
    current = test_dms_folder(out, client, "current (1405)", config['current_folder_url'])
    return historical and current


def main() -> int:
    parser = argparse.ArgumentParser(description="DistCore connectivity smoke test")
    parser.add_argument('--no-vpn', action='store_true', help="Skip VPN handling")
    parser.add_argument('--sql-only', action='store_true', help="Test SQL only")
    parser.add_argument('--dms-only', action='store_true', help="Test DMS only")
    parser.add_argument('--open-report', action='store_true',
                        help="Open the report file when finished")
    parser.add_argument('--report', type=Path, default=None,
                        help="Path to the UTF-8 report file "
                             "(default: logs/connection_test_report.txt)")
    args = parser.parse_args()

    out = Reporter()
    out.header("DistCore Connection Test", Colors.BRIGHT_MAGENTA)

    run_sql = not args.dms_only
    run_dms = not args.sql_only

    vpn_ok = ensure_vpn(out, skip=args.no_vpn)
    if not vpn_ok:
        out.warn("VPN is not up — SQL/DMS tests will likely fail.")

    results = {}
    if run_sql:
        results['SQL Server'] = test_sql(out, _resolve_sql_database_types())
    if run_dms:
        results['DMS'] = test_dms(out)

    out.header("Summary", Colors.BRIGHT_MAGENTA)
    for name, ok in results.items():
        (out.ok if ok else out.fail)(f"{name}: {'PASS' if ok else 'FAIL'}")

    all_ok = bool(results) and all(results.values())
    (out.ok if all_ok else out.fail)(
        "All connection tests passed." if all_ok
        else "One or more connection tests failed."
    )

    report_path = (args.report or (PROJECT_ROOT / 'logs' / 'connection_test_report.txt')).resolve()
    try:
        out.save(report_path)
        out.info(f"Report written (open it to read Farsi filenames): {report_path}")
        if args.open_report and sys.platform == 'win32':
            os.startfile(str(report_path))  # noqa: S606
    except Exception as exc:
        print_warning(f"Could not write report file: {exc}")

    return 0 if all_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
