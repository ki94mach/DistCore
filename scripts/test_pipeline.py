"""Manual test script for FactoryInventoryPipeline."""

import sys
from pathlib import Path
from datetime import date

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory
from src.orchestrator.services.sql_server_db.executors.sql_executor import SQLExecutor


def start_new_batch(triggered_by: str = 'MANUAL_TEST') -> int:
    """Start a new batch and return the batch_id."""
    connection_factory = DBConnectionFactory()
    sql_executor = SQLExecutor(connection_factory)
    
    result = sql_executor.execute_procedure_with_output(
        procedure_name='[Data].[ctl_usp_start_batch]',
        parameters={
            'batch_type': 'FACTORY_INVENTORY',
            'triggered_by': triggered_by
        },
        output_parameters=['batch_id']
    )
    
    batch_id = result['batch_id']
    print(f"   ✓ Created new batch ID: {batch_id}")
    return batch_id


def main():
    """Run manual test of the pipeline."""
    print("=" * 60)
    print("Factory Inventory Pipeline Test")
    print("=" * 60)
    
    # Ask user how they want to proceed
    print("\nOptions:")
    print("  1. Create a new batch automatically (recommended for first run)")
    print("  2. Use an existing batch ID")
    print("  3. Use all-in-one stored procedure (automatically creates batch)")
    print("  4. Let pipeline create batch automatically (pass None)")
    
    choice = input("\nSelect option (1/2/3/4, default=1): ").strip() or "1"
    
    # Get snapshot date
    print("\nSnapshot Date:")
    print("  - Press Enter to use latest date from snapshot table (recommended)")
    print("  - Enter a date (YYYY-MM-DD) to use a specific date")
    snapshot_date_str = input("Enter snapshot date (YYYY-MM-DD) or press Enter for latest: ").strip()
    if snapshot_date_str:
        year, month, day = map(int, snapshot_date_str.split('-'))
        snapshot_date = date(year, month, day)
    else:
        snapshot_date = None  # Will be auto-detected from table
    
    try:
        if choice == "3":
            # Use all-in-one stored procedure
            print("\n" + "=" * 60)
            print("Running all-in-one pipeline (creates batch automatically)...")
            print("=" * 60)
            if snapshot_date:
                print(f"  Snapshot Date: {snapshot_date}")
            else:
                print("  Snapshot Date: Will use latest from table")
            print("-" * 60)
            
            # If snapshot_date is None, we need to get it first for the stored procedure
            if snapshot_date is None:
                print("\n→ Detecting latest snapshot date...")
                connection_factory = DBConnectionFactory()
                with connection_factory.connection('source') as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT MAX(snapshot_date) FROM [Data].[cur_FactoryInventorySnapshot]")
                    row = cursor.fetchone()
                    conn.commit()
                    if not row or row[0] is None:
                        print("❌ Error: No snapshot dates found in table. Please provide a snapshot_date.")
                        sys.exit(1)
                    snapshot_date = row[0]
                    if hasattr(snapshot_date, 'date'):
                        snapshot_date = snapshot_date.date()
                    print(f"   ✓ Using latest snapshot date: {snapshot_date}")
            
            connection_factory = DBConnectionFactory()
            sql_executor = SQLExecutor(connection_factory)
            
            results = sql_executor.execute_procedure(
                procedure_name='[Data].[etl_usp_run_factory_inventory_pipeline]',
                parameters={
                    'snapshot_date': snapshot_date,
                    'triggered_by': 'MANUAL_TEST',
                    'allow_negative': 0
                }
            )
            
            if results:
                print("\n✓ Pipeline completed successfully!")
                print(f"  Batch ID: {results[0].get('batch_id', 'N/A')}")
                print(f"  Snapshot Date: {results[0].get('snapshot_date', 'N/A')}")
                print(f"  Status: {results[0].get('status', 'N/A')}")
            else:
                print("\n✓ Pipeline completed successfully!")
            
        else:
            # Get or create batch_id
            if choice == "1":
                print("\n→ Creating new batch...")
                batch_id = start_new_batch(triggered_by='MANUAL_TEST')
            elif choice == "2":
                batch_id = int(input("\nEnter existing batch ID: "))
            else:  # choice == "4"
                print("\n→ Pipeline will create batch automatically...")
                batch_id = None
            
            if batch_id is not None:
                print(f"\nRunning pipeline with:")
                print(f"  Batch ID: {batch_id}")
            else:
                print(f"\nRunning pipeline (batch will be created automatically):")
            if snapshot_date:
                print(f"  Snapshot Date: {snapshot_date}")
            else:
                print(f"  Snapshot Date: Will use latest from table")
            print("-" * 60)
            
            # Create pipeline
            pipeline = FactoryInventoryPipeline(
                batch_id=batch_id,
                snapshot_date=snapshot_date,
                triggered_by='MANUAL_TEST'
            )
            
            print("\n1. Testing individual stages...")
            
            # Test load_stage
            print("\n   → Loading stage...")
            pipeline.load_stage()
            print("   ✓ Load stage completed")
            
            # Test validate
            print("\n   → Validating...")
            pipeline.validate()
            print("   ✓ Validation completed")
            
            # Test publish
            print("\n   → Publishing...")
            pipeline.publish()
            print("   ✓ Publish completed")
            
            print("\n" + "=" * 60)
            print("All stages completed successfully!")
            print("=" * 60)
            
            # Option to run full pipeline
            run_full = input("\nRun full pipeline (y/n)? ").lower() == 'y'
            if run_full:
                print("\n2. Running full pipeline...")
                pipeline.run()
                print("   ✓ Full pipeline completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

