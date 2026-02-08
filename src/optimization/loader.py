"""Data loader for optimization layer from ETL snapshot tables.

This module provides a bridge between the ETL snapshot tables and the optimization
layer by loading and transforming snapshot data into OptimizationData format.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.optimization.data import OptimizationData, OptimizationSettings
from src.orchestrator.pipelines.utils import get_jalali_year

if TYPE_CHECKING:
    from src.orchestrator.services.sql_server_db import SQLExecutor


class SnapshotDataLoader:
    """Loads optimization data from ETL snapshot tables."""

    def __init__(self, sql_executor: SQLExecutor, database_type: str = "test"):
        """
        Initialize the snapshot data loader.

        Args:
            sql_executor: SQLExecutor instance for database queries
            database_type: Database type to query ('source' or 'test')
        """
        self._sql_executor = sql_executor
        self._database_type = database_type

    def load_optimization_data(
        self,
        snapshot_date: date,
        snapshot_month: Optional[date] = None,
        settings: Optional[OptimizationSettings] = None,
    ) -> OptimizationData:
        """
        Load optimization data from snapshot tables for a given snapshot date.

        Args:
            snapshot_date: Date for inventory and target snapshots
            snapshot_month: Month for sales snapshot (defaults to first day of Jalali month from DimDate)
            settings: Optimization settings (defaults to OptimizationSettings())

        Returns:
            OptimizationData instance populated from snapshot tables

        Raises:
            ValueError: If required snapshot data is missing
        """
        if settings is None:
            settings = OptimizationSettings()

        if snapshot_month is None:
            snapshot_month = self._get_sales_snapshot_month(snapshot_date)

        # Load all snapshot data
        factory_inventory = self._load_factory_inventory(snapshot_date)
        distributor_inventory = self._load_distributor_inventory(snapshot_date)
        sales_data = self._load_sales_snapshot(snapshot_month)
        target_data = self._load_target_snapshot(snapshot_date)
        distributor_deliveries = self._load_distributor_deliveries_snapshot(snapshot_date)

        # Extract unique distributors and products
        distributors = self._extract_distributors(
            distributor_inventory,
            sales_data,
            distributor_deliveries,
        )
        products = self._extract_products(
            factory_inventory,
            distributor_inventory,
            sales_data,
            target_data,
            distributor_deliveries,
        )

        # Transform data to OptimizationData format
        factory_inventory_map = {
            str(row["product_id"]): float(row["on_hand_qty"] or 0.0)
            for row in factory_inventory
        }

        distributor_inventory_map = {
            (str(row["distributor_id"]), str(row["product_id"])): float(
                row["on_hand_qty"] or 0.0
            )
            for row in distributor_inventory
        }

        sales_ma_3_map = {
            (str(row["distributor_id"]), str(row["product_id"])): float(
                row["sales_ma_3"] or 0.0
            )
            for row in sales_data
        }

        sales_ma_6_map = {
            (str(row["distributor_id"]), str(row["product_id"])): float(
                row["sales_ma_6"] or 0.0
            )
            for row in sales_data
        }

        sales_mtd_map = {
            (str(row["distributor_id"]), str(row["product_id"])): float(
                row["sales_mtd"] or 0.0
            )
            for row in sales_data
        }

        delivery_ma_6_map = {
            (str(row["distributor_id"]), str(row["product_id"])): float(
                row["delivered_qty_ma_6"] or 0.0
            )
            for row in distributor_deliveries
        }

        has_delivery_last_6m_map = {
            (str(row["distributor_id"]), str(row["product_id"])): bool(
                row["has_delivery_last_6m"] or 0
            )
            for row in distributor_deliveries
        }

        # Aggregate target data by product (sum across year/month combinations)
        target_units_map: Dict[str, float] = {}
        for row in target_data:
            product_id = str(row["product_id"])
            target_qty = float(row["target_quantity"] or 0.0)
            target_units_map[product_id] = target_units_map.get(product_id, 0.0) + target_qty

        # Load dimension names from SQL Server (Analytics_Stage) for output display
        distributor_names = self._load_distributor_names(sorted(distributors))
        product_names = self._load_product_names(sorted(products))

        return OptimizationData(
            distributors=sorted(distributors),
            products=sorted(products),
            factory_inventory=factory_inventory_map,
            distributor_inventory=distributor_inventory_map,
            sales_ma_3=sales_ma_3_map,
            sales_ma_6=sales_ma_6_map,
            sales_mtd=sales_mtd_map,
            target_units=target_units_map,
            settings=settings,
            delivery_ma_6=delivery_ma_6_map,
            has_delivery_last_6m=has_delivery_last_6m_map,
            distributor_names=distributor_names,
            product_names=product_names,
        )

    def _load_factory_inventory(self, snapshot_date: date) -> List[Dict[str, Any]]:
        """Load factory inventory snapshot data."""
        query = """
        SELECT 
            product_id,
            on_hand_qty
        FROM [Data].[snp_FactoryInventorySnapshot]
        WHERE snapshot_date = ?
        """
        return self._execute_parameterized_query(query, (snapshot_date,))

    def _load_distributor_inventory(self, snapshot_date: date) -> List[Dict[str, Any]]:
        """Load distributor inventory snapshot data."""
        query = """
        SELECT 
            distributor_id,
            product_id,
            on_hand_qty
        FROM [Data].[snp_DistributorInventorySnapshot]
        WHERE snapshot_date = ?
        """
        return self._execute_parameterized_query(query, (snapshot_date,))

    def _get_sales_snapshot_month(self, snapshot_date: date) -> date:
        """
        Return the first day of the Jalali month (as a Gregorian date) for the given snapshot_date.
        This must match the value written by [Data].[etl_usp_build_sales_snapshot], which uses
        [Analytics_Stage].[Data].[DimDate] to resolve the month. Using Gregorian month start
        (snapshot_date.replace(day=1)) would query a different key and return no rows.
        """
        query = """
        SELECT TOP (1) month_start.DateID AS snapshot_month
        FROM [Analytics_Stage].[Data].[DimDate] AS d
        INNER JOIN [Analytics_Stage].[Data].[DimDate] AS month_start
            ON month_start.ShamsiDay = 1
           AND TRY_CONVERT(INT, month_start.LongShamsiYearMonth) = TRY_CONVERT(INT, d.LongShamsiYearMonth)
        WHERE d.DateID = ?
        """
        rows = self._execute_parameterized_query(query, (snapshot_date,))
        if not rows or rows[0].get("snapshot_month") is None:
            raise ValueError(
                f"Could not resolve Jalali month start from [Analytics_Stage].[Data].[DimDate] "
                f"for snapshot_date={snapshot_date!s}. Ensure DimDate is populated for this date."
            )
        val = rows[0]["snapshot_month"]
        return val.date() if hasattr(val, "date") else val

    def _load_sales_snapshot(self, snapshot_month: date) -> List[Dict[str, Any]]:
        """Load sales snapshot data."""
        query = """
        SELECT 
            distributor_id,
            product_id,
            sales_mtd,
            sales_ma_3,
            sales_ma_6
        FROM [Data].[snp_SalesSnapshot]
        WHERE snapshot_month = ?
        """
        return self._execute_parameterized_query(query, (snapshot_month,))

    def _load_target_snapshot(self, snapshot_date: date) -> List[Dict[str, Any]]:
        """Load target snapshot data."""
        # Target snapshots use Jalali calendar year; month rows are stored per Jalali month.
        # We filter by snapshot_date and Jalali year, then aggregate across months downstream.
        year = get_jalali_year(snapshot_date)

        query = """
        SELECT 
            product_id,
            target_quantity
        FROM [Data].[snp_TargetSnapshot]
        WHERE snapshot_date = ?
          AND year = ?
        """
        return self._execute_parameterized_query(query, (snapshot_date, year))

    def _load_distributor_deliveries_snapshot(
        self, snapshot_date: date
    ) -> List[Dict[str, Any]]:
        """Load distributor deliveries snapshot data."""
        query = """
        SELECT 
            distributor_id,
            product_id,
            delivered_qty_ma_6,
            has_delivery_last_6m
        FROM [Data].[snp_DistributorDeliveriesSnapshot]
        WHERE snapshot_date = ?
        """
        return self._execute_parameterized_query(query, (snapshot_date,))

    def _execute_parameterized_query(
        self, query: str, parameters: tuple
    ) -> List[Dict[str, Any]]:
        """
        Execute a parameterized SQL query and return results as list of dictionaries.

        Args:
            query: SQL query with ? placeholders for parameters
            parameters: Tuple of parameter values

        Returns:
            List of dictionaries representing result rows
        """
        # Access the connection factory through the SQLExecutor's internal executors
        connection_factory = self._sql_executor._procedure_executor._connection_factory

        with connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(query, parameters)
            columns = [column[0] for column in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            return results

    def _extract_distributors(
        self,
        distributor_inventory: List[Dict[str, Any]],
        sales_data: List[Dict[str, Any]],
        distributor_deliveries: List[Dict[str, Any]],
    ) -> set[str]:
        """Extract unique distributor IDs from inventory and sales data."""
        distributors = set()
        for row in distributor_inventory:
            if row.get("distributor_id") is not None:
                distributors.add(str(row["distributor_id"]))
        for row in sales_data:
            if row.get("distributor_id") is not None:
                distributors.add(str(row["distributor_id"]))
        for row in distributor_deliveries:
            if row.get("distributor_id") is not None:
                distributors.add(str(row["distributor_id"]))
        return distributors

    def _extract_products(
        self,
        factory_inventory: List[Dict[str, Any]],
        distributor_inventory: List[Dict[str, Any]],
        sales_data: List[Dict[str, Any]],
        target_data: List[Dict[str, Any]],
        distributor_deliveries: List[Dict[str, Any]],
    ) -> set[str]:
        """Extract unique product IDs from all data sources."""
        products = set()
        for row in factory_inventory:
            if row.get("product_id") is not None:
                products.add(str(row["product_id"]))
        for row in distributor_inventory:
            if row.get("product_id") is not None:
                products.add(str(row["product_id"]))
        for row in sales_data:
            if row.get("product_id") is not None:
                products.add(str(row["product_id"]))
        for row in target_data:
            if row.get("product_id") is not None:
                products.add(str(row["product_id"]))
        for row in distributor_deliveries:
            if row.get("product_id") is not None:
                products.add(str(row["product_id"]))
        return products

    def _load_distributor_names(self, distributor_ids: List[str]) -> Dict[str, str]:
        """Load distributor ID -> name from [Analytics_Stage].[Data].[DimDistrbutor]."""
        if not distributor_ids:
            return {}
        try:
            placeholders = ",".join("?" * len(distributor_ids))
            query = f"""
            SELECT ID, DistrbutorTitle
            FROM [Analytics_Stage].[Data].[DimDistrbutor]
            WHERE ID IN ({placeholders})
            """
            rows = self._execute_parameterized_query(query, tuple(distributor_ids))
            return {str(r["ID"]): (r["DistrbutorTitle"] or "").strip() or str(r["ID"]) for r in rows}
        except Exception:
            return {}

    def _load_product_names(self, product_ids: List[str]) -> Dict[str, str]:
        """Load product ID -> name from [Analytics_Stage].[Data].[DimProduct]."""
        if not product_ids:
            return {}
        try:
            placeholders = ",".join("?" * len(product_ids))
            query = f"""
            SELECT ID, ProductTitle
            FROM [Analytics_Stage].[Data].[DimProduct]
            WHERE ID IN ({placeholders})
            """
            rows = self._execute_parameterized_query(query, tuple(product_ids))
            return {str(r["ID"]): (r["ProductTitle"] or "").strip() or str(r["ID"]) for r in rows}
        except Exception:
            return {}

