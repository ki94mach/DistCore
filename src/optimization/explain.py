"""Per-row calculation detail for optimization results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from src.optimization.builder import ModelBuildResult
from src.optimization.data import OptimizationData
from src.optimization.solvers.base import Solution


class _ShipmentLike(Protocol):
    product_id: str
    quantity: float

SLACK_TOL = 1e-4
FACTORY_CAP_TOL = 1e-4
_EXPLANATION_JOIN = "؛ "

SHIPMENTS_BASE_COLUMN_NAMES = ("distributor", "product", "quantity")

# Constraint groups for Excel band row and header styling (order matches column layout).
CONSTRAINT_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("result", "Result", SHIPMENTS_BASE_COLUMN_NAMES),
    ("explanation", "Explanation", ("explanation",)),
    (
        "inputs",
        "Inputs",
        (
            "distributor_inventory",
            "sales_ma_3",
            "sales_ma_6",
            "sales_mtd",
            "coverage_demand",
        ),
    ),
    (
        "demand_coverage",
        "Demand coverage",
        (
            "demand_coverage_required",
            "inventory_plus_delivery",
            "demand_coverage_slack",
        ),
    ),
    (
        "target_units",
        "Target units",
        (
            "target_units",
            "remaining_target_units",
            "target_coverage_required",
            "product_inventory_plus_delivery",
            "target_units_slack",
        ),
    ),
    ("delivery_history", "Delivery history", ("has_delivery_last_6m",)),
    (
        "delivery_smoothing",
        "Delivery smoothing",
        (
            "delivery_ma_6",
            "smoothing_lower",
            "smoothing_upper",
            "delivery_low_slack",
            "delivery_high_slack",
        ),
    ),
    (
        "factory_supply",
        "Factory supply",
        (
            "factory_supply",
            "product_total_shipped",
            "factory_supply_remaining",
        ),
    ),
)

CONSTRAINT_GROUP_BY_COLUMN: dict[str, str] = {
    column: group_id
    for group_id, _, columns in CONSTRAINT_GROUPS
    for column in columns
}

CONSTRAINT_GROUP_LABELS: dict[str, str] = {
    group_id: label for group_id, label, _ in CONSTRAINT_GROUPS
}

# Compared sides of each soft constraint (highlighted within the group band).
CONSTRAINT_COMPARISON_COLUMNS: dict[str, frozenset[str]] = {
    "demand_coverage": frozenset(
        {"demand_coverage_required", "inventory_plus_delivery"}
    ),
    "target_units": frozenset(
        {"target_coverage_required", "product_inventory_plus_delivery"}
    ),
}

# Excel header labels (internal column keys unchanged in table rows).
SHIPMENTS_COLUMN_LABELS: dict[str, str] = {
    "explanation": "explanation",
    "distributor_inventory": "distributor_inventory",
    "sales_ma_3": "sales_ma_3",
    "sales_ma_6": "sales_ma_6",
    "sales_mtd": "sales_mtd",
    "coverage_demand": "coverage_demand",
    "demand_coverage_required": "required (inventory+delivery ≥)",
    "inventory_plus_delivery": "inventory+delivery (distributor)",
    "demand_coverage_slack": "slack",
    "target_units": "target_units",
    "remaining_target_units": "remaining_target_units",
    "target_coverage_required": "required (country inventory+delivery ≥)",
    "product_inventory_plus_delivery": "inventory+delivery (country)",
    "target_units_slack": "slack",
    "has_delivery_last_6m": "has_delivery_last_6m",
    "delivery_ma_6": "delivery_ma_6",
    "smoothing_lower": "smoothing_lower",
    "smoothing_upper": "smoothing_upper",
    "delivery_low_slack": "slack (low)",
    "delivery_high_slack": "slack (high)",
    "factory_supply": "factory_supply",
    "product_total_shipped": "product_total_shipped",
    "factory_supply_remaining": "factory_supply_remaining",
}


def shipment_column_label(column_key: str) -> str:
    """Human-readable Shipments sheet header for a column key."""
    return SHIPMENTS_COLUMN_LABELS.get(column_key, column_key)


def constraint_group_for_column(column_key: str) -> str:
    """Return constraint group id for a Shipments column key."""
    return CONSTRAINT_GROUP_BY_COLUMN.get(column_key, "result")

# Detail columns grouped for Excel readability:
# outcome → row inputs → SC1 → SC2 → HC2 → SC5 → HC1
ROW_DETAIL_COLUMN_NAMES = (
    "explanation",
    # Row inputs: on-hand inventory and sales history
    "distributor_inventory",
    "sales_ma_3",
    "sales_ma_6",
    "sales_mtd",
    "coverage_demand",
    # SC1 — distributor demand coverage (inventory_plus_delivery ≥ demand_coverage_required)
    "demand_coverage_required",
    "inventory_plus_delivery",
    "demand_coverage_slack",
    # SC2 — product target units (product_inventory_plus_delivery ≥ target_coverage_required)
    "target_units",
    "remaining_target_units",
    "target_coverage_required",
    "product_inventory_plus_delivery",
    "target_units_slack",
    # HC2 — delivery history gate
    "has_delivery_last_6m",
    # SC5 — delivery smoothing vs historical deliveries
    "delivery_ma_6",
    "smoothing_lower",
    "smoothing_upper",
    "delivery_low_slack",
    "delivery_high_slack",
    # HC1 — factory supply cap (product-level)
    "factory_supply",
    "product_total_shipped",
    "factory_supply_remaining",
)


def shipments_table_column_names(include_detail: bool) -> tuple[str, ...]:
    """Full Shipments sheet column order (base columns plus optional detail)."""
    if not include_detail:
        return SHIPMENTS_BASE_COLUMN_NAMES
    return SHIPMENTS_BASE_COLUMN_NAMES + ROW_DETAIL_COLUMN_NAMES


@dataclass(frozen=True)
class RowDetail:
    """Derived inputs, bounds, slacks, and explanation for one distributor-product row."""

    explanation: str
    distributor_inventory: float
    sales_ma_3: float
    sales_ma_6: float
    sales_mtd: float
    coverage_demand: float
    demand_coverage_required: float
    remaining_target_units: float
    target_units: float
    target_coverage_required: float
    product_inventory_plus_delivery: float
    delivery_ma_6: float
    has_delivery_last_6m: bool
    smoothing_lower: float
    smoothing_upper: float
    inventory_plus_delivery: float
    demand_coverage_slack: float
    delivery_low_slack: float
    delivery_high_slack: float
    target_units_slack: float
    product_total_shipped: float
    factory_supply: float
    factory_supply_remaining: float


def slack_value_by_name(solution: Solution, name: str) -> float:
    """Return a slack variable value by name, or 0.0 if not present in the solution."""
    for variable, value in solution.variable_values.items():
        if variable.name == name:
            return value
    return 0.0


def _round2(value: float) -> float:
    return round(value, 2)


def product_totals_from_shipments(
    shipments: Sequence[_ShipmentLike],
) -> Mapping[str, float]:
    totals: dict[str, float] = {}
    for shipment in shipments:
        totals[shipment.product_id] = totals.get(shipment.product_id, 0.0) + shipment.quantity
    return totals


def effective_smoothing_lower(
    data: OptimizationData,
    distributor_id: str,
    product_id: str,
    coverage_demand: float,
    remaining_target_units: float,
) -> float:
    settings = data.settings
    delivery_ma = data.delivery_moving_average(distributor_id, product_id)
    if coverage_demand > 0 or remaining_target_units > 0:
        return settings.delivery_lower_bound * delivery_ma
    return 0.0


def _inventory_covers_demand_coverage(
    distributor_inventory: float,
    demand_coverage_required: float,
) -> bool:
    return distributor_inventory >= demand_coverage_required - SLACK_TOL


def _inventory_sufficiency_message(
    coverage_demand: float,
    distributor_inventory: float,
    demand_coverage_required: float,
    remaining_target_units: float,
) -> str | None:
    if not _inventory_covers_demand_coverage(
        distributor_inventory, demand_coverage_required
    ):
        return None
    if coverage_demand > SLACK_TOL or demand_coverage_required > SLACK_TOL:
        return "موجودی توزیع‌کننده برای تقاضا کافی است"
    if remaining_target_units > SLACK_TOL:
        return "موجودی توزیع‌کننده برای تقاضا کافی است؛ تارگت در سطح محصول"
    return "موجودی توزیع‌کننده کافی است"


def _already_notes_inventory_sufficiency(messages: Sequence[str]) -> bool:
    return any("موجودی توزیع‌کننده" in message for message in messages)


def _at_factory_cap(
    factory_supply_remaining: float,
    product_total_shipped: float,
) -> bool:
    return (
        abs(factory_supply_remaining) <= FACTORY_CAP_TOL
        and product_total_shipped > 0
    )


def _explain_demand_coverage_slack(
    *,
    quantity: float,
    distributor_inventory: float,
    inventory_plus_delivery: float,
    demand_coverage_required: float,
    demand_coverage_slack: float,
) -> str | None:
    if demand_coverage_slack <= SLACK_TOL:
        return None
    if quantity <= SLACK_TOL and _inventory_covers_demand_coverage(
        distributor_inventory, demand_coverage_required
    ):
        return "تحویل ۰ — موجودی توزیع‌کننده برای تقاضا کافی است؛ کسری SC1"
    return "کسری SC1: موجودی+تحویل کمتر از موردنیاز"


def _explain_delivery_low_slack(
    *,
    quantity: float,
    has_delivery_last_6m: bool,
    coverage_demand: float,
    distributor_inventory: float,
    demand_coverage_required: float,
    remaining_target_units: float,
    delivery_low_slack: float,
    smoothing_lower: float,
    factory_capped: bool,
) -> str | None:
    if delivery_low_slack <= SLACK_TOL:
        return None

    if quantity <= SLACK_TOL:
        if not has_delivery_last_6m:
            return "کسری SC5 (HC2 فعال)"
        if smoothing_lower <= SLACK_TOL:
            return "کسری SC5 (باند غیرفعال)"
        if coverage_demand <= SLACK_TOL and remaining_target_units > SLACK_TOL:
            if _inventory_covers_demand_coverage(
                distributor_inventory, demand_coverage_required
            ):
                return (
                    "تحویل ۰ — موجودی توزیع‌کننده برای تقاضا کافی است؛ "
                    "کسری SC5 (تارگت محصول)"
                )
        if coverage_demand <= SLACK_TOL and _inventory_covers_demand_coverage(
            distributor_inventory, demand_coverage_required
        ):
            return (
                "تحویل ۰ — موجودی توزیع‌کننده کافی است؛ "
                "کسری SC5 (باند محصول)"
            )
        if factory_capped:
            return "تحویل ۰ — کسری SC5"
        return "تحویل ۰ — کسری SC5 (تقاضا و حد پایین هموارسازی)"

    return "کسری SC5: تحویل کمتر از حد پایین هموارسازی"


def _explain_delivery_high_slack(
    *,
    quantity: float,
    delivery_high_slack: float,
    smoothing_upper: float,
) -> str | None:
    if delivery_high_slack <= SLACK_TOL:
        return None
    if quantity <= SLACK_TOL:
        return "کسری SC5 بالا (تحویل ۰، بالای حد هموارسازی)"
    return "کسری SC5 بالا: تحویل بیشتر از حد بالای هموارسازی"


def build_explanation(
    *,
    quantity: float,
    has_delivery_last_6m: bool,
    coverage_demand: float,
    distributor_inventory: float,
    inventory_plus_delivery: float,
    demand_coverage_required: float,
    demand_coverage_slack: float,
    target_units_slack: float,
    remaining_target_units: float,
    target_coverage_required: float,
    delivery_low_slack: float,
    delivery_high_slack: float,
    smoothing_lower: float,
    smoothing_upper: float,
    factory_supply_remaining: float,
    product_total_shipped: float,
    factory_supply: float,
) -> str:
    phrases: list[str] = []
    slack_phrases: list[str] = []
    at_cap = _at_factory_cap(factory_supply_remaining, product_total_shipped)
    inventory_note = _inventory_sufficiency_message(
        coverage_demand,
        distributor_inventory,
        demand_coverage_required,
        remaining_target_units,
    )

    if not has_delivery_last_6m:
        phrases.append("مسدود (HC2): بدون تحویل در ۶ ماه گذشته")

    demand_msg = _explain_demand_coverage_slack(
        quantity=quantity,
        distributor_inventory=distributor_inventory,
        inventory_plus_delivery=inventory_plus_delivery,
        demand_coverage_required=demand_coverage_required,
        demand_coverage_slack=demand_coverage_slack,
    )
    if demand_msg is not None:
        slack_phrases.append(demand_msg)

    if target_units_slack > SLACK_TOL:
        slack_phrases.append(
            "کسری SC2: پوشش کشور کمتر از پوشش تارگت موردنیاز"
        )

    low_msg = _explain_delivery_low_slack(
        quantity=quantity,
        has_delivery_last_6m=has_delivery_last_6m,
        coverage_demand=coverage_demand,
        distributor_inventory=distributor_inventory,
        demand_coverage_required=demand_coverage_required,
        remaining_target_units=remaining_target_units,
        delivery_low_slack=delivery_low_slack,
        smoothing_lower=smoothing_lower,
        factory_capped=at_cap,
    )
    if low_msg is not None:
        slack_phrases.append(low_msg)

    high_msg = _explain_delivery_high_slack(
        quantity=quantity,
        delivery_high_slack=delivery_high_slack,
        smoothing_upper=smoothing_upper,
    )
    if high_msg is not None:
        slack_phrases.append(high_msg)

    if at_cap and slack_phrases:
        phrases.append("مانده موجودی کارخانه تمام شده (HC1)")
    if (
        inventory_note
        and quantity <= SLACK_TOL
        and has_delivery_last_6m
        and slack_phrases
        and not _already_notes_inventory_sufficiency(slack_phrases)
    ):
        phrases.append(inventory_note)
    phrases.extend(slack_phrases)

    if at_cap and not slack_phrases:
        phrases.append("مانده موجودی کارخانه تمام شده (HC1)")

    if quantity > 0 and not slack_phrases:
        if inventory_note:
            phrases.append(
                "تحویل بهینه — موجودی توزیع‌کننده برای تقاضا کافی بود"
            )
        else:
            phrases.append("تحویل بهینه — بدون کسری نرم")

    if not phrases and quantity == 0 and has_delivery_last_6m:
        if inventory_note:
            phrases.append(f"تحویل ۰ — {inventory_note}")
        else:
            phrases.append("تحویل ۰")

    return _EXPLANATION_JOIN.join(phrases)


def build_row_detail(
    distributor_id: str,
    product_id: str,
    quantity: float,
    data: OptimizationData,
    build_result: ModelBuildResult,
    solution: Solution,
    product_totals: Mapping[str, float],
) -> RowDetail:
    """Build calculation detail for one distributor-product row."""
    settings = data.settings
    inventory = data.inventory(distributor_id, product_id)
    coverage_demand = data.coverage_demand(distributor_id, product_id)
    remaining_target_units = data.remaining_target_units(product_id)
    delivery_ma = data.delivery_moving_average(distributor_id, product_id)
    has_delivery_last_6m = data.has_recent_delivery(distributor_id, product_id)
    factory_supply = data.factory_supply(product_id)
    product_total_shipped = product_totals.get(product_id, 0.0)

    smoothing_lower = effective_smoothing_lower(
        data,
        distributor_id,
        product_id,
        coverage_demand,
        remaining_target_units,
    )
    smoothing_upper = settings.delivery_upper_bound * delivery_ma

    demand_coverage_slack = slack_value_by_name(
        solution, f"s_demand_coverage_{distributor_id}_{product_id}"
    )
    delivery_low_slack = slack_value_by_name(
        solution, f"s_delivery_low_{distributor_id}_{product_id}"
    )
    delivery_high_slack = slack_value_by_name(
        solution, f"s_delivery_high_{distributor_id}_{product_id}"
    )
    target_units_slack = slack_value_by_name(solution, f"s_units_{product_id}")

    # build_result is part of the public API for future constraint introspection
    _ = build_result

    factory_supply_remaining = factory_supply - product_total_shipped
    inventory_plus_delivery = inventory + quantity
    demand_coverage_required = settings.coverage_ratio * coverage_demand
    product_total_inventory = data.total_distributor_inventory(product_id)
    product_inventory_plus_delivery = product_total_inventory + product_total_shipped
    target_coverage_required = settings.target_coverage_ratio * remaining_target_units

    explanation = build_explanation(
        quantity=quantity,
        has_delivery_last_6m=has_delivery_last_6m,
        coverage_demand=coverage_demand,
        distributor_inventory=inventory,
        inventory_plus_delivery=inventory_plus_delivery,
        demand_coverage_required=demand_coverage_required,
        demand_coverage_slack=demand_coverage_slack,
        target_units_slack=target_units_slack,
        remaining_target_units=remaining_target_units,
        target_coverage_required=target_coverage_required,
        delivery_low_slack=delivery_low_slack,
        delivery_high_slack=delivery_high_slack,
        smoothing_lower=smoothing_lower,
        smoothing_upper=smoothing_upper,
        factory_supply_remaining=factory_supply_remaining,
        product_total_shipped=product_total_shipped,
        factory_supply=factory_supply,
    )

    return RowDetail(
        explanation=explanation,
        distributor_inventory=_round2(inventory),
        sales_ma_3=_round2(data.sales_ma_3.get((distributor_id, product_id), 0.0)),
        sales_ma_6=_round2(data.sales_ma_6.get((distributor_id, product_id), 0.0)),
        sales_mtd=_round2(data.sales_mtd.get((distributor_id, product_id), 0.0)),
        coverage_demand=_round2(coverage_demand),
        demand_coverage_required=_round2(demand_coverage_required),
        remaining_target_units=_round2(remaining_target_units),
        target_units=_round2(data.target_units.get(product_id, 0.0)),
        target_coverage_required=_round2(target_coverage_required),
        product_inventory_plus_delivery=_round2(product_inventory_plus_delivery),
        delivery_ma_6=_round2(delivery_ma),
        has_delivery_last_6m=has_delivery_last_6m,
        smoothing_lower=_round2(smoothing_lower),
        smoothing_upper=_round2(smoothing_upper),
        inventory_plus_delivery=_round2(inventory_plus_delivery),
        demand_coverage_slack=_round2(demand_coverage_slack),
        delivery_low_slack=_round2(delivery_low_slack),
        delivery_high_slack=_round2(delivery_high_slack),
        target_units_slack=_round2(target_units_slack),
        product_total_shipped=_round2(product_total_shipped),
        factory_supply=_round2(factory_supply),
        factory_supply_remaining=_round2(factory_supply_remaining),
    )


def row_detail_as_dict(detail: RowDetail) -> dict[str, object]:
    """Convert RowDetail to a table row fragment in canonical column order."""
    values: dict[str, object] = {
        "explanation": detail.explanation,
        "distributor_inventory": detail.distributor_inventory,
        "sales_ma_3": detail.sales_ma_3,
        "sales_ma_6": detail.sales_ma_6,
        "sales_mtd": detail.sales_mtd,
        "coverage_demand": detail.coverage_demand,
        "demand_coverage_required": detail.demand_coverage_required,
        "inventory_plus_delivery": detail.inventory_plus_delivery,
        "demand_coverage_slack": detail.demand_coverage_slack,
        "target_units": detail.target_units,
        "remaining_target_units": detail.remaining_target_units,
        "target_coverage_required": detail.target_coverage_required,
        "product_inventory_plus_delivery": detail.product_inventory_plus_delivery,
        "target_units_slack": detail.target_units_slack,
        "has_delivery_last_6m": detail.has_delivery_last_6m,
        "delivery_ma_6": detail.delivery_ma_6,
        "smoothing_lower": detail.smoothing_lower,
        "smoothing_upper": detail.smoothing_upper,
        "delivery_low_slack": detail.delivery_low_slack,
        "delivery_high_slack": detail.delivery_high_slack,
        "factory_supply": detail.factory_supply,
        "product_total_shipped": detail.product_total_shipped,
        "factory_supply_remaining": detail.factory_supply_remaining,
    }
    return {name: values[name] for name in ROW_DETAIL_COLUMN_NAMES}


__all__ = [
    "RowDetail",
    "CONSTRAINT_COMPARISON_COLUMNS",
    "CONSTRAINT_GROUP_BY_COLUMN",
    "CONSTRAINT_GROUP_LABELS",
    "CONSTRAINT_GROUPS",
    "ROW_DETAIL_COLUMN_NAMES",
    "SHIPMENTS_BASE_COLUMN_NAMES",
    "SHIPMENTS_COLUMN_LABELS",
    "build_explanation",
    "build_row_detail",
    "constraint_group_for_column",
    "product_totals_from_shipments",
    "row_detail_as_dict",
    "shipment_column_label",
    "shipments_table_column_names",
    "slack_value_by_name",
]
