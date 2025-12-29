from src.orchestrator.pipelines.base_pipeline import BaseETLPipeline

class FactoryInventoryPipeline(BaseETLPipeline):
    """
    Pipeline for the factory inventory.
    
    This pipeline demonstrates how to use SQL execution methods:
    - execute_procedure: Execute stored procedures
    - execute_procedure_with_output: Execute procedures with output parameters
    - execute_sql_file: Execute SQL files from the sql folder
    """
    
    def load_stage(self):
        """
        Load the data into the stage.
        Example: Execute a stored procedure to load staging data.
        """
        # Option 1: Execute a stored procedure
        self.execute_procedure(
            '[Data].[etl_usp_load_stage_factory_inventory]',
            parameters={'batch_id': self.batch_id}
        )
        
        # Option 2: Execute a SQL file
        # self.execute_sql_file(
        #     '20_etl/factory_inventory/load_stage.sql',
        #     parameters={'batch_id': str(self.batch_id)}
        # )
    
    def validate(self):
        """
        Validate the data in the stage.
        Example: Execute validation stored procedure.
        """
        self.execute_procedure(
            '[Data].[etl_usp_validate_factory_inventory]',
            parameters={'batch_id': self.batch_id, 'allow_negative': 0}
        )
    
    def publish(self):
        """
        Publish the data to the target.
        Example: Execute publication stored procedure.
        """
        self.execute_procedure(
            '[Data].[etl_usp_publish_factory_inventory_snapshot]',
            parameters={
                'batch_id': self.batch_id,
                'snapshot_date': self.snapshot_date
            }
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
            fetch_results=False
        )
    
    def run(self):
        """
        Run the ETL pipeline using the base class implementation.
        Alternatively, you can use the SQL stored procedure that orchestrates everything:
        
        # Option: Use the all-in-one stored procedure
        results = self.execute_procedure(
            '[Data].[etl_usp_run_factory_inventory_pipeline]',
            parameters={
                'snapshot_date': self.snapshot_date,
                'triggered_by': 'PYTHON_PIPELINE',
                'allow_negative': 0
            }
        )
        # If using the stored procedure, you don't need to call super().run()
        """
        # Use the base class implementation which calls load_stage, validate, publish
        super().run()