"""Data loader for optimization layer from ETL snapshot tables.

This module provides a bridge between the ETL snapshot tables and the optimization
layer by loading and transforming snapshot data into OptimizationData format.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.optimization.data import OptimizationData, OptimizationSettings

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
            snapshot_month: Month for sales snapshot (defaults to snapshot_date's month)
            settings: Optimization settings (defaults to OptimizationSettings())

        Returns:
            OptimizationData instance populated from snapshot tables

        Raises:
            ValueError: If required snapshot data is missing
        """
        if settings is None:
            settings = OptimizationSettings()

        if snapshot_month is None:
            snapshot_month = snapshot_date.replace(day=1)

        # Load all snapshot data
        factory_inventory = self._load_factory_inventory(snapshot_date)
        distributor_inventory = self._load_distributor_inventory(snapshot_date)
        sales_data = self._load_sales_snapshot(snapshot_month)
        target_data = self._load_target_snapshot(snapshot_date)

        # Extract unique distributors and products
        distributors = self._extract_distributors(distributor_inventory, sales_data)
        products = self._extract_products(
            factory_inventory, distributor_inventory, sales_data, target_data
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

        # Aggregate target data by product (sum across year/month combinations)
        target_units_map: Dict[str, float] = {}
        for row in target_data:
            product_id = str(row["product_id"])
            target_qty = float(row["target_quantity"] or 0.0)
            target_units_map[product_id] = target_units_map.get(product_id, 0.0) + target_qty

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
        # Extract year and month from snapshot_date
        year = snapshot_date.year
        month = snapshot_date.month

        query = """
        SELECT 
            product_id,
            target_quantity
        FROM [Data].[snp_TargetSnapshot]
        WHERE snapshot_date = ?
          AND year = ?
          AND month = ?
        """
        return self._execute_parameterized_query(query, (snapshot_date, year, month))

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
    ) -> set[str]:
        """Extract unique distributor IDs from inventory and sales data."""
        distributors = set()
        for row in distributor_inventory:
            if row.get("distributor_id") is not None:
                distributors.add(str(row["distributor_id"]))
        for row in sales_data:
            if row.get("distributor_id") is not None:
                distributors.add(str(row["distributor_id"]))
        return distributors

    def _extract_products(
        self,
        factory_inventory: List[Dict[str, Any]],
        distributor_inventory: List[Dict[str, Any]],
        sales_data: List[Dict[str, Any]],
        target_data: List[Dict[str, Any]],
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
        return products

