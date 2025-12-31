"""Test script to diagnose table creation issues."""

import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory

def test_table_creation():
    """Test creating the ctl_ProcedureCatalog table directly."""
    factory = DBConnectionFactory()
    database_type = 'test'
    
    print("=" * 60)
    print("Testing Table Creation")
    print("=" * 60)
    print(f"Database type: {database_type}\n")
    
    # Test 1: Check if table exists
    print("Test 1: Checking if table exists...")
    try:
        with factory.connection(database_type) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_SCHEMA = 'Data' 
                  AND TABLE_NAME = 'ctl_ProcedureCatalog'
            """)
            result = cursor.fetchone()
            if result:
                print("   ✗ Table already exists!")
                return
            else:
                print("   ✓ Table does not exist (good, we can create it)")
    except Exception as e:
        print(f"   ✗ Error checking table: {e}")
        return
    
    # Test 2: Try creating table with IF OBJECT_ID pattern
    print("\nTest 2: Creating table with IF OBJECT_ID pattern...")
    create_sql = """
    IF OBJECT_ID(N'[Data].[ctl_ProcedureCatalog]', 'U') IS NULL
    BEGIN
        CREATE TABLE [Data].[ctl_ProcedureCatalog] (
            procedure_name NVARCHAR(200) NOT NULL CONSTRAINT PK_ProcedureCatalog PRIMARY KEY,
            schema_name NVARCHAR(128) NOT NULL,
            procedure_category NVARCHAR(50) NOT NULL,
            description NVARCHAR(1000) NULL,
            purpose NVARCHAR(MAX) NULL,
            is_enabled BIT NOT NULL CONSTRAINT DF_ProcedureCatalog_is_enabled DEFAULT 1,
            version NVARCHAR(20) NULL,
            created_at DATETIME2 NOT NULL CONSTRAINT DF_ProcedureCatalog_created_at DEFAULT SYSUTCDATETIME(),
            updated_at DATETIME2 NOT NULL CONSTRAINT DF_ProcedureCatalog_updated_at DEFAULT SYSUTCDATETIME(),
            created_by NVARCHAR(100) NULL,
            notes NVARCHAR(MAX) NULL
        );
    END;
    """
    
    try:
        with factory.connection(database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(create_sql)
            conn.commit()
            print("   ✓ Table creation statement executed")
            
            # Verify table was created
            cursor.execute("""
                SELECT 1 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_SCHEMA = 'Data' 
                  AND TABLE_NAME = 'ctl_ProcedureCatalog'
            """)
            result = cursor.fetchone()
            if result:
                print("   ✓ Table successfully created!")
            else:
                print("   ✗ Table creation statement ran but table was not created")
                print("   This suggests the IF condition evaluated to false")
    except Exception as e:
        print(f"   ✗ Error creating table: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Check OBJECT_ID directly
    print("\nTest 3: Checking OBJECT_ID directly...")
    try:
        with factory.connection(database_type) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT OBJECT_ID(N'[Data].[ctl_ProcedureCatalog]', 'U')")
            result = cursor.fetchone()
            obj_id = result[0] if result else None
            print(f"   OBJECT_ID result: {obj_id}")
            if obj_id is None:
                print("   ✓ OBJECT_ID is NULL (table doesn't exist)")
            else:
                print(f"   ✗ OBJECT_ID is {obj_id} (table might exist with different name)")
    except Exception as e:
        print(f"   ✗ Error checking OBJECT_ID: {e}")

if __name__ == "__main__":
    test_table_creation()

