import signal
import sys
from typing import Optional, Tuple, List
from datetime import date, timedelta
from pathlib import Path
from src.orchestrator.pipelines.base_pipeline import BaseETLPipeline
from src.orchestrator.pipelines.utils import (
    get_sql_folder_path,
    parse_select_statement,
    substitute_date_parameter,
    apply_date_equality_filter
)
from src.orchestrator.services.sql_server_db.executors.sql_utils import (
    resolve_sql_file_path,
    read_sql_file
)

class DistributorInventoryPipeline(BaseETLPipeline):
    """
    Pipeline for the distributor inventory.
    
    This pipeline demonstrates how to use SQL execution methods:
    - execute_procedure: Execute stored procedures
    - execute_procedure_with_output: Execute procedures with output parameters
    - execute_sql_file: Execute SQL files from the sql folder
    
    If batch_id is None, a new batch will be automatically created when run() is called.
    If snapshot_date is None, today's date will be used as the snapshot date.
    """
    
    def __init__(
        self, 
        batch_id: Optional[int],
        snapshot_date: Optional[date] = None,
        distributor_id: Optional[int] = None,
        center_id: Optional[int] = None,
        connection_factory=None,
        triggered_by: str = 'PYTHON_PIPELINE',
        database_type: str = 'test'
    ):
        """
        Initialize the pipeline.
        
        Args:
            batch_id: Batch ID to use. If None, a new batch will be created automatically.
            snapshot_date: Date for the snapshot (as-of date for inventory levels). 
                          If None, today's date will be used.
            distributor_id: Distributor ID to use. If None, all distributors will be used.
            center_id: Center ID to use. If None, all centers will be used.
            connection_factory: Optional DBConnectionFactory instance
            triggered_by: Identifier for who/what triggered this pipeline (used when creating new batch)
            database_type: Type of database to use ('source' or 'test'). Defaults to 'test'.
        """
        # If batch_id is None, we'll create it in run() method
        # For now, we need to provide a placeholder to satisfy BaseETLPipeline
        self._batch_id = batch_id
        self._snapshot_date = snapshot_date
        self._distributor_id = distributor_id
        self._center_id = center_id
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
            distributor_id=distributor_id,
            center_id=center_id,
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
            object.__setattr__(self, 'distributor_id', self._distributor_id)
            object.__setattr__(self, 'center_id', self._center_id)
            self._snapshot_date_detected = True
    
    def _ensure_batch_created(self):
        """Ensure batch is created if it wasn't provided."""
        # If batch was already created or we have a valid batch_id, return
        if self._batch_created:
            return
        
        # Check if distributor_id and center_id are provided
        if self._distributor_id is None or self._center_id is None:
            raise ValueError("distributor_id and center_id must be provided")
        
        # Check if we need to create a batch (either _batch_id is None/0 or base class batch_id is 0)
        if (self._batch_id is None or self._batch_id == 0) or (hasattr(self, 'batch_id') and self.batch_id == 0):
            result = self.execute_procedure_with_output(
                '[Data].[ctl_usp_start_batch]',
                parameters={
                    'batch_type': 'DISTRIBUTOR_INVENTORY',
                    'distributor_id': self._distributor_id,
                    'center_id': self._center_id,
                    'triggered_by': self._triggered_by
                },
                output_parameters=['batch_id'],
                database_type=self._database_type
            )
            
            self._batch_id = result['batch_id']
            # Update the base class's batch_id attribute
            object.__setattr__(self, 'batch_id', self._batch_id)
            object.__setattr__(self, 'distributor_id', self._distributor_id)
            object.__setattr__(self, 'center_id', self._center_id)
            self._batch_created = True
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals (Ctrl+C) gracefully."""
        self._interrupted = True
        
        # Mark batch as FAILED if it was created
        if self._batch_created and self._batch_id:
            try:
                self.finish_batch(self._batch_id, 'FAILED', 'Process interrupted by user (Ctrl+C)')
            except Exception:
                pass
        
        # Re-raise KeyboardInterrupt to exit
        raise KeyboardInterrupt("Process interrupted by user")
    
    def load_stage(self, batch_size: int = 10000, incremental: bool = True, single_date_only: bool = False):
        """
        Load the data into the stage using batch processing for better performance.
        Extracts data from source server (op-db1-srv) using sql/20_etl/factory_inventory/extract.sql
        and loads into staging table on test server (op-hst-db-srv) in batches.
        
        Args:
            batch_size: Number of rows to process in each batch (default: 10000)
            incremental: If True, only loads data after the latest date in staging table (default: True).
                        Ignored if single_date_only is True.
            single_date_only: If True, loads only records for the snapshot_date (default: False).
                            When True, uses equality filter (FKDate = snapshot_date) instead of range filter.
        
        Note: If called through run(), errors are handled by the base class.
        If called directly, errors are handled by the context manager.
        """
        with self._handle_batch_failure("Load stage failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()
            
            since_date, use_equality_filter = self._determine_date_filter(
                incremental, single_date_only
            )
            
            extract_query = self._build_extract_query(since_date, use_equality_filter)
            self._prepare_staging_table()
            
            try:
                self._extract_and_load_batches(extract_query, batch_size)
            except KeyboardInterrupt:
                self._cleanup_partial_staging_data()
                raise
    
    def _determine_date_filter(self, incremental: bool, single_date_only: bool) -> Tuple[Optional[date], bool]:
        """
        Determine the date filter strategy based on load mode.
        
        Args:
            incremental: Whether to use incremental loading
            single_date_only: Whether to load only snapshot_date
            
        Returns:
            Tuple of (since_date, use_equality_filter)
        """
        if single_date_only:
            return self.snapshot_date, True
        
        if incremental:
            latest_date = self._get_latest_staging_date()
            if latest_date:
                return latest_date + timedelta(days=1), False
        
        return None, False
    
    def _get_latest_staging_date(self) -> Optional[date]:
        """
        Get the latest date from the staging table.
        
        Returns:
            Latest date from staging table, or None if table is empty
        """
        with self._connection_factory.connection('test') as test_conn:
            test_cursor = test_conn.cursor()
            test_cursor.execute("""
                SELECT MAX(as_of_datetime) AS latest_date
                FROM [Data].[stg_DistributorInventory]
            """)
            result = test_cursor.fetchone()
            return result[0] if result and result[0] is not None else None
    
    def _build_extract_query(self, since_date: Optional[date], use_equality_filter: bool) -> str:
        """
        Build the final extract query with date parameters applied.
        
        Args:
            since_date: Date to filter by, or None for full load
            use_equality_filter: Whether to use equality filter (=) instead of range (>=)
            
        Returns:
            Final SQL query ready for execution
        """
        sql_folder = get_sql_folder_path(Path(__file__))
        sql_path = resolve_sql_file_path('20_etl/distributor_inventory/extract.sql', sql_folder)
        query_template = read_sql_file(sql_path)
        
        select_statement = parse_select_statement(query_template)
        query = substitute_date_parameter(select_statement, 'since', since_date)
        
        if use_equality_filter and since_date:
            query = apply_date_equality_filter(query, '[FKDate]', since_date)
        
        return query
    
    def _prepare_staging_table(self) -> None:
        """
        Prepare staging table by deleting existing rows for this batch_id.
        This makes the operation rerun-safe.
        """
        delete_query = "DELETE FROM [Data].[stg_DistributorInventory] WHERE batch_id = ?"
        
        with self._connection_factory.connection('test') as test_conn:
            test_cursor = test_conn.cursor()
            test_cursor.execute(delete_query, (self.batch_id,))
            test_conn.commit()
    
    def _get_staging_insert_query(self) -> str:
        """
        Get the INSERT query for staging table.
        
        Returns:
            INSERT query string
        """
        return """
            INSERT INTO [Data].[stg_DistributorInventory] 
                (batch_id, distributor_id, center_id, product_id, product_batch_no, as_of_datetime, on_hand_qty)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
    
    def _transform_row_to_staging_data(self, row: tuple, columns: List[str]) -> tuple:
        """
        Transform a database row to staging table format.
        
        Args:
            row: Raw row tuple from database
            columns: Column names from cursor description
            
        Returns:
            Tuple of values for staging table insertion
        """
        row_dict = dict(zip(columns, row))
        return (
            self.batch_id,
            row_dict.get('distributor_id'),
            row_dict.get('center_id'),
            row_dict.get('product_id'),
            row_dict.get('product_batch_no'),
            row_dict.get('as_of_datetime'),
            row_dict.get('on_hand_qty')
        )
    
    def _load_batch_to_staging(self, batch_data: List[tuple], insert_query: str, batch_number: int) -> None:
        """
        Load a single batch of data into staging table.
        
        Args:
            batch_data: List of row tuples to insert
            insert_query: INSERT query string
            batch_number: Current batch number (for error messages)
            
        Raises:
            Exception: If batch insertion fails
        """
        with self._connection_factory.connection('test') as test_conn:
            test_cursor = test_conn.cursor()
            try:
                test_cursor.executemany(insert_query, batch_data)
                test_conn.commit()
            except Exception as e:
                test_conn.rollback()
                raise Exception(f"Failed to load batch {batch_number} into staging: {str(e)}") from e
    
    def _extract_and_load_batches(self, extract_query: str, batch_size: int) -> None:
        """
        Extract data from source and load into staging in batches.
        
        Args:
            extract_query: SQL query to extract data from source
            batch_size: Number of rows per batch
        """
        insert_query = self._get_staging_insert_query()
        batch_count = 0
        
        with self._connection_factory.connection('source') as source_conn:
            source_cursor = source_conn.cursor()
            source_cursor.arraysize = batch_size
            source_cursor.execute(extract_query)
            
            columns = [column[0] for column in source_cursor.description]
            
            while True:
                if self._interrupted:
                    raise KeyboardInterrupt("Process interrupted by user")
                
                rows = source_cursor.fetchmany(batch_size)
                if not rows:
                    break
                
                batch_data = [
                    self._transform_row_to_staging_data(row, columns)
                    for row in rows
                ]
                
                batch_count += 1
                self._load_batch_to_staging(batch_data, insert_query, batch_count)
    
    def _cleanup_partial_staging_data(self) -> None:
        """
        Clean up partial staging data for this batch on interruption.
        """
        delete_query = "DELETE FROM [Data].[stg_DistributorInventory] WHERE batch_id = ?"
        
        try:
            with self._connection_factory.connection('test') as test_conn:
                test_cursor = test_conn.cursor()
                test_cursor.execute(delete_query, (self.batch_id,))
                test_conn.commit()
        except Exception:
            pass
    
    def publish(self):
        """
        Publish the data to the target.
        Example: Execute snapshot build stored procedure.
        
        Note: If called through run(), errors are handled by the base class.
        If called directly, errors are handled by the context manager.
        """
        with self._handle_batch_failure("Publish failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()
            self.execute_procedure(
                '[Data].[etl_usp_build_distributor_inventory_snapshot]',
                parameters={
                    'batch_id': self.batch_id,
                    'snapshot_date': self.snapshot_date
                },
                database_type=self._database_type
            )
    
    def finish_batch(self, batch_id: int, status: str, message: str = ''):
        """
        Finish the batch by calling the stored procedure.
        
        The ctl_usp_finish_batch procedure requires that there be no active transaction.
        To ensure this, we use a fresh connection with autocommit=True to avoid any
        transaction state.
        
        Args:
            batch_id: The batch ID
            status: Batch status ('SUCCESS', 'FAILED', etc.)
            message: Optional status message
        """
        # Use a fresh connection (not from pool) with autocommit=True to ensure no active transaction
        # The ctl_usp_finish_batch procedure explicitly checks XACT_STATE() and fails
        # if there's an active transaction. Setting autocommit=True ensures no transaction is started.
        fresh_conn = self._connection_factory.get_connection(
            self._database_type,
            use_pool=False  # Don't use pool to ensure fresh connection with no transaction state
        )
        try:
            # Enable autocommit mode to ensure no transaction is active
            # This is required because ctl_usp_finish_batch checks XACT_STATE() and fails
            # if there's an active transaction
            fresh_conn.autocommit = True
            
            cursor = fresh_conn.cursor()
            exec_sql = "EXEC [Data].[ctl_usp_finish_batch] @batch_id = ?, @distributor_id = ?, @center_id = ?, @status = ?, @message = ?"
            param_values = [batch_id, status, message]
            
            cursor.execute(exec_sql, param_values)
            # No need to commit when autocommit=True, but it's harmless
        finally:
            # Always close the fresh connection
            fresh_conn.close()
    
    def run(self):
        """
        Run the ETL pipeline using the base class implementation.
        If batch_id was None during initialization, a new batch will be created automatically.
        If snapshot_date was None during initialization, today's date will be used.
        
        Handles KeyboardInterrupt (Ctrl+C) gracefully by marking batch as FAILED.
        
        Alternatively, you can use the SQL stored procedure that orchestrates everything:
        
        # Option: Use the all-in-one stored procedure
        results = self.execute_procedure(
            '[Data].[etl_usp_run_distributor_inventory_snapshot_pipeline]',
            parameters={
                'snapshot_date': self.snapshot_date,
                'triggered_by': self._triggered_by
            }
        ) 
        # If using the stored procedure, you don't need to call super().run()
        """
        # Ensure snapshot_date and batch are created before running
        self._ensure_snapshot_date()
        self._ensure_batch_created()
        try:
            # Use the base class implementation which calls load_stage, publish
            super().run()
        except KeyboardInterrupt:
            # Handle user interruption
            if self._batch_created and self._batch_id:
                try:
                    self.finish_batch(self._batch_id, 'FAILED', 'Process interrupted by user (Ctrl+C)')
                except Exception:
                    pass
            # Re-raise to exit
            raise
