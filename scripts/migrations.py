import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory
from src.orchestrator.services.sql_server_db.executors.sql_executor import SQLExecutor
from src.orchestrator.services.vpn import ensure_vpn_connected

def main():
    # SQL Server is behind the corporate VPN — make sure it is up.
    ensure_vpn_connected()

    factory = DBConnectionFactory()
    executor = SQLExecutor(factory)

    # Get project root for path resolution
    project_root = Path(__file__).resolve().parent.parent
    migrations_dir = project_root / 'sql' / '00_migrations'
    migration_files = sorted(migrations_dir.glob('*.sql'))

    for migration_file in migration_files:
        # Get relative path from sql folder
        relative_path = migration_file.relative_to(project_root / 'sql')
        print(f"Executing migration: {relative_path}")
        try:
            executor.execute_sql_file(str(relative_path), database_type='test')
            print(f"Migration executed successfully: {relative_path}")
        except Exception as e:
            print(f"X Migration failed: {relative_path}")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            # Continue with other migrations
            continue

if __name__ == "__main__":
    main()
