/*
Purpose: Create or alter view that exposes factory inventory snapshot data as optimizer input. This view provides a simplified, optimizer-ready interface to snapshot data.
Grain: One row per (snapshot_date, factory_id, product_id) combination, matching [Data].[snp_FactoryInventorySnapshot].
Assumptions: T-SQL on SQL Server; [Data] schema already exists; snapshot table [Data].[snp_FactoryInventorySnapshot] exists (see 030_snap_factory_inventory_snapshot.sql); requires permissions to create views.
Usage: This view exposes core inventory fields needed by the optimization engine. It serves as the primary input view for optimization processes, abstracting the underlying snapshot table structure. The view can be filtered by snapshot_date in downstream queries to select specific point-in-time snapshots.
How to run: Execute in SSMS or via sqlcmd against the target database. Script is idempotent using CREATE OR ALTER syntax.
*/

CREATE OR ALTER VIEW [Data].[opt_vw_opt_input_inventory]
AS
SELECT 
    snapshot_date,
    factory_id,
    product_id,
    product_batch_no,
    on_hand_qty
    
    -- TODO: Future columns to be added as source tables become available:
    --   - Unit of measure (uom) - e.g., 'CASES', 'UNITS', 'PALLETS'
    --   - Unit price or cost per unit
    --   - Factory capacity constraints (max storage, production capacity)
    --   - Product category or classification codes
    --   - Warehouse location codes
    --   - Safety stock levels
    --   - Lead time indicators
    -- Example placeholders:
    -- , uom
    -- , unit_price
    -- , factory_capacity
    -- , max_storage_qty

FROM [Data].[snp_FactoryInventorySnapshot];
GO

/*
Example Usage:

-- Example 1: Select inventory for a specific snapshot date
SELECT 
    snapshot_date,
    factory_id,
    product_id,
    product_batch_no,
    on_hand_qty
FROM [Data].[opt_vw_opt_input_inventory]
WHERE snapshot_date = '2024-01-15'
ORDER BY factory_id, product_id;

-- Example 2: Get latest snapshot date inventory
SELECT 
    snapshot_date,
    factory_id,
    product_id,
    on_hand_qty
FROM [Data].[opt_vw_opt_input_inventory]
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM [Data].[snp_FactoryInventorySnapshot])
ORDER BY factory_id, product_id;

-- Example 3: Count records by snapshot date
SELECT 
    snapshot_date,
    COUNT(*) AS record_count,
    COUNT(DISTINCT factory_id) AS factory_count,
    COUNT(DISTINCT product_id) AS product_count,
    SUM(on_hand_qty) AS total_on_hand
FROM [Data].[opt_vw_opt_input_inventory]
GROUP BY snapshot_date
ORDER BY snapshot_date DESC;
*/
