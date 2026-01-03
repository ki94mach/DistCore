"""Tests for FactoryInventoryPipeline."""

import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import date

# Add project root to Python path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory


class TestFactoryInventoryPipeline(unittest.TestCase):
    """Test cases for FactoryInventoryPipeline."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.batch_id = 123
        self.snapshot_date = date(2024, 1, 15)
        self.connection_factory_mock = Mock(spec=DBConnectionFactory)
        self.pipeline = FactoryInventoryPipeline(
            batch_id=self.batch_id,
            snapshot_date=self.snapshot_date,
            connection_factory=self.connection_factory_mock
        )
    
    def test_init(self):
        """Test pipeline initialization."""
        self.assertEqual(self.pipeline.batch_id, self.batch_id)
        self.assertEqual(self.pipeline.snapshot_date, self.snapshot_date)
        self.assertIsNotNone(self.pipeline._sql_executor)
    
    @patch.object(FactoryInventoryPipeline, 'execute_procedure')
    def test_load_stage(self, mock_execute):
        """Test load_stage method."""
        # Execute
        self.pipeline.load_stage()
        
        # Verify
        mock_execute.assert_called_once_with(
            '[Data].[etl_usp_load_stage_factory_inventory]',
            parameters={'batch_id': self.batch_id}
        )
    
    @patch.object(FactoryInventoryPipeline, 'execute_procedure')
    def test_publish(self, mock_execute):
        """Test publish method."""
        # Execute
        self.pipeline.publish()
        
        # Verify
        mock_execute.assert_called_once_with(
            '[Data].[etl_usp_build_factory_inventory_snapshot]',
            parameters={
                'batch_id': self.batch_id,
                'snapshot_date': self.snapshot_date
            }
        )
    
    @patch.object(FactoryInventoryPipeline, 'execute_procedure')
    def test_finish_batch(self, mock_execute):
        """Test finish_batch method."""
        # Execute
        self.pipeline.finish_batch(
            batch_id=456,
            status='SUCCESS',
            message='Test completed'
        )
        
        # Verify
        mock_execute.assert_called_once_with(
            '[Data].[ctl_usp_finish_batch]',
            parameters={
                'batch_id': 456,
                'status': 'SUCCESS',
                'message': 'Test completed'
            },
            fetch_results=False
        )
    
    @patch.object(FactoryInventoryPipeline, 'load_stage')
    @patch.object(FactoryInventoryPipeline, 'publish')
    @patch.object(FactoryInventoryPipeline, 'finish_batch')
    def test_run_success(self, mock_finish, mock_publish, mock_load):
        """Test run method with successful execution."""
        # Execute
        self.pipeline.run()
        
        # Verify methods called in order
        mock_load.assert_called_once()
        mock_publish.assert_called_once()
        mock_finish.assert_called_once_with(
            self.batch_id,
            'SUCCESS',
            'OK'
        )
    
    @patch.object(FactoryInventoryPipeline, 'load_stage')
    @patch.object(FactoryInventoryPipeline, 'publish')
    @patch.object(FactoryInventoryPipeline, 'finish_batch')
    def test_run_failure(self, mock_finish, mock_publish, mock_load):
        """Test run method with failure."""
        # Setup - simulate failure in publish
        test_error = Exception("Publish failed")
        mock_publish.side_effect = test_error
        
        # Execute and verify exception is raised
        with self.assertRaises(Exception) as context:
            self.pipeline.run()
        
        self.assertEqual(str(context.exception), "Publish failed")
        
        # Verify error handling
        mock_finish.assert_called_once_with(
            self.batch_id,
            'FAILED',
            'Publish failed'
        )


class TestFactoryInventoryPipelineIntegration(unittest.TestCase):
    """Integration tests for FactoryInventoryPipeline (requires database)."""
    
    @unittest.skip("Requires database connection")
    def test_full_pipeline_execution(self):
        """Test full pipeline execution against real database."""
        batch_id = 999
        snapshot_date = date(2024, 1, 15)
        
        # Use real factory (will need valid config)
        factory = DBConnectionFactory()
        pipeline = FactoryInventoryPipeline(
            batch_id=batch_id,
            snapshot_date=snapshot_date,
            connection_factory=factory
        )
        
        # Execute pipeline
        try:
            pipeline.run()
            print(f"Pipeline executed successfully. Batch ID: {batch_id}")
        except Exception as e:
            self.fail(f"Pipeline execution failed: {e}")


if __name__ == '__main__':
    unittest.main()
