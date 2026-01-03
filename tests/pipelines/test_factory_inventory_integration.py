"""Integration tests for FactoryInventoryPipeline (requires database)."""

import unittest
import sys
from pathlib import Path
from datetime import date

# Add project root to Python path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory


class TestFactoryInventoryPipelineIntegration(unittest.TestCase):
    """Integration tests that require actual database connection."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test class - create factory once."""
        try:
            cls.factory = DBConnectionFactory()
        except Exception as e:
            cls.factory = None
            print(f"Warning: Could not initialize DBConnectionFactory: {e}")
            print("Integration tests will be skipped.")
    
    def setUp(self):
        """Set up test fixtures."""
        if self.factory is None:
            self.skipTest("Database connection not available")
        
        self.snapshot_date = date(2024, 1, 15)
        # Use a test batch ID - adjust based on your test data strategy
        self.batch_id = 999
    
    def test_pipeline_initialization(self):
        """Test that pipeline can be initialized with real factory."""
        pipeline = FactoryInventoryPipeline(
            batch_id=self.batch_id,
            snapshot_date=self.snapshot_date,
            connection_factory=self.factory
        )
        
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.batch_id, self.batch_id)
        self.assertEqual(pipeline.snapshot_date, self.snapshot_date)
    
    @unittest.skip("Uncomment to run full integration test")
    def test_full_pipeline_execution(self):
        """Test full pipeline execution against real database."""
        pipeline = FactoryInventoryPipeline(
            batch_id=self.batch_id,
            snapshot_date=self.snapshot_date,
            connection_factory=self.factory
        )
        
        # Execute pipeline
        try:
            pipeline.run()
            print(f"✓ Pipeline executed successfully. Batch ID: {self.batch_id}")
        except Exception as e:
            self.fail(f"Pipeline execution failed: {e}")
    
    @unittest.skip("Uncomment to test individual stages")
    def test_load_stage_only(self):
        """Test load_stage method only."""
        pipeline = FactoryInventoryPipeline(
            batch_id=self.batch_id,
            snapshot_date=self.snapshot_date,
            connection_factory=self.factory
        )
        
        try:
            pipeline.load_stage()
            print(f"✓ Load stage executed successfully. Batch ID: {self.batch_id}")
        except Exception as e:
            self.fail(f"Load stage failed: {e}")
    
    @unittest.skip("Uncomment to test stored procedure execution")
    def test_execute_all_in_one_procedure(self):
        """Test using the all-in-one stored procedure."""
        pipeline = FactoryInventoryPipeline(
            batch_id=self.batch_id,
            snapshot_date=self.snapshot_date,
            connection_factory=self.factory
        )
        
        results = pipeline.execute_procedure(
            '[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]',
            parameters={
                'snapshot_date': self.snapshot_date,
                'triggered_by': 'PYTHON_TEST'
            }
        )
        
        if results:
            print(f"✓ Procedure executed. Results: {results}")
        
        self.assertIsNotNone(results)


if __name__ == '__main__':
    unittest.main()
