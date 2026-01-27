"""
Migrate dimension tables from source server to test server.

This script can:
1. List available dimension tables in the source database
2. Copy table schemas from source to test
3. Copy data from source to test
4. Handle existing tables (skip, truncate, or merge)

Usage:
    # List dimension tables in source
    python scripts/migrate_dimension_tables.py --list

    # Migrate specific tables
    python scripts/migrate_dimension_tables.py --tables Table1 Table2 --schema-only
    python scripts/migrate_dimension_tables.py --tables Table1 Table2 --data-only
    python scripts/migrate_dimension_tables.py --tables Table1 Table2

    # Migrate all tables matching a pattern
    python scripts/migrate_dimension_tables.py --pattern "Dim%" --schema-only

    # Handle existing tables
    python scripts/migrate_dimension_tables.py --tables Table1 --truncate-existing
    python scripts/migrate_dimension_tables.py --tables Table1 --replace-existing
"""

import sys
import argparse
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory


class DimensionTableMigrator:
    """Migrate dimension tables from source to test database."""

    def __init__(self):
        self.factory = DBConnectionFactory()

    def list_dimension_tables(
        self,
        schema: str = 'Data',
        pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List dimension tables in the source database.

        Args:
            schema: Schema name to search in (default: 'Data')
            pattern: Optional LIKE pattern to filter table names (e.g., 'Dim%')

        Returns:
            List of dictionaries with table information
        """
        query = """
            SELECT 
                TABLE_SCHEMA,
                TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = ?
              AND TABLE_TYPE = 'BASE TABLE'
        """
        
        if pattern:
            query += " AND TABLE_NAME LIKE ?"

        tables = []
        try:
            with self.factory.connection('source') as conn:
                cursor = conn.cursor()
                
                if pattern:
                    cursor.execute(query, (schema, pattern))
                else:
                    cursor.execute(query, (schema,))
                
                for row in cursor.fetchall():
                    table_schema = row[0]
                    table_name = row[1]
                    
                    # Get row count
                    try:
                        count_cursor = conn.cursor()
                        count_cursor.execute(f"SELECT COUNT(*) FROM [{table_schema}].[{table_name}]")
                        row_count = count_cursor.fetchone()[0]
                        count_cursor.close()
                    except:
                        row_count = None
                    
                    tables.append({
                        'schema': table_schema,
                        'name': table_name,
                        'full_name': f"[{table_schema}].[{table_name}]",
                        'row_count': row_count
                    })
        
        except Exception as e:
            print(f"Error listing tables: {e}")
            raise

        return tables

    def get_table_schema(
        self,
        table_name: str,
        schema: str = 'Data'
    ) -> str:
        """
        Get CREATE TABLE statement for a table.

        Args:
            table_name: Name of the table
            schema: Schema name

        Returns:
            CREATE TABLE statement
        """
        full_table_name = f"[{schema}].[{table_name}]"
        
        query = f"""
            SELECT 
                c.COLUMN_NAME,
                c.DATA_TYPE,
                c.CHARACTER_MAXIMUM_LENGTH,
                c.NUMERIC_PRECISION,
                c.NUMERIC_SCALE,
                c.IS_NULLABLE,
                c.COLUMN_DEFAULT,
                CASE 
                    WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 
                    ELSE 0 
                END AS IS_PRIMARY_KEY,
                CASE 
                    WHEN ic.is_identity = 1 THEN 1 
                    ELSE 0 
                END AS IS_IDENTITY
            FROM INFORMATION_SCHEMA.COLUMNS c
            LEFT JOIN (
                SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
                    ON tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                    AND tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
            ) pk ON c.TABLE_SCHEMA = pk.TABLE_SCHEMA
                AND c.TABLE_NAME = pk.TABLE_NAME
                AND c.COLUMN_NAME = pk.COLUMN_NAME
            LEFT JOIN sys.identity_columns ic
                ON ic.object_id = OBJECT_ID('{full_table_name}')
                AND ic.name = c.COLUMN_NAME
            WHERE c.TABLE_SCHEMA = ?
              AND c.TABLE_NAME = ?
            ORDER BY c.ORDINAL_POSITION
        """

        columns = []
        try:
            with self.factory.connection('source') as conn:
                cursor = conn.cursor()
                cursor.execute(query, (schema, table_name))
                
                for row in cursor.fetchall():
                    col_name = row[0]
                    data_type = row[1]
                    max_length = row[2]
                    precision = row[3]
                    scale = row[4]
                    is_nullable = row[5]
                    default = row[6]
                    is_pk = row[7]
                    is_identity = row[8]

                    # Build column definition
                    col_def = f"[{col_name}] {data_type}"
                    
                    # Add length/precision ONLY where SQL Server supports it
                    dt = data_type.lower()

                    # (MAX) / (n) for string/binary types
                    if dt in ("varchar", "nvarchar", "char", "nchar", "binary", "varbinary"):
                        if max_length == -1:
                            col_def += "(MAX)"
                        elif max_length and max_length > 0:
                            col_def += f"({max_length})"

                    # (precision, scale) only for decimal/numeric
                    elif dt in ("decimal", "numeric"):
                        if precision is not None and scale is not None:
                            col_def += f"({precision},{scale})"

                    # optional: float precision
                    elif dt == "float" and precision:
                        col_def += f"({precision})"


                    # Add identity
                    if is_identity:
                        col_def += " IDENTITY(1,1)"

                    # Add nullable
                    if is_nullable == 'NO':
                        col_def += " NOT NULL"
                    else:
                        col_def += " NULL"

                    # Add default
                    if default:
                        col_def += f" DEFAULT {default}"

                    columns.append({
                        'name': col_name,
                        'definition': col_def,
                        'is_pk': is_pk == 1
                    })

        except Exception as e:
            print(f"Error getting schema for {table_name}: {e}")
            raise

        if not columns:
            raise ValueError(f"Table {full_table_name} not found or has no columns")

        # Build CREATE TABLE statement
        pk_columns = [col['name'] for col in columns if col['is_pk']]
        
        create_sql = f"CREATE TABLE {full_table_name} (\n"
        create_sql += ",\n".join([f"    {col['definition']}" for col in columns])
        
        if pk_columns:
            pk_cols_str = ", ".join([f"[{col}]" for col in pk_columns])
            create_sql += f",\n    CONSTRAINT PK_{table_name} PRIMARY KEY ({pk_cols_str})"
        
        create_sql += "\n);"

        return create_sql

    def table_exists(
        self,
        table_name: str,
        schema: str = 'Data',
        database_type: str = 'test'
    ) -> bool:
        """Check if a table exists in the target database."""
        query = """
            SELECT 1
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = ?
              AND TABLE_NAME = ?
        """
        
        try:
            with self.factory.connection(database_type) as conn:
                cursor = conn.cursor()
                cursor.execute(query, (schema, table_name))
                return cursor.fetchone() is not None
        except:
            return False

    def migrate_table_schema(
        self,
        table_name: str,
        source_schema: str = 'dbo',
        target_schema: str = 'Data',
        if_exists: str = 'skip'
    ) -> bool:
        """
        Migrate table schema from source to test.

        Args:
            table_name: Name of the table
            source_schema: Source schema name
            target_schema: Target schema name
            if_exists: What to do if table exists ('skip', 'drop', 'error')

        Returns:
            True if schema was migrated, False if skipped
        """
        full_table_name = f"[{target_schema}].[{table_name}]"
        
        # Check if table exists
        exists = self.table_exists(table_name, target_schema, 'test')
        
        if exists:
            if if_exists == 'skip':
                print(f"  Table {full_table_name} already exists, skipping schema migration")
                return False
            elif if_exists == 'drop':
                print(f"  Dropping existing table {full_table_name}")
                self._drop_table(table_name, target_schema, 'test')
            elif if_exists == 'error':
                raise ValueError(f"Table {full_table_name} already exists in test database")

        # Get schema from source
        print(f"  Getting schema for {full_table_name} from source...")
        create_sql = self.get_table_schema(table_name, source_schema)
        create_sql = create_sql.replace(
            f"[{source_schema}].[{table_name}]", f'[{target_schema}].[{table_name}]'
            )
        # Create table in test
        print(f"  Creating table {full_table_name} in test...")
        try:
            with self.factory.connection('test') as conn:
                cursor = conn.cursor()
                cursor.execute(create_sql)
                conn.commit()
                print(f"  ✓ Schema migrated successfully")
                return True
        except Exception as e:
            print(f"  ✗ Error creating table: {e}")
            raise
    def _has_identity_column(
            self, table_name: str,
            schema: str,
            database_type: str
            ) -> bool:
        query = f"""
            SELECT TOP 1 1
            FROM sys.identity_columns
            WHERE object_id = OBJECT_ID('[{schema}].[{table_name}]')
        """
        with self.factory.connection(database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return cursor.fetchone() is not None

    def migrate_table_data(
        self,
        table_name: str,
        source_schema: str = 'dbo',
        target_schema: str = 'Data',
        batch_size: int = 10000,
        if_exists: str = 'truncate'
    ) -> int:
        """
        Migrate table data from source to test.

        Args:
            table_name: Name of the table
            schema: Schema name
            batch_size: Number of rows to transfer per batch
            if_exists: What to do if data exists ('truncate', 'merge', 'error')

        Returns:
            Number of rows migrated
        """
        source_full = f"[{source_schema}].[{table_name}]"
        target_full = f"[{target_schema}].[{table_name}]"
        # Check if table has data
        try:
            with self.factory.connection('test') as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {target_full}")
                existing_count = cursor.fetchone()[0]
        except:
            existing_count = 0

        if existing_count > 0:
            if if_exists == 'truncate':
                print(f"  Truncating existing data in {target_full}...")
                with self.factory.connection('test') as conn:
                    cursor = conn.cursor()
                    cursor.execute(f"TRUNCATE TABLE {target_full}")
                    conn.commit()
            elif if_exists == 'merge':
                print(f"  Merging data into {target_full} (existing rows will be updated)...")
                # For merge, we'll use a different approach
                return self._merge_table_data(table_name, target_schema, batch_size)
            elif if_exists == 'error':
                raise ValueError(f"Table {target_full} already has {existing_count} rows in test database")

        # Get column names
        columns = self._get_table_columns(table_name, source_schema, 'source')
        column_list = ", ".join([f"[{col}]" for col in columns])

        # Get row count from source
        with self.factory.connection('source') as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {source_full}")
            total_rows = cursor.fetchone()[0]

        if total_rows == 0:
            print(f"  Source table {source_full} is empty, nothing to migrate")
            return 0

        print(f"  Migrating {total_rows:,} rows from {source_full}...")

        # Get a key column for ordering (prefer primary key, otherwise first column)
        key_column = self._get_key_column_for_ordering(table_name, source_schema, 'source')
        
        # Migrate data in batches
        migrated_rows = 0
        last_key_value = None

        while migrated_rows < total_rows:
            # Read batch from source
            with self.factory.connection('source') as source_conn:
                source_cursor = source_conn.cursor()
                
                if key_column and last_key_value is not None:
                    # Use key-based pagination (more efficient and reliable)
                    query = f"""
                        SELECT TOP ({batch_size}) {column_list}
                        FROM {source_full}
                        WHERE [{key_column}] > ?
                        ORDER BY [{key_column}]
                    """
                    source_cursor.execute(query, (last_key_value,))
                elif key_column:
                    # First batch
                    query = f"""
                        SELECT TOP ({batch_size}) {column_list}
                        FROM {source_full}
                        ORDER BY [{key_column}]
                    """
                    source_cursor.execute(query)
                if not key_column:
                    raise ValueError(
                        f"Table {source_full} has no PK or identity column"
                        "Cannot safely batch copy."
                    )
                
                rows = source_cursor.fetchall()

                if not rows:
                    break

                # Insert batch into test
                placeholders = ", ".join(["?" for _ in columns])
                insert_query = f"""
                INSERT INTO {target_full} ({column_list}) VALUES ({placeholders})
                """

                has_identity = self._has_identity_column(table_name, target_schema, 'test')

                with self.factory.connection('test') as test_conn:
                    test_cursor = test_conn.cursor()
                    if has_identity:
                        test_cursor.execute(f""" 
                                                SET IDENTITY_INSERT {target_full} ON
                                                """)
                    test_cursor.executemany(insert_query, rows)
                    test_conn.commit()
                batch_size_actual = len(rows)
                migrated_rows += batch_size_actual
                
                # Update last key value for next iteration
                if key_column:
                    key_col_index = columns.index(key_column)
                    last_key_value = rows[-1][key_col_index]
                
                if migrated_rows % (batch_size * 10) == 0 or migrated_rows >= total_rows:
                    progress_pct = 100 * migrated_rows // total_rows if total_rows > 0 else 0
                    print(f"    Progress: {migrated_rows:,} / {total_rows:,} rows ({progress_pct}%)")

        print(f"  ✓ Migrated {migrated_rows:,} rows successfully")
        return migrated_rows

    def _get_table_columns(
        self,
        table_name: str,
        schema: str,
        database_type: str
    ) -> List[str]:
        """Get list of column names for a table."""
        query = """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ?
              AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """
        
        with self.factory.connection(database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (schema, table_name))
            return [row[0] for row in cursor.fetchall()]

    def _get_key_column_for_ordering(
        self,
        table_name: str,
        schema: str,
        database_type: str
    ) -> Optional[str]:
        """
        Get a suitable column for ordering (prefer primary key, then identity, then first column).
        Returns None if no suitable column found.
        """
        # Try to get primary key column
        pk_query = """
            SELECT TOP 1 COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = ?
              AND TABLE_NAME = ?
              AND CONSTRAINT_NAME IN (
                  SELECT CONSTRAINT_NAME
                  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                  WHERE CONSTRAINT_TYPE = 'PRIMARY KEY'
                    AND TABLE_SCHEMA = ?
                    AND TABLE_NAME = ?
              )
            ORDER BY ORDINAL_POSITION
        """
        
        with self.factory.connection(database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(pk_query, (schema, table_name, schema, table_name))
            row = cursor.fetchone()
            if row:
                return row[0]
            
            # Try to get identity column
            full_table_name = f"[{schema}].[{table_name}]"
            identity_query = f"""
                SELECT TOP 1 name
                FROM sys.identity_columns
                WHERE object_id = OBJECT_ID('{full_table_name}')
            """
            cursor.execute(identity_query)
            row = cursor.fetchone()
            if row:
                return row[0]
            
            # Fallback to first column
            columns = self._get_table_columns(table_name, schema, database_type)
            if columns:
                return columns[0]
            
            return None

    def _drop_table(
        self,
        table_name: str,
        schema: str,
        database_type: str
    ):
        """Drop a table from the database."""
        full_table_name = f"[{schema}].[{table_name}]"
        with self.factory.connection(database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(f"DROP TABLE {full_table_name}")
            conn.commit()

    def _merge_table_data(
        self,
        table_name: str,
        schema: str,
        batch_size: int
    ) -> int:
        """
        Merge data from source to test (update existing, insert new).
        This is a simplified merge - assumes primary key exists.
        """
        full_table_name = f"[{schema}].[{table_name}]"
        
        # Get primary key columns
        pk_query = """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = ?
              AND TABLE_NAME = ?
              AND CONSTRAINT_NAME IN (
                  SELECT CONSTRAINT_NAME
                  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                  WHERE CONSTRAINT_TYPE = 'PRIMARY KEY'
                    AND TABLE_SCHEMA = ?
                    AND TABLE_NAME = ?
              )
            ORDER BY ORDINAL_POSITION
        """
        
        with self.factory.connection('source') as conn:
            cursor = conn.cursor()
            cursor.execute(pk_query, (schema, table_name, schema, table_name))
            pk_columns = [row[0] for row in cursor.fetchall()]

        if not pk_columns:
            print(f"  Warning: No primary key found, falling back to truncate and insert")
            return self.migrate_table_data(table_name, schema, batch_size, 'truncate')

        # Get all columns
        all_columns = self._get_table_columns(table_name, schema, 'source')
        non_pk_columns = [col for col in all_columns if col not in pk_columns]
        
        # Build MERGE statement
        pk_list = ", ".join([f"[{col}]" for col in pk_columns])
        non_pk_list = ", ".join([f"[{col}]" for col in non_pk_columns])
        all_columns_list = ", ".join([f"[{col}]" for col in all_columns])
        
        pk_match = " AND ".join([f"s.[{col}] = t.[{col}]" for col in pk_columns])
        non_pk_update = ", ".join([f"t.[{col}] = s.[{col}]" for col in non_pk_columns])
        
        # For merge, we need to use a different approach since we can't directly
        # reference source database in MERGE. We'll use a staging approach or
        # copy data in batches and merge.
        # For now, we'll use a simpler approach: copy to temp table then merge
        
        source_table = f"[{schema}].[{table_name}]"
        test_table = f"[{schema}].[{table_name}]"
        temp_table = f"[{schema}].[{table_name}_temp_merge]"
        
        # Get row count from source
        with self.factory.connection('source') as source_conn:
            source_cursor = source_conn.cursor()
            source_cursor.execute(f"SELECT COUNT(*) FROM {source_table}")
            total_rows = source_cursor.fetchone()[0]

        if total_rows == 0:
            print(f"  Source table {source_table} is empty, nothing to merge")
            return 0

        print(f"  Merging {total_rows:,} rows...")
        print(f"  Note: Using simplified merge (truncate and insert)")
        print(f"  For true merge with updates, consider using SQL Server linked servers or SSIS")
        
        # For now, use truncate and insert as merge is complex without linked servers
        return self.migrate_table_data(table_name, schema, batch_size, 'truncate')


def main():
    parser = argparse.ArgumentParser(
        description='Migrate dimension tables from source to test database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List dimension tables in source database'
    )
    
    parser.add_argument(
        '--tables',
        nargs='+',
        help='Specific table names to migrate (without schema prefix)'
    )
    
    parser.add_argument(
        '--pattern',
        help='Pattern to match table names (e.g., "Dim%%")'
    )
    
    parser.add_argument(
        '--source-schema',
        default='dbo',
        help='Source schema name (default: dbo)'
    )
    
    parser.add_argument(
        '--target-schema',
        default='Data',
        help='Target schema name (default: Data)'
    )

    parser.add_argument(
        '--schema-only',
        action='store_true',
        help='Migrate only table schemas, not data'
    )
    
    parser.add_argument(
        '--data-only',
        action='store_true',
        help='Migrate only data, assume schema already exists'
    )
    
    parser.add_argument(
        '--truncate-existing',
        action='store_true',
        help='Truncate existing data before migrating (default: skip)'
    )
    
    parser.add_argument(
        '--replace-existing',
        action='store_true',
        help='Merge data (update existing, insert new)'
    )
    
    parser.add_argument(
        '--drop-existing',
        action='store_true',
        help='Drop existing tables before creating schema'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10000,
        help='Number of rows to transfer per batch (default: 10000)'
    )

    args = parser.parse_args()

    migrator = DimensionTableMigrator()

    # List tables
    if args.list:
        print("Dimension tables in source database:")
        print("-" * 80)
        tables = migrator.list_dimension_tables(
            schema=args.schema,
            pattern=args.pattern
        )
        
        if not tables:
            print("No tables found.")
            return
        
        for table in tables:
            row_count = table['row_count'] if table['row_count'] is not None else '?'
            print(f"  {table['full_name']:<50} {row_count:>15} rows")
        
        print(f"\nTotal: {len(tables)} table(s)")
        return

    # Determine which tables to migrate
    if args.tables:
        tables_to_migrate = [
            {'name': t,
             'source_schema': args.source_schema,
             'schema': args.target_schema}
            for t in args.tables
        ]
    elif args.pattern:
        all_tables = migrator.list_dimension_tables(
            schema=args.source_schema,
            pattern=args.pattern
        )
        tables_to_migrate = [
            {'name': t,
             'source_schema': args.source_schema,
             'schema': args.target_schema}
            for t in all_tables
        ]
    else:
        print("Error: Must specify --tables, --pattern, or --list")
        parser.print_help()
        return

    if not tables_to_migrate:
        print("No tables found to migrate.")
        return

    # Determine behavior for existing tables
    schema_if_exists = 'skip'
    if args.drop_existing:
        schema_if_exists = 'drop'
    
    data_if_exists = 'error'
    if args.truncate_existing:
        data_if_exists = 'truncate'
    elif args.drop_existing:
        data_if_exists = 'merge'

    # Migrate tables
    print(f"Migrating {len(tables_to_migrate)} table(s)...")
    print("=" * 80)

    for table_info in tables_to_migrate:
        table_name = table_info['name']
        schema = table_info['schema']
        full_name = f"[{schema}].[{table_name}]"
        
        print(f"\n[{table_name}]")
        print("-" * 80)

        try:
            # Migrate schema
            if not args.data_only:
                migrator.migrate_table_schema(
                    table_name=table_name,
                    source_schema=args.source_schema,
                    target_schema=args.target_schema,
                    if_exists=schema_if_exists
                )

            # Migrate data
            if not args.schema_only:
                migrator.migrate_table_data(
                    table_name=table_name,
                    source_schema=args.source_schema,
                    target_schema=args.target_schema,
                    batch_size=args.batch_size,
                    if_exists=data_if_exists
                )

            print(f"✓ {full_name} migrated successfully")

        except Exception as e:
            print(f"✗ Error migrating {full_name}: {e}")
            import traceback
            traceback.print_exc()
            continue

    print("\n" + "=" * 80)
    print("Migration complete!")


if __name__ == "__main__":
    main()

