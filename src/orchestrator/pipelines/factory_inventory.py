import signal
import sys
from typing import Optional
from datetime import date, timedelta
from src.orchestrator.pipelines.base_pipeline import BaseETLPipeline

class FactoryInventoryPipeline(BaseETLPipeline):
    """
    Pipeline for the factory inventory.
    
    This pipeline demonstrates how to use SQL execution methods:
    - execute_procedure: Execute stored procedures
    - execute_procedure_with_output: Execute procedures with output parameters
    - execute_sql_file: Execute SQL files from the sql folder
    
    If batch_id is None, a new batch will be automatically created when run() is called.
    If snapshot_date is None, today's date will be used as the snapshot date.
    """
    
    def __init__(self, batch_id: Optional[int], snapshot_date: Optional[date] = None, connection_factory=None, triggered_by: str = 'PYTHON_PIPELINE', database_type: str = 'test'):
        """
        Initialize the pipeline.
        
        Args:
            batch_id: Batch ID to use. If None, a new batch will be created automatically.
            snapshot_date: Date for the snapshot (as-of date for inventory levels). 
                          If None, today's date will be used.
            connection_factory: Optional DBConnectionFactory instance
            triggered_by: Identifier for who/what triggered this pipeline (used when creating new batch)
            database_type: Type of database to use ('source' or 'test'). Defaults to 'test'.
        """
        # If batch_id is None, we'll create it in run() method
        # For now, we need to provide a placeholder to satisfy BaseETLPipeline
        self._batch_id = batch_id
        self._snapshot_date = snapshot_date
        self._triggered_by = triggered_by
        self._database_type = database_type
        self._batch_created = False
        self._snapshot_date_detected = False
        self._interrupted = False
        
        # Register signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        if sys.platform != 'win32':
            signal.signal(signal.SIGTERM, self._signal_handler)
        
        # If snapshot_date is None, we'll use today's date, but need a placeholder for BaseETLPipeline
        # Use today's date as placeholder - will be set properly when needed
        placeholder_date = snapshot_date if snapshot_date is not None else date.today()
        
        # BaseETLPipeline requires batch_id, so we use a placeholder if None
        super().__init__(
            batch_id=batch_id if batch_id is not None else 0,
            snapshot_date=placeholder_date,
            connection_factory=connection_factory
        )
    
    def _ensure_snapshot_date(self):
        """Ensure snapshot_date is set, using today's date if not provided."""
        if self._snapshot_date_detected:
            return
        
        if self._snapshot_date is None:
            # Use today's date as the snapshot date (as-of date for inventory)
            today = date.today()
            self._snapshot_date = today
            # Update the base class's snapshot_date attribute
            object.__setattr__(self, 'snapshot_date', today)
            self._snapshot_date_detected = True
    
    def _ensure_batch_created(self):
        """Ensure batch is created if it wasn't provided."""
        # If batch was already created or we have a valid batch_id, return
        if self._batch_created:
            return
        
        # Check if we need to create a batch (either _batch_id is None/0 or base class batch_id is 0)
        if (self._batch_id is None or self._batch_id == 0) or (hasattr(self, 'batch_id') and self.batch_id == 0):
            result = self.execute_procedure_with_output(
                '[Data].[ctl_usp_start_batch]',
                parameters={
                    'batch_type': 'FACTORY_INVENTORY',
                    'triggered_by': self._triggered_by
                },
                output_parameters=['batch_id'],
                database_type=self._database_type
            )
            
            self._batch_id = result['batch_id']
            # Update the base class's batch_id attribute
            object.__setattr__(self, 'batch_id', self._batch_id)
            self._batch_created = True
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals (Ctrl+C) gracefully."""
        print("\n\n⚠️  Interrupt signal received. Cleaning up...")
        self._interrupted = True
        
        # Mark batch as FAILED if it was created
        if self._batch_created and self._batch_id:
            try:
                self.finish_batch(self._batch_id, 'FAILED', 'Process interrupted by user (Ctrl+C)')
                print(f"✓ Batch {self._batch_id} marked as FAILED in database.")
            except Exception as e:
                print(f"⚠️  Warning: Could not update batch status: {str(e)}")
        
        # Re-raise KeyboardInterrupt to exit
        raise KeyboardInterrupt("Process interrupted by user")
    
    def load_stage(self, batch_size: int = 10000, incremental: bool = True):
        """
        Load the data into the stage using batch processing for better performance.
        Extracts data from source server (op-db1-srv) using sql/20_etl/factory_inventory/extract.sql
        and loads into staging table on test server (op-hst-db-srv) in batches.
        
        Args:
            batch_size: Number of rows to process in each batch (default: 10000)
            incremental: If True, only loads data after the latest date in staging table (default: True)
        """
        self._ensure_snapshot_date()
        self._ensure_batch_created()
        
        # Get the latest date from staging table for incremental loading
        since_date = None
        if incremental:
            with self._connection_factory.connection('test') as test_conn:
                test_cursor = test_conn.cursor()
                test_cursor.execute("""
                    SELECT MAX(as_of_datetime) AS latest_date
                    FROM [Data].[stg_FactoryInventory]
                """)
                result = test_cursor.fetchone()
                if result and result[0] is not None:
                    # Add 1 day to get only dates AFTER the latest date (not including it)
                    since_date = result[0] + timedelta(days=1)
                    print(f"Incremental load: Getting data after {result[0]} (starting from {since_date})")
                else:
                    print("No existing data in staging. Performing full load.")
        
        # Read the SQL file content
        from pathlib import Path
        from src.orchestrator.services.sql_server_db.executors.sql_utils import (
            resolve_sql_file_path,
            read_sql_file
        )
        
        # Calculate sql folder path: from factory_inventory.py go up to project root
        # factory_inventory.py -> pipelines -> orchestrator -> src -> project root
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent.parent  # 4 levels up
        sql_folder = project_root / 'sql'
        
        # Fallback if sql folder not found (try one more level up)
        if not sql_folder.exists():
            sql_folder = project_root.parent / 'sql'
        
        sql_path = resolve_sql_file_path('20_etl/factory_inventory/extract.sql', sql_folder)
        extract_query = read_sql_file(sql_path)
        
        # Extract just the SELECT statement, replacing @since with the actual date or NULL
        # This handles the DECLARE and parameter in the SQL file
        lines = extract_query.split('\n')
        select_lines = []
        in_select = False
        for line in lines:
            stripped = line.strip().upper()
            # Skip DECLARE and comments
            if stripped.startswith('DECLARE') or stripped.startswith('--') or stripped.startswith('/*'):
                continue
            if stripped.startswith('SELECT'):
                in_select = True
            if in_select:
                # Replace @since parameter with the actual date or NULL
                if since_date:
                    # Format date for SQL Server: 'YYYY-MM-DD'
                    date_str = since_date.strftime("'%Y-%m-%d'")
                    line = line.replace('@since', date_str)
                else:
                    line = line.replace('@since', 'NULL')
                select_lines.append(line)
        extract_query = '\n'.join(select_lines)
        
        # Step 1: Delete existing staging rows for this batch_id (rerun-safe)
        delete_query = "DELETE FROM [Data].[stg_FactoryInventory] WHERE batch_id = ?"
        
        # Step 2: Insert query
        insert_query = """
        INSERT INTO [Data].[stg_FactoryInventory] 
            (batch_id, factory_id, product_id, product_batch_no, as_of_datetime, on_hand_qty)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        
        # Open test connection first to delete existing rows
        with self._connection_factory.connection('test') as test_conn:
            test_cursor = test_conn.cursor()
            test_cursor.execute(delete_query, (self.batch_id,))
            test_conn.commit()
        
        # Step 3: Extract and load in batches from source to test
        total_rows = 0
        batch_count = 0
        
        try:
            with self._connection_factory.connection('source') as source_conn:
                source_cursor = source_conn.cursor()
                source_cursor.execute(extract_query)
                
                # Process data in batches
                while True:
                    # Check for interruption
                    if self._interrupted:
                        raise KeyboardInterrupt("Process interrupted by user")
                    
                    # Fetch a batch of rows
                    rows = source_cursor.fetchmany(batch_size)
                    if not rows:
                        break
                    
                    # Get column names from cursor description
                    columns = [column[0] for column in source_cursor.description]
                    
                    # Prepare batch data for insertion
                    batch_data = []
                    for row in rows:
                        row_dict = dict(zip(columns, row))
                        batch_data.append((
                            self.batch_id,
                            row_dict.get('factory_id'),
                            row_dict.get('product_id'),
                            row_dict.get('product_batch_no'),
                            row_dict.get('as_of_datetime'),
                            row_dict.get('on_hand_qty')
                        ))
                    
                    # Insert batch into test server
                    with self._connection_factory.connection('test') as test_conn:
                        test_cursor = test_conn.cursor()
                        try:
                            test_cursor.executemany(insert_query, batch_data)
                            test_conn.commit()
                            
                            total_rows += len(batch_data)
                            batch_count += 1
                            
                            # Progress feedback
                            if batch_count % 10 == 0 or len(batch_data) < batch_size:
                                print(f"Loaded {total_rows:,} rows in {batch_count} batches...")
                                
                        except Exception as e:
                            test_conn.rollback()
                            raise Exception(f"Failed to load batch {batch_count + 1} into staging: {str(e)}") from e
            
            print(f"Completed loading {total_rows:,} rows into staging.")
            
        except KeyboardInterrupt:
            print(f"\n⚠️  Loading interrupted. Loaded {total_rows:,} rows in {batch_count} batches before interruption.")
            # Clean up: delete partial staging data for this batch
            try:
                with self._connection_factory.connection('test') as test_conn:
                    test_cursor = test_conn.cursor()
                    test_cursor.execute(delete_query, (self.batch_id,))
                    test_conn.commit()
                    print(f"✓ Cleaned up partial staging data for batch {self.batch_id}.")
            except Exception as e:
                print(f"⚠️  Warning: Could not clean up staging data: {str(e)}")
            # Re-raise to trigger batch status update
            raise
    
    def validate(self):
        """
        Validate the data in the stage.
        Example: Execute validation stored procedure.
        """
        self._ensure_snapshot_date()
        self._ensure_batch_created()
        self.execute_procedure(
            '[Data].[etl_usp_validate_factory_inventory]',
            parameters={'batch_id': self.batch_id, 'allow_negative': 0},
            database_type=self._database_type
        )
    
    def publish(self):
        """
        Publish the data to the target.
        Example: Execute publication stored procedure.
        """
        self._ensure_snapshot_date()
        self._ensure_batch_created()
        self.execute_procedure(
            '[Data].[etl_usp_publish_factory_inventory_snapshot]',
            parameters={
                'batch_id': self.batch_id,
                'snapshot_date': self.snapshot_date
            },
            database_type=self._database_type
        )
    
    def finish_batch(self, batch_id: int, status: str, message: str = ''):
        """
        Finish the batch by calling the stored procedure.
        
        Args:
            batch_id: The batch ID
            status: Batch status ('SUCCESS', 'FAILED', etc.)
            message: Optional status message
        """
        self.execute_procedure(
            '[Data].[ctl_usp_finish_batch]',
            parameters={
                'batch_id': batch_id,
                'status': status,
                'message': message
            },
            database_type=self._database_type,
            fetch_results=False
        )
    
    def run(self):
        """
        Run the ETL pipeline using the base class implementation.
        If batch_id was None during initialization, a new batch will be created automatically.
        If snapshot_date was None during initialization, today's date will be used.
        
        Handles KeyboardInterrupt (Ctrl+C) gracefully by marking batch as FAILED.
        
        Alternatively, you can use the SQL stored procedure that orchestrates everything:
        
        # Option: Use the all-in-one stored procedure
        results = self.execute_procedure(
            '[Data].[etl_usp_run_factory_inventory_pipeline]',
            parameters={
                'snapshot_date': self.snapshot_date,
                'triggered_by': self._triggered_by,
                'allow_negative': 0
            }
        )
        # If using the stored procedure, you don't need to call super().run()
        """
        try:
            # Ensure snapshot_date and batch are created before running
            self._ensure_snapshot_date()
            self._ensure_batch_created()
            # Use the base class implementation which calls load_stage, validate, publish
            super().run()
        except KeyboardInterrupt:
            # Handle user interruption
            print("\n⚠️  Pipeline interrupted by user (Ctrl+C)")
            if self._batch_created and self._batch_id:
                try:
                    self.finish_batch(self._batch_id, 'FAILED', 'Process interrupted by user (Ctrl+C)')
                    print(f"✓ Batch {self._batch_id} marked as FAILED in database.")
                except Exception as e:
                    print(f"⚠️  Warning: Could not update batch status: {str(e)}")
            # Re-raise to exit
            raise