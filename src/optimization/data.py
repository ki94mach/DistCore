"""Input data models for the optimization layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence, Tuple, Union

SalesWindow = Union[Literal[3, 6], Literal["max"]]


def parse_sales_window(value: Any) -> SalesWindow:
    """Normalize sales_window from API/CLI/config input."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"3", "6"}:
            return int(normalized)
        if normalized == "max":
            return "max"
        raise ValueError(f"sales_window must be 3, 6, or max (got {value!r})")
    if value in {3, 6, "max"}:
        return value
    raise ValueError(f"sales_window must be 3, 6, or max (got {value!r})")


def resolve_sales_moving_average(window: SalesWindow, ma3: float, ma6: float) -> float:
    """Pick the sales MA for demand based on sales_window setting."""
    if window == 3:
        return ma3
    if window == 6:
        return ma6
    if window == "max":
        return max(ma3, ma6)
    raise ValueError(f"Unsupported sales_window: {window!r}. Allowed: 3, 6, 'max'")


# Weight Fine Tuning:
@dataclass(frozen=True)
class OptimizationSettings:
    coverage_ratio: float = 1.5  # Distributor coverage ratio (SC1)
    target_coverage_ratio: float = 1.5  # Target units coverage ratio (SC2)
    sales_window: SalesWindow = 3
    delivery_lower_bound: float = 0.9
    delivery_upper_bound: float = 1.2
    weight_demand: float = 1.0
    weight_target_units: float = 2.0
    weight_smoothing: float = 1.0
    weight_shipment: float = 1.0


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
    product_names: Mapping[str, str] = field(default_factory=dict)  # Persian names for CSV
    product_names_en: Mapping[str, str] = field(default_factory=dict)  # English names for terminal

    def inventory(self, distributor: str, product: str) -> float:
        return self.distributor_inventory.get((distributor, product), 0.0)

    def sales_moving_average(self, distributor: str, product: str) -> float:
        key = (distributor, product)
        return resolve_sales_moving_average(
            self.settings.sales_window,
            self.sales_ma_3.get(key, 0.0),
            self.sales_ma_6.get(key, 0.0),
        )

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

    def total_distributor_inventory(self, product: str) -> float:
        return sum(self.inventory(distributor, product) for distributor in self.distributors)

    def remaining_target_units(self, product: str) -> float:
        target = self.target_units.get(product, 0.0)
        return max(0.0, target - self.total_sales_mtd(product))

    def factory_supply(self, product: str) -> float:
        return self.factory_inventory.get(product, 0.0)


class DataWithSettings:
    """
    Wrapper around OptimizationData that overrides .settings and any methods that depend on it.
    Use when the caller wants to force a specific settings instance (e.g. CLI-provided)
    so the optimization layer definitely uses those values.
    """

    __slots__ = ("_data", "settings")

    def __init__(self, data: OptimizationData, settings: OptimizationSettings) -> None:
        self._data = data
        self.settings = settings

    def __getattr__(self, name: str):
        return getattr(self._data, name)

    def sales_moving_average(self, distributor: str, product: str) -> float:
        key = (distributor, product)
        return resolve_sales_moving_average(
            self.settings.sales_window,
            self._data.sales_ma_3.get(key, 0.0),
            self._data.sales_ma_6.get(key, 0.0),
        )

    def coverage_demand(self, distributor: str, product: str) -> float:
        demand = self.sales_moving_average(distributor, product) - self.sales_month_to_date(
            distributor, product
        )
        return max(0.0, demand)

