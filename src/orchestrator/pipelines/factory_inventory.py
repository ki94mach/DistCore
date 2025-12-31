from typing import Optional
from datetime import date
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
    
    def load_stage(self):
        """
        Load the data into the stage.
        Extracts data from source server (op-db1-srv) using sql/20_etl/factory_inventory/extract.sql
        and loads into staging table on test server (op-hst-db-srv).
        """
        self._ensure_snapshot_date()
        self._ensure_batch_created()
        
        # Step 1: Extract data from source server using SQL file
        extracted_data = self.execute_sql_file(
            '20_etl/factory_inventory/extract.sql',
            database_type='source'
        )
        
        if not extracted_data:
            # No data to load
            return
        
        # Step 2: Load data into staging table on test server
        # First, delete any existing staging rows for this batch_id (rerun-safe)
        delete_query = "DELETE FROM [Data].[stg_FactoryInventory] WHERE batch_id = ?"
        
        # Then insert the extracted data
        insert_query = """
        INSERT INTO [Data].[stg_FactoryInventory] 
            (batch_id, factory_id, product_id, product_batch_no, as_of_datetime, on_hand_qty)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        
        with self._connection_factory.connection('test') as test_conn:
            test_cursor = test_conn.cursor()
            
            try:
                # Delete existing rows for this batch (rerun-safe)
                test_cursor.execute(delete_query, (self.batch_id,))
                
                # Prepare data for batch insert
                insert_data = [
                    (
                        self.batch_id,
                        row.get('factory_id'),
                        row.get('product_id'),
                        row.get('product_batch_no'),
                        row.get('as_of_datetime'),
                        row.get('on_hand_qty')
                    )
                    for row in extracted_data
                ]
                
                # Insert extracted data using executemany for better performance
                if insert_data:
                    test_cursor.executemany(insert_query, insert_data)
                
                test_conn.commit()
                
            except Exception as e:
                test_conn.rollback()
                raise Exception(f"Failed to load data into staging: {str(e)}") from e
    
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
        # Ensure snapshot_date and batch are created before running
        self._ensure_snapshot_date()
        self._ensure_batch_created()
        # Use the base class implementation which calls load_stage, validate, publish
        super().run()