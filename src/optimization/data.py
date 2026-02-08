"""Input data models for the optimization layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence, Tuple

# Weight Fine Tuning:
@dataclass(frozen=True)
class OptimizationSettings:
    coverage_ratio: float = 1.5
    sales_window: int = 6
    delivery_lower_bound: float = 0.9
    delivery_upper_bound: float = 1.2
    weight_coverage: float = 1.0
    weight_target_units: float = 1.0
    weight_delivery: float = 1.0


@dataclass(frozen=True)
class OptimizationData:
    distributors: Sequence[str]
    products: Sequence[str]
    factory_inventory: Mapping[str, float]
    distributor_inventory: Mapping[Tuple[str, str], float]
    sales_ma_3: Mapping[Tuple[str, str], float]
    sales_ma_6: Mapping[Tuple[str, str], float]
    sales_mtd: Mapping[Tuple[str, str], float]
    target_units: Mapping[str, float]
    settings: OptimizationSettings
    delivery_ma_6: Mapping[Tuple[str, str], float] = field(default_factory=dict)
    has_delivery_last_6m: Mapping[Tuple[str, str], bool] = field(default_factory=dict)
    distributor_names: Mapping[str, str] = field(default_factory=dict)
    product_names: Mapping[str, str] = field(default_factory=dict)

    def inventory(self, distributor: str, product: str) -> float:
        return self.distributor_inventory.get((distributor, product), 0.0)

    def sales_moving_average(self, distributor: str, product: str) -> float:
        if self.settings.sales_window == 3:
            return self.sales_ma_3.get((distributor, product), 0.0)
        return self.sales_ma_6.get((distributor, product), 0.0)

    def sales_month_to_date(self, distributor: str, product: str) -> float:
        return self.sales_mtd.get((distributor, product), 0.0)

    def coverage_demand(self, distributor: str, product: str) -> float:
        demand = self.sales_moving_average(distributor, product) - self.sales_month_to_date(
            distributor, product
        )
        return max(0.0, demand)

    def delivery_moving_average(self, distributor: str, product: str) -> float:
        return self.delivery_ma_6.get((distributor, product), 0.0)

    def has_recent_delivery(self, distributor: str, product: str) -> bool:
        return bool(self.has_delivery_last_6m.get((distributor, product), False))

    def total_sales_mtd(self, product: str) -> float:
        return sum(
            self.sales_month_to_date(distributor, product)
            for distributor in self.distributors
            )

    def remaining_target_units(self, product: str) -> float:
        target = self.target_units.get(product, 0.0)
        return max(0.0, target - self.total_sales_mtd(product))

    def factory_supply(self, product: str) -> float:
        return self.factory_inventory.get(product, 0.0)
        
