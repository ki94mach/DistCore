from src.orchestrator.pipelines.sql_snapshot_pipeline import SqlSnapshotPipeline


class FactoryInventoryPipeline(SqlSnapshotPipeline):
    """Publish factory inventory snapshot from DWOrchid.FactInventory."""

    @property
    def batch_type(self) -> str:
        return "FACTORY_INVENTORY"

    @property
    def publish_procedure(self) -> str:
        return self._qualify("etl_usp_build_factory_inventory_snapshot")
