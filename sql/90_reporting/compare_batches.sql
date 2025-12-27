/*
Purpose: Compare two inventory batches to help identify differences in factory inventory data between batch runs. This script provides row counts, detailed differences by factory/product combination, and summary statistics to facilitate batch comparison and troubleshooting.
Grain: Aggregated by (factory_id, product_id) per batch using MAX(on_hand_qty) to match the publish logic. Multiple rows for the same (factory_id, product_id) within a batch are aggregated to a single quantity value.
Assumptions: T-SQL on SQL Server; staging table stg.FactoryInventory exists (see 020_stg_factory_inventory.sql); both batch_id values exist in stg.FactoryInventory; aggregation uses MAX(on_hand_qty) to match the publish.sql aggregation rule.
Usage: Execute in SSMS or via sqlcmd. Set @batch_a and @batch_b parameters to the batch identifiers you want to compare. The script returns multiple result sets: row counts, top differences, and summary statistics.
Parameters:
    @batch_a BIGINT - First batch identifier to compare (must exist in stg.FactoryInventory).
    @batch_b BIGINT - Second batch identifier to compare (must exist in stg.FactoryInventory).
How to run: Set the @batch_a and @batch_b parameters at the top of the script, then execute. All queries are pure SELECTs with no side effects.
*/

DECLARE @batch_a BIGINT = NULL;  -- TODO: Set this parameter when calling
DECLARE @batch_b BIGINT = NULL;  -- TODO: Set this parameter when calling

-- Validate parameters
IF @batch_a IS NULL OR @batch_b IS NULL
BEGIN
    RAISERROR('Both @batch_a and @batch_b must be provided. Set valid batch identifiers.', 16, 1);
    RETURN;
END;

-- ============================================================================
-- 1. Row Counts Per Batch
-- ============================================================================
-- Shows the raw row count and distinct (factory_id, product_id) count for each batch
SELECT 
    batch_id,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT factory_id) AS distinct_factories,
    COUNT(DISTINCT product_id) AS distinct_products,
    COUNT(DISTINCT CONCAT(CAST(factory_id AS NVARCHAR(10)), '_', CAST(product_id AS NVARCHAR(10)))) AS distinct_factory_product_combos
FROM stg.FactoryInventory
WHERE batch_id IN (@batch_a, @batch_b)
GROUP BY batch_id
ORDER BY batch_id;

-- ============================================================================
-- 2. Top Differences Per (factory_id, product_id)
-- ============================================================================
-- Shows the largest quantity differences between batches, ordered by absolute delta
-- Aggregates each batch by (factory_id, product_id) using MAX(on_hand_qty) to match publish logic
WITH BatchA AS (
    SELECT 
        factory_id,
        product_id,
        MAX(on_hand_qty) AS qty_a
    FROM stg.FactoryInventory
    WHERE batch_id = @batch_a
      AND factory_id IS NOT NULL
      AND product_id IS NOT NULL
    GROUP BY factory_id, product_id
),
BatchB AS (
    SELECT 
        factory_id,
        product_id,
        MAX(on_hand_qty) AS qty_b
    FROM stg.FactoryInventory
    WHERE batch_id = @batch_b
      AND factory_id IS NOT NULL
      AND product_id IS NOT NULL
    GROUP BY factory_id, product_id
),
Comparison AS (
    SELECT 
        ISNULL(a.factory_id, b.factory_id) AS factory_id,
        ISNULL(a.product_id, b.product_id) AS product_id,
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
    qty_a,
    qty_b,
    delta,
    ABS(delta) AS abs_delta
FROM Comparison
WHERE delta != 0.0  -- Only show differences
ORDER BY ABS(delta) DESC, factory_id, product_id;

-- ============================================================================
-- 3. Summary Statistics
-- ============================================================================
-- Provides aggregate statistics about the differences between batches
WITH BatchA AS (
    SELECT 
        factory_id,
        product_id,
        MAX(on_hand_qty) AS qty_a
    FROM stg.FactoryInventory
    WHERE batch_id = @batch_a
      AND factory_id IS NOT NULL
      AND product_id IS NOT NULL
    GROUP BY factory_id, product_id
),
BatchB AS (
    SELECT 
        factory_id,
        product_id,
        MAX(on_hand_qty) AS qty_b
    FROM stg.FactoryInventory
    WHERE batch_id = @batch_b
      AND factory_id IS NOT NULL
      AND product_id IS NOT NULL
    GROUP BY factory_id, product_id
),
Comparison AS (
    SELECT 
        ISNULL(a.factory_id, b.factory_id) AS factory_id,
        ISNULL(a.product_id, b.product_id) AS product_id,
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

/*
Example Usage:

-- Example 1: Compare batches 123 and 124
DECLARE @batch_a BIGINT = 123;
DECLARE @batch_b BIGINT = 124;
-- Execute the entire script

-- Example 2: Compare latest two batches
DECLARE @batch_a BIGINT = (SELECT MAX(batch_id) - 1 FROM stg.FactoryInventory);
DECLARE @batch_b BIGINT = (SELECT MAX(batch_id) FROM stg.FactoryInventory);
-- Execute the entire script

-- Example 3: Verify batch exists before comparing
IF EXISTS (SELECT 1 FROM stg.FactoryInventory WHERE batch_id = 123)
   AND EXISTS (SELECT 1 FROM stg.FactoryInventory WHERE batch_id = 124)
BEGIN
    DECLARE @batch_a BIGINT = 123;
    DECLARE @batch_b BIGINT = 124;
    -- Execute the entire script
END
ELSE
BEGIN
    PRINT 'One or both batches do not exist.';
END
*/

