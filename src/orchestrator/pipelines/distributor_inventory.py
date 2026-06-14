from src.orchestrator.pipelines.sql_snapshot_pipeline import SqlSnapshotPipeline


class DistributorInventoryPipeline(SqlSnapshotPipeline):
    """Publish distributor inventory snapshot from DWOrchid.FactInventory."""

    @property
    def batch_type(self) -> str:
        return "DISTRIBUTOR_INVENTORY"

    @property
    def publish_procedure(self) -> str:
        return self._qualify("etl_usp_build_distributor_inventory_snapshot")
