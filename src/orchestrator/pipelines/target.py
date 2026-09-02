from src.orchestrator.pipelines.sql_snapshot_pipeline import SqlSnapshotPipeline


class TargetPipeline(SqlSnapshotPipeline):
    """Publish target snapshot from Iris_DW Sale.Data0_Target_Dosage."""

    @property
    def batch_type(self) -> str:
        return "TARGET"

    @property
    def publish_procedure(self) -> str:
        return self._qualify("etl_usp_build_target_snapshot")
