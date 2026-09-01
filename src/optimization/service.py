"""Non-interactive application service for optimization runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional, Sequence

import pyodbc

from src.optimization.builder import ModelBuilder
from src.optimization.constraints import (
    DeliveryHistoryConstraint,
    DeliverySmoothingConstraint,
    DemandCoverageConstraint,
    FactorySupplyConstraint,
    ProductTargetUnitsConstraint,
    ShipmentMinimizationConstraint,
)
from src.optimization.data import OptimizationData, OptimizationSettings
from src.optimization.explain import (
    build_row_detail,
    product_totals_from_shipments,
    row_detail_as_dict,
    shipments_table_column_names,
)
from src.optimization.errors import (
    DatabaseUnavailableError,
    InvalidRunRequestError,
    MissingSnapshotError,
    SolverUnavailableError,
)
from src.optimization.loader import SnapshotDataLoader
from src.optimization.solvers import (
    get_constraint_preset,
    is_solver_available,
    solve,
)

if TYPE_CHECKING:
    from src.optimization.builder import ModelBuildResult
    from src.optimization.solvers.base import Solution
    from src.orchestrator.services.sql_server_db import SQLExecutor


@dataclass(frozen=True)
class RunRequest:
    """Inputs needed for one optimization run."""

    snapshot_date: date
    solver: str
    settings: Optional[OptimizationSettings] = None
    settings_preset: Optional[str] = None
    solver_options: Optional[Mapping[str, Mapping[str, Any]]] = None
    include_export_variables: bool = False
    snapshot_month: Optional[date] = None


@dataclass(frozen=True)
class Shipment:
    """A shipment decision with stable IDs and display labels."""

    distributor_id: str
    distributor_name: str
    product_id: str
    product_name: str
    product_name_en: str
    quantity: float


@dataclass(frozen=True)
class RunSummary:
    """Aggregates for a completed optimization run."""

    total_shipments: float
    num_distributors: int
    num_products: int
    shipments_by_product: Mapping[str, float]
    shipments_by_distributor: Mapping[str, float]


@dataclass(frozen=True)
class TabularData:
    """Column-oriented metadata and rows ready for CSV or Excel writers."""

    columns: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class RunResult:
    """Structured output from one optimization run."""

    status: str
    objective: Optional[float]
    solver_name: str
    is_optimal: bool
    is_feasible: bool
    shipments: tuple[Shipment, ...]
    summary: RunSummary
    table: TabularData

    def to_dict(self) -> dict[str, Any]:
        """Return the legacy JSON-compatible result shape used by the CLI."""
        return {
            "status": self.status,
            "is_optimal": self.is_optimal,
            "is_feasible": self.is_feasible,
            "objective_value": self.objective,
            "solver_name": self.solver_name,
            "summary": {
                "total_shipments": self.summary.total_shipments,
                "num_distributors": self.summary.num_distributors,
                "num_products": self.summary.num_products,
                "shipments_by_product": dict(self.summary.shipments_by_product),
                "shipments_by_distributor": dict(
                    self.summary.shipments_by_distributor
                ),
            },
            "shipments": [
                {
                    "distributor": shipment.distributor_name,
                    "product": shipment.product_name_en,
                    "quantity": shipment.quantity,
                }
                for shipment in self.shipments
            ],
        }


class OptimizationService:
    """Load, build, solve, and format an optimization run without UI concerns."""

    def __init__(
        self,
        sql_executor: SQLExecutor,
        database_type: str = "prod",
        *,
        loader_factory: Callable[..., SnapshotDataLoader] = SnapshotDataLoader,
        builder_factory: Callable[..., ModelBuilder] = ModelBuilder,
        solve_fn: Callable[..., Solution] = solve,
    ) -> None:
        self._sql_executor = sql_executor
        self._database_type = database_type
        self._loader_factory = loader_factory
        self._builder_factory = builder_factory
        self._solve = solve_fn

    def run(self, request: RunRequest) -> RunResult:
        """Execute one optimization run."""
        settings = self._resolve_settings(request)
        solver_name = request.solver.strip()
        if not solver_name or not is_solver_available(solver_name):
            raise SolverUnavailableError(solver_name or request.solver)

        data = self._load_data(request, settings)
        constraints = self._constraints()
        builder = self._builder_factory(constraints)
        build_result = builder.build(data, settings_override=settings)
        solver_options = (
            {
                name: dict(options)
                for name, options in request.solver_options.items()
            }
            if request.solver_options
            else None
        )

        try:
            solution = self._solve(
                build_result.model,
                build_result.decision_variables,
                method=solver_name,
                data=data,
                solver_options=solver_options,
            )
        except (ImportError, RuntimeError) as exc:
            if not is_solver_available(solver_name):
                raise SolverUnavailableError(solver_name, str(exc)) from exc
            raise

        return self._format_result(
            build_result,
            solution,
            data,
            include_export_variables=request.include_export_variables,
        )

    @staticmethod
    def _resolve_settings(request: RunRequest) -> OptimizationSettings:
        if request.settings is not None and request.settings_preset is not None:
            raise InvalidRunRequestError(
                "Specify either settings or settings_preset, not both"
            )
        if request.settings is not None:
            return request.settings
        if request.settings_preset is None:
            return OptimizationSettings()

        settings = get_constraint_preset(request.settings_preset)
        if settings is None:
            raise InvalidRunRequestError(
                f"Unknown optimization settings preset: {request.settings_preset}"
            )
        return settings

    def _load_data(
        self, request: RunRequest, settings: OptimizationSettings
    ) -> OptimizationData:
        try:
            loader = self._loader_factory(
                sql_executor=self._sql_executor,
                database_type=self._database_type,
            )
            return loader.load_optimization_data(
                snapshot_date=request.snapshot_date,
                snapshot_month=request.snapshot_month,
                settings=settings,
            )
        except ValueError as exc:
            raise MissingSnapshotError(request.snapshot_date, str(exc)) from exc
        except (pyodbc.Error, ConnectionError, TimeoutError, OSError) as exc:
            raise DatabaseUnavailableError(
                f"Could not load optimization data for {request.snapshot_date!s}: {exc}"
            ) from exc

    @staticmethod
    def _constraints() -> Sequence[Any]:
        return (
            FactorySupplyConstraint(),
            DeliveryHistoryConstraint(),
            DeliverySmoothingConstraint(),
            DemandCoverageConstraint(),
            ProductTargetUnitsConstraint(),
            ShipmentMinimizationConstraint(),
        )

    @staticmethod
    def _format_result(
        build_result: ModelBuildResult,
        solution: Solution,
        data: OptimizationData,
        *,
        include_export_variables: bool,
    ) -> RunResult:
        shipments: list[Shipment] = []
        by_product: dict[str, float] = {}
        by_distributor: dict[str, float] = {}
        total_shipments = 0.0

        for (distributor_id, product_id), variable in build_result.decision_variables.items():
            raw_quantity = solution.variable_values.get(variable, 0.0)
            quantity = round(raw_quantity, 2)
            distributor_name = (data.distributor_names or {}).get(
                distributor_id, distributor_id
            )
            product_name = (data.product_names or {}).get(product_id, product_id)
            product_name_en = (data.product_names_en or {}).get(
                product_id, product_id
            )
            shipments.append(
                Shipment(
                    distributor_id=distributor_id,
                    distributor_name=distributor_name,
                    product_id=product_id,
                    product_name=product_name,
                    product_name_en=product_name_en,
                    quantity=quantity,
                )
            )
            total_shipments += raw_quantity
            by_product[product_name_en] = (
                by_product.get(product_name_en, 0.0) + raw_quantity
            )
            by_distributor[distributor_name] = (
                by_distributor.get(distributor_name, 0.0) + raw_quantity
            )

        summary = RunSummary(
            total_shipments=round(total_shipments, 2),
            num_distributors=len(data.distributors),
            num_products=len(data.products),
            shipments_by_product={
                key: round(value, 2) for key, value in by_product.items()
            },
            shipments_by_distributor={
                key: round(value, 2) for key, value in by_distributor.items()
            },
        )
        objective = (
            round(solution.objective_value, 2)
            if solution.objective_value is not None
            else None
        )
        return RunResult(
            status=solution.status,
            objective=objective,
            solver_name=solution.solver_name,
            is_optimal=solution.is_optimal,
            is_feasible=solution.is_feasible,
            shipments=tuple(shipments),
            summary=summary,
            table=OptimizationService._build_table(
                shipments,
                data,
                build_result,
                solution,
                include_export_variables,
            ),
        )

    @staticmethod
    def _build_table(
        shipments: Sequence[Shipment],
        data: OptimizationData,
        build_result: ModelBuildResult,
        solution: Solution,
        include_variables: bool,
    ) -> TabularData:
        columns = list(
            shipments_table_column_names(include_variables)
        )

        product_totals = product_totals_from_shipments(shipments)
        rows: list[dict[str, Any]] = []
        for shipment in sorted(
            shipments, key=lambda item: (item.distributor_id, item.product_id)
        ):
            row: dict[str, Any] = {
                "distributor": shipment.distributor_name,
                "product": shipment.product_name,
                "quantity": shipment.quantity,
            }
            if include_variables:
                detail = build_row_detail(
                    shipment.distributor_id,
                    shipment.product_id,
                    shipment.quantity,
                    data,
                    build_result,
                    solution,
                    product_totals,
                )
                row.update(row_detail_as_dict(detail))
            rows.append(row)
        return TabularData(columns=tuple(columns), rows=tuple(rows))


__all__ = [
    "OptimizationService",
    "RunRequest",
    "RunResult",
    "RunSummary",
    "Shipment",
    "TabularData",
]
