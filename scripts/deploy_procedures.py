"""Deploy stored procedures from sql/10_routines/procedures to the database."""

import sys
from pathlib import Path
from typing import Tuple, List

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory
from src.orchestrator.services.sql_server_db.executors.sql_executor import SQLExecutor


def check_migrations_run(factory: DBConnectionFactory, database_type: str) -> Tuple[bool, List[str]]:
    """Check if required tables exist (indicating migrations have been run)."""
    missing_tables = []
    required_tables = ['ctl_BatchRun', 'ctl_ProcedureCatalog', 'ctl_ProcedureParameter']
    
    try:
        with factory.connection(database_type) as conn:
            cursor = conn.cursor()
            for table_name in required_tables:
                cursor.execute("""
                    SELECT 1 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_SCHEMA = 'Data' 
                      AND TABLE_NAME = ?
                """, table_name)
                if cursor.fetchone() is None:
                    missing_tables.append(table_name)
            
            return (len(missing_tables) == 0, missing_tables)
    except Exception as e:
        return (False, [f"Error checking tables: {str(e)}"])


def main():
    """Deploy all stored procedures from sql/10_routines/procedures."""
    # Allow database type to be specified via command line argument
    database_type = 'test'  # Default to 'test' to match procedure execution defaults
    if len(sys.argv) > 1:
        database_type = sys.argv[1].lower()
        if database_type not in ['source', 'test']:
            print(f"Error: database_type must be 'source' or 'test', got '{database_type}'")
            sys.exit(1)
    
    factory = DBConnectionFactory()
    executor = SQLExecutor(factory)
    
    # Check if migrations have been run
    print("Checking if migrations have been run...")
    migrations_ok, missing_tables = check_migrations_run(factory, database_type)
    if not migrations_ok:
        print("\nWARNING: Required tables are missing!")
        if missing_tables:
            print(f"   Missing tables: {', '.join(missing_tables)}")
        print(f"   Please run migrations on the '{database_type}' database first:")
        print("   python scripts/migrations.py")
        print(f"\n   Note: migrations.py runs on 'test' database by default.")
        print(f"   If you need to deploy to 'source', run migrations on 'source' first.")
        response = input("\nContinue anyway? (y/n): ").strip().lower()
        if response != 'y':
            print("Deployment cancelled.")
            sys.exit(0)
    else:
        print("OK: All required tables exist.\n")

    # Get project root for path resolution
    project_root = Path(__file__).resolve().parent.parent
    
    # Get procedures from routines directory only (stored procedures are now all in 10_routines/procedures)
    routines_dir = project_root / 'sql' / '10_routines' / 'procedures'
    
    # Get all SQL files from routines directory (exclude README files)
    procedure_files = sorted([f for f in routines_dir.glob('*.sql') if not f.name.startswith('README')])
    
    if not procedure_files:
        print("No procedure files found in sql/10_routines/procedures/")
        return
    
    print("=" * 60)
    print("Deploying Stored Procedures")
    print("=" * 60)
    print(f"Database type: {database_type}")
    print(f"Note: Make sure migrations were run on the '{database_type}' database")
    print(f"Found {len(procedure_files)} procedure file(s) to deploy\n")
    
    for procedure_file in procedure_files:
        # Get relative path from sql folder
        relative_path = procedure_file.relative_to(project_root / 'sql')
        print(f"Deploying: {relative_path}")
        
        try:
            # Execute the procedure file
            executor.execute_sql_file(str(relative_path), database_type=database_type)
            print(f"  OK: Successfully deployed: {relative_path}\n")
        except Exception as e:
            print(f"  ERROR: Failed to deploy: {relative_path}")
            print(f"    Error: {e}\n")
            # Continue with other procedures even if one fails
            continue
    
    print("=" * 60)
    print("Procedure deployment completed")
    print("=" * 60)
    print(f"\nNote: Procedures deployed to '{database_type}' database.")


if __name__ == "__main__":
    main()

