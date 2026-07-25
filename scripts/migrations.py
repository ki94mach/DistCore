"""Run SQL migrations against dev (full) or prod (snapshots + ctl + fact only)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory
from src.orchestrator.services.sql_server_db.executors.sql_executor import SQLExecutor
from src.orchestrator.services.vpn import ensure_vpn_connected

PROD_MIGRATION_PREFIXES = (
    "000_",
    "010_",
    "030_",
    "031_",
    "032_",
    "033_",
    "034_",
    "036_",
)

STAGING_MIGRATION_PREFIXES = (
    "020_",
    "021_",
    "022_",
    "023_",
    "024_",
    "035_",
)


def _migration_files(migrations_dir: Path, *, prod: bool) -> list[Path]:
    all_files = sorted(migrations_dir.glob("*.sql"))
    if not prod:
        return all_files
    return [
        path
        for path in all_files
        if path.name.startswith(PROD_MIGRATION_PREFIXES)
        and not path.name.startswith(STAGING_MIGRATION_PREFIXES)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DistCore SQL migrations.")
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Run prod migrations only (ctl, snapshots, fact table). Skips staging tables.",
    )
    parser.add_argument(
        "--database-type",
        default=None,
        help="Database connection key from db.yml (default: test).",
    )
    args = parser.parse_args()

    ensure_vpn_connected()

    database_type = args.database_type or "test"
    factory = DBConnectionFactory()
    executor = SQLExecutor(factory)

    project_root = Path(__file__).resolve().parent.parent
    migrations_dir = project_root / "sql" / "00_migrations"
    migration_files = _migration_files(migrations_dir, prod=args.prod)

    mode_label = "prod" if args.prod else "full"
    print(f"Running {mode_label} migrations on '{database_type}' ({len(migration_files)} files)...")

    for migration_file in migration_files:
        relative_path = migration_file.relative_to(project_root / "sql")
        print(f"Executing migration: {relative_path}")
        try:
            executor.execute_sql_file(str(relative_path), database_type=database_type)
            print(f"Migration executed successfully: {relative_path}")
        except Exception as exc:
            print(f"X Migration failed: {relative_path}")
            print(f"   Error: {exc}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    main()
