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


def _print_target(factory: DBConnectionFactory, database_type: str) -> None:
    db_cfg = factory.get_database_config(database_type)
    schema = factory.get_schema(database_type)
    print(
        f"Target: server={db_cfg['server']!r}, "
        f"database={db_cfg['database']!r}, schema={schema!r}"
    )


def _check_migration_permissions(factory: DBConnectionFactory, database_type: str) -> bool:
    """Verify the connected login can run DDL migrations."""
    schema = factory.get_schema(database_type)
    db_name = factory.get_database_name(database_type)

    with factory.connection(database_type) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                SUSER_SNAME() AS login_name,
                USER_NAME() AS db_user,
                DB_NAME() AS current_database,
                HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE TABLE') AS can_create_table
            """
        )
        row = cursor.fetchone()
        login_name, db_user, current_database, can_create_table = row

        cursor.execute(
            """
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM sys.schemas WHERE name = ?
            ) THEN 1 ELSE 0 END
            """,
            schema,
        )
        schema_exists = bool(cursor.fetchone()[0])

        cursor.execute(
            "SELECT HAS_PERMS_BY_NAME(?, 'SCHEMA', 'ALTER')",
            schema,
        )
        can_alter_schema = cursor.fetchone()[0]

    print(f"Connected as login={login_name!r}, db_user={db_user!r}, database={current_database!r}")

    ok = True
    if not schema_exists:
        print(
            f"X Schema {schema!r} does not exist in {db_name}. "
            "Ask your DBA to create it before running migrations."
        )
        ok = False

    if not can_create_table:
        print(
            f"X Login lacks CREATE TABLE on database {db_name!r} (SQL error 262). "
            "Migrations cannot create ctl/snapshot/fact tables until a DBA grants DDL rights."
        )
        ok = False

    if can_alter_schema != 1:
        print(
            f"X Login lacks ALTER on schema {schema!r}. "
            "Grant ALTER ON SCHEMA or use a role such as db_ddladmin for migration runs."
        )
        ok = False

    if not ok:
        print()
        print("Example grants for your DBA (adjust login/role names):")
        print(f"  USE [{db_name}];")
        print(f"  -- IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'{schema}')")
        print(f"  --     EXEC('CREATE SCHEMA [{schema}]');")
        print("  -- ALTER ROLE db_ddladmin ADD MEMBER [YOUR_DOMAIN\\your.user];")
        print(f"  -- GRANT ALTER ON SCHEMA::[{schema}] TO [YOUR_DOMAIN\\your.user];")
        print("  -- GRANT CREATE TABLE TO [YOUR_DOMAIN\\your.user];")
        print()
        print("After permissions are granted, re-run:")
        print("  python scripts/migrations.py --prod")

    return ok


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
        help="Database connection key from db.yml (default: prod).",
    )
    parser.add_argument(
        "--skip-permission-check",
        action="store_true",
        help="Skip preflight DDL permission check (not recommended).",
    )
    args = parser.parse_args()

    ensure_vpn_connected()

    database_type = args.database_type or "prod"
    factory = DBConnectionFactory()
    executor = SQLExecutor(factory)

    _print_target(factory, database_type)

    if not args.skip_permission_check and not _check_migration_permissions(factory, database_type):
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent
    migrations_dir = project_root / "sql" / "00_migrations"
    migration_files = _migration_files(migrations_dir, prod=args.prod)

    mode_label = "prod" if args.prod else "full"
    print(f"Running {mode_label} migrations on '{database_type}' ({len(migration_files)} files)...")

    failed = []
    for migration_file in migration_files:
        relative_path = migration_file.relative_to(project_root / "sql")
        print(f"Executing migration: {relative_path}")
        try:
            executor.execute_sql_file(str(relative_path), database_type=database_type)
            print(f"Migration executed successfully: {relative_path}")
        except Exception as exc:
            print(f"X Migration failed: {relative_path}")
            print(f"   Error: {exc}")
            failed.append(relative_path)
            break

    if failed:
        print()
        print(f"Stopped after failure in {failed[0]}. Fix the issue above, then re-run migrations.")
        sys.exit(1)

    print()
    print("All migrations completed successfully.")


if __name__ == "__main__":
    main()
