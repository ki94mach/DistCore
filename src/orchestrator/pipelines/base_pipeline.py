# src/orchestrator/pipelines/base_pipeline.py

from abc import ABC, abstractmethod
from datetime import date
class BaseETLPipeline(ABC):
    """
    Base class for all ETL pipelines.
    """
    def __init__(self, batch_id: int, snapshot_date: date):
        self.batch_id = batch_id
        self.snapshot_date = snapshot_date
    
    @abstractmethod
    def run(self):
        """
        Run the ETL pipeline.
        """
        try:
            self.load_stage()
            self.validate()
            self.publish()
            self.finish_batch(self.batch_id, 'SUCCESS')
        except Exception as e:
            self.finish_batch(self.batch_id, 'FAILED', str(e))
            raise e

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