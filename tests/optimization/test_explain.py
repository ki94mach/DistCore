"""Tests for per-row optimization calculation detail."""

from __future__ import annotations

import unittest

from src.optimization.builder import ModelBuildResult
from src.optimization.data import OptimizationData, OptimizationSettings
from src.optimization.explain import (
    build_explanation,
    build_row_detail,
    effective_smoothing_lower,
    slack_value_by_name,
)
from src.optimization.lp import Model, Variable
from src.optimization.solvers.base import Solution


def _sample_data(**overrides) -> OptimizationData:
    base = {
        "distributors": ["D1"],
        "products": ["P1"],
        "factory_inventory": {"P1": 100.0},
        "distributor_inventory": {("D1", "P1"): 4.0},
        "sales_ma_3": {("D1", "P1"): 20.0},
        "sales_ma_6": {("D1", "P1"): 18.0},
        "sales_mtd": {("D1", "P1"): 5.0},
        "target_units": {"P1": 50.0},
        "settings": OptimizationSettings(),
        "delivery_ma_6": {("D1", "P1"): 9.0},
        "has_delivery_last_6m": {("D1", "P1"): True},
    }
    base.update(overrides)
    return OptimizationData(**base)


def _empty_build_result() -> ModelBuildResult:
    return ModelBuildResult(model=Model(), decision_variables={})


def _solution_with_slacks(
    slacks: dict[str, float],
    *,
    quantity: float = 7.0,
) -> Solution:
    x_var = Variable("x_D1_P1")
    variable_values = {x_var: quantity}
    for name, value in slacks.items():
        variable_values[Variable(name)] = value
    return Solution(
        status="Optimal",
        objective_value=1.0,
        variable_values=variable_values,
        is_optimal=True,
        solver_name="Test",
    )


def _base_explanation_kwargs(**overrides) -> dict[str, float | bool]:
    defaults: dict[str, float | bool] = {
        "quantity": 7.0,
        "has_delivery_last_6m": True,
        "coverage_demand": 15.0,
        "distributor_inventory": 4.0,
        "inventory_plus_delivery": 11.0,
        "demand_coverage_required": 22.5,
        "demand_coverage_slack": 0.0,
        "target_units_slack": 0.0,
        "remaining_target_units": 45.0,
        "target_coverage_required": 67.5,
        "delivery_low_slack": 0.0,
        "delivery_high_slack": 0.0,
        "smoothing_lower": 8.1,
        "smoothing_upper": 10.8,
        "factory_supply_remaining": 93.0,
        "product_total_shipped": 7.0,
        "factory_supply": 100.0,
    }
    defaults.update(overrides)
    return defaults


class TestExplain(unittest.TestCase):
    def test_slack_value_by_name(self) -> None:
        solution = _solution_with_slacks({"s_demand_coverage_D1_P1": 2.5})
        self.assertEqual(slack_value_by_name(solution, "s_demand_coverage_D1_P1"), 2.5)
        self.assertEqual(slack_value_by_name(solution, "missing"), 0.0)

    def test_effective_smoothing_lower_with_demand(self) -> None:
        data = _sample_data()
        lower = effective_smoothing_lower(data, "D1", "P1", 15.0, 45.0)
        self.assertEqual(lower, 0.9 * 9.0)

    def test_effective_smoothing_lower_without_demand_or_target(self) -> None:
        data = _sample_data()
        lower = effective_smoothing_lower(data, "D1", "P1", 0.0, 0.0)
        self.assertEqual(lower, 0.0)

    def test_build_explanation_blocked(self) -> None:
        text = build_explanation(
            **_base_explanation_kwargs(
                quantity=0.0,
                has_delivery_last_6m=False,
                inventory_plus_delivery=4.0,
                factory_supply_remaining=100.0,
                product_total_shipped=0.0,
            )
        )
        self.assertIn("مسدود (HC2)", text)

    def test_build_explanation_factory_cap_before_slacks(self) -> None:
        text = build_explanation(
            **_base_explanation_kwargs(
                quantity=10.0,
                inventory_plus_delivery=14.0,
                demand_coverage_slack=1.5,
                delivery_low_slack=0.5,
                factory_supply_remaining=0.0,
                product_total_shipped=100.0,
            )
        )
        self.assertLess(
            text.index("مانده موجودی کارخانه تمام شده"),
            text.index("کسری SC1"),
        )
        self.assertIn("کسری SC1: موجودی+تحویل کمتر از موردنیاز", text)
        self.assertIn("کسری SC5: تحویل کمتر از حد پایین هموارسازی", text)

    def test_build_explanation_no_numbers_in_text(self) -> None:
        text = build_explanation(
            **_base_explanation_kwargs(
                quantity=10.0,
                demand_coverage_slack=1.5,
                delivery_low_slack=450.0,
                smoothing_lower=450.0,
                factory_supply_remaining=0.0,
                product_total_shipped=100.0,
            )
        )
        stripped = text
        for label in ("SC1", "SC2", "SC5", "HC1", "HC2"):
            stripped = stripped.replace(label, "")
        for char in stripped:
            if char.isdigit():
                self.fail(f"explanation contains digit: {text}")

    def test_build_explanation_minimized_shipment(self) -> None:
        text = build_explanation(
            **_base_explanation_kwargs(
                quantity=7.0,
                inventory_plus_delivery=22.5,
                demand_coverage_required=22.5,
            )
        )
        self.assertEqual(text, "تحویل بهینه — بدون کسری نرم")

    def test_build_explanation_zero_qty_no_delivery_need_with_smoothing_slack(self) -> None:
        text = build_explanation(
            **_base_explanation_kwargs(
                quantity=0.0,
                coverage_demand=0.0,
                distributor_inventory=500.0,
                inventory_plus_delivery=500.0,
                demand_coverage_required=0.0,
                remaining_target_units=0.0,
                delivery_low_slack=450.0,
                smoothing_lower=450.0,
                product_total_shipped=0.0,
                factory_supply_remaining=100.0,
            )
        )
        self.assertIn("موجودی توزیع‌کننده", text)
        self.assertIn("کسری SC5 (باند محصول)", text)

    def test_build_explanation_zero_qty_target_only_inventory_sufficient(self) -> None:
        text = build_explanation(
            **_base_explanation_kwargs(
                quantity=0.0,
                coverage_demand=0.0,
                distributor_inventory=4.0,
                inventory_plus_delivery=4.0,
                demand_coverage_required=0.0,
                remaining_target_units=45.0,
                delivery_low_slack=450.0,
                smoothing_lower=450.0,
                product_total_shipped=0.0,
                factory_supply_remaining=100.0,
            )
        )
        self.assertIn("موجودی توزیع‌کننده برای تقاضا کافی است", text)
        self.assertIn("کسری SC5 (تارگت محصول)", text)

    def test_build_explanation_zero_quantity_without_shortfall(self) -> None:
        text = build_explanation(
            **_base_explanation_kwargs(
                quantity=0.0,
                coverage_demand=0.0,
                distributor_inventory=50.0,
                inventory_plus_delivery=50.0,
                demand_coverage_required=0.0,
                remaining_target_units=0.0,
                product_total_shipped=0.0,
                factory_supply_remaining=100.0,
            )
        )
        self.assertEqual(text, "تحویل ۰ — موجودی توزیع‌کننده کافی است")

    def test_build_row_detail_derived_fields(self) -> None:
        data = _sample_data()
        solution = _solution_with_slacks(
            {
                "s_demand_coverage_D1_P1": 0.0,
                "s_delivery_low_D1_P1": 0.0,
                "s_delivery_high_D1_P1": 0.0,
                "s_units_P1": 0.0,
            },
            quantity=7.13,
        )
        detail = build_row_detail(
            "D1",
            "P1",
            7.13,
            data,
            _empty_build_result(),
            solution,
            {"P1": 7.13},
        )
        self.assertEqual(detail.coverage_demand, 15.0)
        self.assertEqual(detail.demand_coverage_required, 22.5)
        self.assertEqual(detail.target_coverage_required, 67.5)
        self.assertEqual(detail.product_inventory_plus_delivery, 11.13)
        self.assertEqual(detail.explanation, "تحویل بهینه — بدون کسری نرم")


if __name__ == "__main__":
    unittest.main()
