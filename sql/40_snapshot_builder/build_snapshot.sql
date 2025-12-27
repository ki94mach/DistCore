/*
Purpose: Build an optimization-ready "as-of" snapshot by joining curated tables. This query assembles factory inventory data with sales features, targets, and derived metrics for input to the optimization engine.
Grain: One row per (snapshot_date, factory_id, product_id) combination. This grain matches the optimizer input requirements, providing a consistent point-in-time view of inventory levels along with related features and targets needed for decision-making.
Assumptions: T-SQL on SQL Server; curated table [Data].[cur_FactoryInventorySnapshot] exists (see 030_cur_factory_inventory_snapshot.sql); additional curated tables for sales, targets, and derived metrics will be joined as they become available.
Usage: This is a view-like SELECT query that will evolve to include joins with sales features, targets, and derived metrics. Currently scaffolds the base inventory snapshot. The query is intended to be materialized or used as a CTE in downstream optimization processes that require a complete, feature-rich snapshot at a specific point in time.
Parameters:
    @snapshot_date DATE - The snapshot date for which to build the optimization-ready dataset. Must correspond to a snapshot_date that exists in [Data].[cur_FactoryInventorySnapshot].
How to run: Execute in SSMS or via sqlcmd with @snapshot_date parameter set. For now, this returns the base inventory snapshot; TODO sections indicate where additional joins will be added.
*/

DECLARE @snapshot_date DATE = NULL;     -- TODO: Set this parameter when calling

-- Validate parameters
IF @snapshot_date IS NULL
BEGIN
    RAISERROR('@snapshot_date cannot be NULL. Provide a valid snapshot date.', 16, 1);
    RETURN;
END;

-- Base inventory snapshot
SELECT 
    inv.snapshot_date,
    inv.factory_id,
    inv.product_id,
    inv.on_hand_qty,
    inv.batch_id,
    inv.created_at
    
    -- TODO: Sales features
    -- Join curated sales tables to add:
    --   - Moving average sales (e.g., 4-week, 12-week moving averages)
    --   - Sales velocity metrics
    --   - Recent sales trends
    --   - Seasonal adjustment factors
    -- Example placeholder (to be replaced with actual joins):
    -- , sales.ma_sales_4w
    -- , sales.ma_sales_12w
    -- , sales.sales_velocity
    
    -- TODO: Targets
    -- Join curated target tables to add:
    --   - Product-level targets
    --   - Factory-level targets
    --   - Distributor targets (if applicable)
    --   - Target achievement metrics
    -- Example placeholder (to be replaced with actual joins):
    -- , tgt.product_target_qty
    -- , tgt.factory_target_qty
    -- , tgt.target_period_start
    -- , tgt.target_period_end
    
    -- TODO: Derived metrics
    -- Calculate or join derived metrics such as:
    --   - Days of supply (on_hand_qty / avg_daily_sales)
    --   - Inventory coverage ratios
    --   - Safety stock levels
    --   - Reorder point indicators
    --   - Excess inventory flags
    --   - Low stock flags
    -- Example placeholder (to be calculated or joined):
    -- , CASE WHEN sales.ma_sales_4w > 0 THEN inv.on_hand_qty / (sales.ma_sales_4w / 28.0) ELSE NULL END AS days_of_supply
    -- , CASE WHEN inv.on_hand_qty < reorder_point THEN 1 ELSE 0 END AS low_stock_flag

FROM [Data].[cur_FactoryInventorySnapshot] AS inv
WHERE inv.snapshot_date = @snapshot_date

-- TODO: Add LEFT JOIN statements for sales features
-- Example (to be implemented):
-- LEFT JOIN [Data].[cur_SalesFeatures] AS sales
--     ON sales.snapshot_date = inv.snapshot_date
--    AND sales.factory_id = inv.factory_id
--    AND sales.product_id = inv.product_id

-- TODO: Add LEFT JOIN statements for targets
-- Example (to be implemented):
-- LEFT JOIN [Data].[cur_ProductTargets] AS tgt
--     ON tgt.product_id = inv.product_id
--    AND @snapshot_date BETWEEN tgt.target_period_start AND tgt.target_period_end

ORDER BY inv.factory_id, inv.product_id;

/*
Example Execution:

-- Example 1: Build snapshot for snapshot date 2024-01-15
DECLARE @snapshot_date DATE = '2024-01-15';
-- Then execute the entire script

-- Example 2: Verify snapshot data
DECLARE @snapshot_date DATE = '2024-01-15';
-- Execute script and review output

-- Example 3: Check snapshot completeness
SELECT 
    snapshot_date,
    COUNT(*) AS row_count,
    COUNT(DISTINCT factory_id) AS factory_count,
    COUNT(DISTINCT product_id) AS product_count
FROM [Data].[cur_FactoryInventorySnapshot]
WHERE snapshot_date = @snapshot_date
GROUP BY snapshot_date;
*/

