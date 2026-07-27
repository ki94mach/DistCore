"""Authoritative catalog for the active snapshot pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Type

from .distributor_deliveries import DistributorDeliveriesPipeline
from .distributor_inventory import DistributorInventoryPipeline
from .factory_inventory import FactoryInventoryPipeline
from .sales_snapshot import SalesSnapshotPipeline
from .sql_snapshot_pipeline import SqlSnapshotPipeline
from .target import TargetPipeline


class PipelineKey(str, Enum):
    FACTORY_INVENTORY = "factory_inventory"
    DISTRIBUTOR_INVENTORY = "distributor_inventory"
    SALES = "sales"
    TARGET = "target"
    DISTRIBUTOR_DELIVERIES = "distributor_deliveries"


class BusinessKeyType(str, Enum):
    SNAPSHOT_DATE = "snapshot_date"
    SNAPSHOT_MONTH = "snapshot_month"


@dataclass(frozen=True)
class PipelineDefinition:
    key: PipelineKey
    menu_key: str
    name: str
    pipeline_class: Type[SqlSnapshotPipeline]
    batch_type: str
    snapshot_table: str
    business_key_type: BusinessKeyType
    optional_for_optimize: bool = False


PIPELINE_CATALOG: tuple[PipelineDefinition, ...] = (
    PipelineDefinition(
        PipelineKey.FACTORY_INVENTORY,
        "1",
        "Factory Inventory",
        FactoryInventoryPipeline,
        "FACTORY_INVENTORY",
        "snp_FactoryInventorySnapshot",
        BusinessKeyType.SNAPSHOT_DATE,
    ),
    PipelineDefinition(
        PipelineKey.DISTRIBUTOR_INVENTORY,
        "2",
        "Distributor Inventory",
        DistributorInventoryPipeline,
        "DISTRIBUTOR_INVENTORY",
        "snp_DistributorInventorySnapshot",
        BusinessKeyType.SNAPSHOT_DATE,
    ),
    PipelineDefinition(
        PipelineKey.SALES,
        "3",
        "Sales Snapshot",
        SalesSnapshotPipeline,
        "SALES_SNAPSHOT",
        "snp_SalesSnapshot",
        BusinessKeyType.SNAPSHOT_MONTH,
    ),
    PipelineDefinition(
        PipelineKey.TARGET,
        "4",
        "Target",
        TargetPipeline,
        "TARGET",
        "snp_TargetSnapshot",
        BusinessKeyType.SNAPSHOT_DATE,
    ),
    PipelineDefinition(
        PipelineKey.DISTRIBUTOR_DELIVERIES,
        "5",
        "Distributor Deliveries",
        DistributorDeliveriesPipeline,
        "DISTRIBUTOR_DELIVERIES",
        "snp_DistributorDeliveriesSnapshot",
        BusinessKeyType.SNAPSHOT_DATE,
    ),
)

PIPELINES_BY_KEY = {definition.key: definition for definition in PIPELINE_CATALOG}
PIPELINES_BY_MENU_KEY = {
    definition.menu_key: definition for definition in PIPELINE_CATALOG
}


def get_pipeline_definition(key: PipelineKey) -> PipelineDefinition:
    try:
        return PIPELINES_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"Unknown pipeline: {key}") from exc


__all__ = [
    "BusinessKeyType",
    "PIPELINE_CATALOG",
    "PIPELINES_BY_KEY",
    "PIPELINES_BY_MENU_KEY",
    "PipelineDefinition",
    "PipelineKey",
    "get_pipeline_definition",
]
