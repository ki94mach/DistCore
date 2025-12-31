# src/orchestrator/pipelines/base_pipeline.py

from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

from ..services.sql_server_db.factory import DBConnectionFactory
from ..services.sql_server_db.executors.sql_executor import SQLExecutor


class BaseETLPipeline(ABC):
    """
    Base class for all ETL pipelines.
    Provides SQL execution capabilities for running stored procedures and SQL files.
    """
    def __init__(self, batch_id: int, snapshot_date: date, connection_factory: Optional[DBConnectionFactory] = None):
        self.batch_id = batch_id
        self.snapshot_date = snapshot_date
        self._connection_factory = connection_factory or DBConnectionFactory()
        self._sql_executor = SQLExecutor(self._connection_factory)
        self._in_run_method = False  # Track if we're executing within run() to avoid duplicate error handling
    
    @abstractmethod
    def run(self):
        """
        Run the ETL pipeline.
        """
        self._in_run_method = True
        try:
            self.load_stage()
            self.validate()
            self.publish()
            if self._has_valid_batch_id():
                self.finish_batch(self.batch_id, 'SUCCESS', 'OK')
        except Exception as e:
            if self._has_valid_batch_id():
                self.finish_batch(self.batch_id, 'FAILED', str(e))
            raise e
        finally:
            self._in_run_method = False

    @abstractmethod
    def load_stage(self):
        """
        Load the data into the stage.
        """
        pass
    
    @abstractmethod
    def validate(self):
        """
        Validate the data in the stage.
        """
        pass
    
    @abstractmethod
    def publish(self):
        """
        Publish the data to the target.
        """
        pass

    @abstractmethod
    def finish_batch(self, batch_id: int, status: str, message: str):
        """
        Finish the batch.
        """
        pass

    def _has_valid_batch_id(self) -> bool:
        return self.batch_id not in (None, 0)
    
    @contextmanager
    def _handle_batch_failure(self, error_message_prefix: str = ""):
        """
        Context manager to automatically mark batch as FAILED if an exception occurs.
        
        This should be used in ETL step methods (load_stage, validate, publish) 
        when they might be called directly (not through run()).
        
        If the method is called through run(), the base class will handle errors,
        so this context manager will skip calling finish_batch to avoid duplicate calls.
        
        Args:
            error_message_prefix: Optional prefix to add to error messages
            
        Example:
            def validate(self):
                with self._handle_batch_failure("Validation failed: "):
                    # validation code here
                    self.execute_procedure(...)
        """
        try:
            yield
        except Exception as e:
            # Only mark as failed if:
            # 1. We have a valid batch_id
            # 2. We're NOT in the run() method (to avoid duplicate calls)
            #    (If we're in run(), the base class will handle the error)
            if self._has_valid_batch_id() and not self._in_run_method:
                try:
                    error_msg = f"{error_message_prefix}{str(e)}" if error_message_prefix else str(e)
                    self.finish_batch(self.batch_id, 'FAILED', error_msg)
                except Exception as finish_error:
                    # If finish_batch itself fails, log but don't mask the original error
                    print(f"⚠️  Warning: Could not mark batch as FAILED: {str(finish_error)}")
            # Re-raise the original exception
            raise
    
    def execute_procedure(
        self,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        database_type: str = 'test',
        fetch_results: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a stored procedure.
        
        Args:
            procedure_name: Full procedure name (e.g., '[Data].[etl_usp_run_factory_inventory_pipeline]')
            parameters: Dictionary of parameter names (without @) to values
            database_type: Type of database ('source' or 'test')
            fetch_results: If True, fetch and return result sets
            
        Returns:
            List of dictionaries representing rows, or None
            
        Example:
            results = self.execute_procedure(
                '[Data].[etl_usp_run_factory_inventory_pipeline]',
                parameters={'snapshot_date': self.snapshot_date, 'triggered_by': 'SCHEDULED_JOB'}
            )
        """
        return self._sql_executor.execute_procedure(
            procedure_name=procedure_name,
            parameters=parameters,
            database_type=database_type,
            fetch_results=fetch_results
        )
    
    def execute_procedure_with_output(
        self,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        output_parameters: Optional[List[str]] = None,
        database_type: str = 'test'
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure and capture output parameters.
        
        Args:
            procedure_name: Full procedure name
            parameters: Dictionary of input parameter names to values
            output_parameters: List of output parameter names (without @)
            database_type: Type of database ('source' or 'test')
            
        Returns:
            Dictionary containing output parameter values and any result sets
            
        Example:
            result = self.execute_procedure_with_output(
                '[Data].[ctl_usp_start_batch]',
                parameters={'batch_type': 'FACTORY_INVENTORY', 'triggered_by': 'SCHEDULED_JOB'},
                output_parameters=['batch_id']
            )
            batch_id = result['batch_id']
        """
        return self._sql_executor.execute_procedure_with_output(
            procedure_name=procedure_name,
            parameters=parameters,
            output_parameters=output_parameters,
            database_type=database_type
        )
    
    def execute_sql_file(
        self,
        sql_file_path: Union[str, Path],
        database_type: str = 'test',
        parameters: Optional[Dict[str, str]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a SQL file from the sql folder.
        
        Args:
            sql_file_path: Path to SQL file (relative to sql folder or absolute)
            database_type: Type of database ('source' or 'test')
            parameters: Optional dictionary for parameter substitution
            
        Returns:
            List of dictionaries representing result rows, or None
            
        Example:
            results = self.execute_sql_file(
                '10_routines/procedures/etl_load_stage_factory_inventory.sql',
                parameters={'batch_id': str(self.batch_id)}
            )
        """
        return self._sql_executor.execute_sql_file(
            sql_file_path=sql_file_path,
            database_type=database_type,
            parameters=parameters
        )
