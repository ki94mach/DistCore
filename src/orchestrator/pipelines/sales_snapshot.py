from src.orchestrator.pipelines.sql_snapshot_pipeline import SqlSnapshotPipeline


class SalesSnapshotPipeline(SqlSnapshotPipeline):
    """Publish sales snapshot from DWOrchid.Flat_Fact_Sale."""

    @property
    def batch_type(self) -> str:
        return "SALES_SNAPSHOT"

    @property
    def publish_procedure(self) -> str:
        return self._qualify("etl_usp_build_sales_snapshot")
