"""
Add UTF-8 BOM to existing CSV files so Excel opens them with correct encoding (Farsi/Unicode).

Use this to fix CSVs that were saved without the BOM and show garbled characters in Excel.

Usage:
    # Fix all CSV files in the project data/ folder (default)
    python scripts/fix_csv_utf8_bom.py

    # Fix specific file(s)
    python scripts/fix_csv_utf8_bom.py path/to/file1.csv path/to/file2.csv

    # Fix all CSVs in a directory
    python scripts/fix_csv_utf8_bom.py path/to/directory
"""

from __future__ import annotations

import sys
from pathlib import Path


def add_bom_to_csv(file_path: Path) -> bool:
    """Read CSV as UTF-8 and rewrite with UTF-8-sig (BOM). Returns True if changed."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Maybe already has BOM or different encoding; try utf-8-sig to strip BOM then re-add
        try:
            content = file_path.read_text(encoding="utf-8-sig")
        except Exception:
            print(f"  Skip (cannot decode): {file_path}", file=sys.stderr)
            return False
    # If first bytes are already BOM, no need to rewrite
    if content.startswith("\ufeff"):
        return False
    file_path.write_text(content, encoding="utf-8-sig")
    return True


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"

    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
        files = []
        for p in paths:
            if p.is_file() and p.suffix.lower() == ".csv":
                files.append(p)
            elif p.is_dir():
                files.extend(p.glob("*.csv"))
            else:
                print(f"  Not found or not CSV: {p}", file=sys.stderr)
    else:
        if not data_dir.is_dir():
            print(f"Data directory not found: {data_dir}", file=sys.stderr)
            sys.exit(1)
        files = list(data_dir.glob("*.csv"))

    if not files:
        print("No CSV files to process.")
        return

    print(f"Processing {len(files)} CSV file(s)...")
    updated = 0
    for f in sorted(files):
        if add_bom_to_csv(f):
            print(f"  Updated: {f}")
            updated += 1
    print(f"Done. Updated {updated} file(s).")


if __name__ == "__main__":
    main()
