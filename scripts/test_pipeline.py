"""Manual test script for FactoryInventoryPipeline."""

import sys
from pathlib import Path
from datetime import date

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory
from src.orchestrator.services.sql_server_db.executors.sql_executor import SQLExecutor


def start_new_batch(triggered_by: str = 'MANUAL_TEST', database_type: str = 'test') -> int:
    """Start a new batch and return the batch_id."""
    connection_factory = DBConnectionFactory()
    sql_executor = SQLExecutor(connection_factory)
    
    result = sql_executor.execute_procedure_with_output(
        procedure_name='[Data].[ctl_usp_start_batch]',
        parameters={
            'batch_type': 'FACTORY_INVENTORY',
            'triggered_by': triggered_by
        },
        output_parameters=['batch_id'],
        database_type=database_type
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
    print("  - Press Enter to use today's date (recommended for new ETL runs)")
    print("  - Enter a date (YYYY-MM-DD) to use a specific date")
    snapshot_date_str = input("Enter snapshot date (YYYY-MM-DD) or press Enter for today: ").strip()
    if snapshot_date_str:
        year, month, day = map(int, snapshot_date_str.split('-'))
        snapshot_date = date(year, month, day)
    else:
        snapshot_date = None  # Will default to today's date
    
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
            
            # If snapshot_date is None, use today's date for the stored procedure
            if snapshot_date is None:
                from datetime import date as dt_date
                snapshot_date = dt_date.today()
                print(f"\n→ Using today's date as snapshot date: {snapshot_date}")
            
            connection_factory = DBConnectionFactory()
            sql_executor = SQLExecutor(connection_factory)
            
            results = sql_executor.execute_procedure(
                procedure_name='[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]',
                parameters={
                    'snapshot_date': snapshot_date,
                    'triggered_by': 'MANUAL_TEST'
                },
                database_type='test'
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
                batch_id = start_new_batch(triggered_by='MANUAL_TEST', database_type='test')
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
                print(f"  Snapshot Date: Will use today's date")
            print("-" * 60)
            
            # Create pipeline
            pipeline = FactoryInventoryPipeline(
                batch_id=batch_id,
                snapshot_date=snapshot_date,
                triggered_by='MANUAL_TEST',
                database_type='test'
            )
            
            print("\n1. Testing individual stages...")
            
            # Test load_stage
            print("\n   → Loading stage...")
            pipeline.load_stage()
            print("   ✓ Load stage completed")
            
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
        error_msg = str(e)
        print(f"\n❌ Error: {error_msg}")
        
        # Check if it's a procedure not found error
        if "Could not find stored procedure" in error_msg or "2812" in error_msg:
            print("\n" + "=" * 60)
            print("PROCEDURE NOT FOUND")
            print("=" * 60)
            print("The stored procedure has not been deployed to the database yet.")
            print("\nTo fix this, run the deployment script:")
            print("  python scripts/deploy_procedures.py")
            print("\nThis will deploy all stored procedures to the 'test' database.")
            print("If you need to deploy to a different database, use:")
            print("  python scripts/deploy_procedures.py <database_type>")
            print("  (where <database_type> is 'source' or 'test')")
            print("=" * 60)
        
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
