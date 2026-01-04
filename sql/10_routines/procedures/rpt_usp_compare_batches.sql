/*
Purpose: Compare two inventory batches to help identify differences in factory inventory data between batch runs. This stored procedure provides row counts, detailed differences by factory/product combination, and summary statistics to facilitate batch comparison and troubleshooting.
Grain: Aggregated by (factory_id, product_id) per batch using MAX(on_hand_qty) to match the publish logic. Multiple rows for the same (factory_id, product_id) within a batch are aggregated to a single quantity value.
Assumptions: T-SQL on SQL Server; staging table [Data].[stg_FactoryInventory] exists (see 020_stg_factory_inventory.sql); both batch_id values exist in [Data].[stg_FactoryInventory]; aggregation uses MAX(on_hand_qty) to match the publish.sql aggregation rule.
Usage: Execute via EXEC [Data].[rpt_usp_compare_batches] @batch_a = 123, @batch_b = 124. The procedure returns multiple result sets: row counts, top differences, and summary statistics.
Parameters:
    @batch_a BIGINT - First batch identifier to compare (must exist in [Data].[stg_FactoryInventory]).
    @batch_b BIGINT - Second batch identifier to compare (must exist in [Data].[stg_FactoryInventory]).
How to run: Execute via EXEC [Data].[rpt_usp_compare_batches] @batch_a = 123, @batch_b = 124. All queries are pure SELECTs with no side effects.
*/

CREATE OR ALTER PROCEDURE [Data].[rpt_usp_compare_batches]
    @batch_a BIGINT,
    @batch_b BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    -- Validate parameters
    IF @batch_a IS NULL OR @batch_b IS NULL
    BEGIN
        THROW 50000, N'Both @batch_a and @batch_b must be provided. Set valid batch identifiers.', 1;
    END;

-- ============================================================================
-- 1. Row Counts Per Batch
-- ============================================================================
-- Shows the raw row count and distinct (factory_id, product_id) count for each batch
WITH DistinctCombos AS (
    SELECT 
        batch_id,
        factory_id,
        product_id,
        product_batch_no
    FROM [Data].[stg_FactoryInventory]
    WHERE batch_id IN (@batch_a, @batch_b)
    GROUP BY batch_id, factory_id, product_id, product_batch_no
),
ComboCounts AS (
    SELECT 
        batch_id,
        COUNT(*) AS distinct_factory_product_combos
    FROM DistinctCombos
    GROUP BY batch_id
)
SELECT 
    f.batch_id,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT f.factory_id) AS distinct_factories,
    COUNT(DISTINCT f.product_id) AS distinct_products,
    COUNT(DISTINCT f.product_batch_no) AS distinct_product_batches,
    ISNULL(cc.distinct_factory_product_combos, 0) AS distinct_factory_product_combos
FROM [Data].[stg_FactoryInventory] f
LEFT JOIN ComboCounts cc ON f.batch_id = cc.batch_id
WHERE f.batch_id IN (@batch_a, @batch_b)
GROUP BY f.batch_id, cc.distinct_factory_product_combos
ORDER BY f.batch_id;

-- ============================================================================
-- 2. Top Differences Per (factory_id, product_id)
-- ============================================================================
-- Shows the largest quantity differences between batches, ordered by absolute delta
-- Aggregates each batch by (factory_id, product_id) using MAX(on_hand_qty) to match publish logic
WITH BatchA AS (
    SELECT 
        factory_id,
        product_id,
        product_batch_no,
        MAX(on_hand_qty) AS qty_a
    FROM [Data].[stg_FactoryInventory]
    WHERE batch_id = @batch_a
      AND factory_id IS NOT NULL
      AND product_id IS NOT NULL
      AND product_batch_no IS NOT NULL
    GROUP BY factory_id, product_id, product_batch_no
),
BatchB AS (
    SELECT 
        factory_id,
        product_id,
        product_batch_no,
        MAX(on_hand_qty) AS qty_b
    FROM [Data].[stg_FactoryInventory]
    WHERE batch_id = @batch_b
      AND factory_id IS NOT NULL
      AND product_id IS NOT NULL
      AND product_batch_no IS NOT NULL
    GROUP BY factory_id, product_id, product_batch_no
),
Comparison AS (
    SELECT 
        ISNULL(a.factory_id, b.factory_id) AS factory_id,
        ISNULL(a.product_id, b.product_id) AS product_id,
        ISNULL(a.product_batch_no, b.product_batch_no) AS product_batch_no,
        ISNULL(a.qty_a, 0.0) AS qty_a,
        ISNULL(b.qty_b, 0.0) AS qty_b,
        ISNULL(b.qty_b, 0.0) - ISNULL(a.qty_a, 0.0) AS delta
    FROM BatchA AS a
    FULL OUTER JOIN BatchB AS b
        ON a.factory_id = b.factory_id
       AND a.product_id = b.product_id
)
SELECT TOP 100
    factory_id,
    product_id,
    product_batch_no,
    qty_a,
    qty_b,
    delta,
    ABS(delta) AS abs_delta
FROM Comparison
WHERE delta != 0.0  -- Only show differences
ORDER BY ABS(delta) DESC, factory_id, product_id, product_batch_no;

-- ============================================================================
-- 3. Summary Statistics
-- ============================================================================
-- Provides aggregate statistics about the differences between batches
WITH BatchA AS (
    SELECT 
        factory_id,
        product_id,
        product_batch_no,
        MAX(on_hand_qty) AS qty_a
    FROM [Data].[stg_FactoryInventory]
    WHERE batch_id = @batch_a
      AND factory_id IS NOT NULL
      AND product_id IS NOT NULL
      AND product_batch_no IS NOT NULL
    GROUP BY factory_id, product_id, product_batch_no
),
BatchB AS (
    SELECT 
        factory_id,
        product_id,
        product_batch_no,
        MAX(on_hand_qty) AS qty_b
    FROM [Data].[stg_FactoryInventory]
    WHERE batch_id = @batch_b
      AND factory_id IS NOT NULL
      AND product_id IS NOT NULL
      AND product_batch_no IS NOT NULL
    GROUP BY factory_id, product_id, product_batch_no
),
Comparison AS (
    SELECT 
        ISNULL(a.factory_id, b.factory_id) AS factory_id,
        ISNULL(a.product_id, b.product_id) AS product_id,
        ISNULL(a.product_batch_no, b.product_batch_no) AS product_batch_no,
        ISNULL(a.qty_a, 0.0) AS qty_a,
        ISNULL(b.qty_b, 0.0) AS qty_b,
        ISNULL(b.qty_b, 0.0) - ISNULL(a.qty_a, 0.0) AS delta,
        CASE WHEN a.factory_id IS NULL THEN 1 ELSE 0 END AS only_in_batch_b,
        CASE WHEN b.factory_id IS NULL THEN 1 ELSE 0 END AS only_in_batch_a
    FROM BatchA AS a
    FULL OUTER JOIN BatchB AS b
        ON a.factory_id = b.factory_id
       AND a.product_id = b.product_id
)
SELECT 
    COUNT(*) AS total_factory_product_combos,
    SUM(CASE WHEN delta != 0.0 THEN 1 ELSE 0 END) AS count_changed,
    SUM(CASE WHEN delta = 0.0 THEN 1 ELSE 0 END) AS count_unchanged,
    SUM(only_in_batch_b) AS count_only_in_batch_b,
    SUM(only_in_batch_a) AS count_only_in_batch_a,
    MAX(ABS(delta)) AS max_abs_delta,
    MIN(delta) AS min_delta,
    MAX(delta) AS max_delta,
    AVG(CASE WHEN delta != 0.0 THEN ABS(delta) ELSE NULL END) AS avg_abs_delta,
    SUM(CASE WHEN delta > 0.0 THEN delta ELSE 0.0 END) AS total_positive_delta,
    SUM(CASE WHEN delta < 0.0 THEN ABS(delta) ELSE 0.0 END) AS total_negative_delta
FROM Comparison;
END;
GO

/*
Example Usage:

-- Example 1: Compare batches 123 and 124
EXEC [Data].[rpt_usp_compare_batches] @batch_a = 123, @batch_b = 124;

-- Example 2: Compare latest two batches
DECLARE @batch_a BIGINT = (SELECT MAX(batch_id) - 1 FROM [Data].[stg_FactoryInventory]);
DECLARE @batch_b BIGINT = (SELECT MAX(batch_id) FROM [Data].[stg_FactoryInventory]);
EXEC [Data].[rpt_usp_compare_batches] @batch_a = @batch_a, @batch_b = @batch_b;

-- Example 3: Verify batch exists before comparing
IF EXISTS (SELECT 1 FROM [Data].[stg_FactoryInventory] WHERE batch_id = 123)
   AND EXISTS (SELECT 1 FROM [Data].[stg_FactoryInventory] WHERE batch_id = 124)
BEGIN
    EXEC [Data].[rpt_usp_compare_batches] @batch_a = 123, @batch_b = 124;
END
ELSE
BEGIN
    PRINT 'One or both batches do not exist.';
END
*/

