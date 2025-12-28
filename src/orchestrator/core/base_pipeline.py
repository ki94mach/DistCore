import abc

class BaseETLPipeline(abc.ABC):
    """
    Base class for all ETL pipelines.
    """
    @abc.abstractmethod
    def load_stage(self):
        """
        Load the data into the stage.
        """
        pass
    
    @abc.abstractmethod
    def validate(self):
        """
        Validate the data in the stage.
        """
        pass
    
    @abc.abstractmethod
    def publish(self):
        """
        Publish the data to the target.
        """
        pass
    
    @abc.abstractmethod
    def run(self):
        """
        Run the ETL pipeline.
        """
        pass