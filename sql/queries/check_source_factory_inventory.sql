/*
Purpose: Check records in source table that match the ingestion logic for Factory Inventory.
Assumptions: Run this query on the source database (DWOrchid).
Usage: This query returns the count and sample records that would be extracted according to the ingestion logic.
       For incremental load check, set @since_date to the date you want to filter from (or NULL for full load).
*/

-- Option 1: Full Load Check (all records matching ingestion logic)
-- Set @since_date to NULL to check all records that would be extracted

DECLARE @since_date DATE = NULL;  -- Set to NULL for full load, or set a specific date for incremental check (e.g., '2024-01-15')

-- Count of records that match ingestion logic
SELECT 
    COUNT(*) AS record_count,
    CASE 
        WHEN @since_date IS NULL THEN 'FULL LOAD'
        ELSE 'INCREMENTAL LOAD (from ' + CAST(@since_date AS VARCHAR(10)) + ')'
    END AS load_type,
    MIN([FKDate]) AS min_fk_date,
    MAX([FKDate]) AS max_fk_date
FROM [DWOrchid].[dbo].[FactInventory]
WHERE [FKDate] IS NOT NULL
  AND (@since_date IS NULL OR [FKDate] >= @since_date);

-- Sample records (first 100) that match ingestion logic
SELECT TOP 100
    [FkProvider] AS factory_id,
    [FKProduct] AS product_id,
    [BatchNo] AS product_batch_no,
    [FKDate] AS as_of_datetime,
    [DQty] AS on_hand_qty
FROM [DWOrchid].[dbo].[FactInventory]
WHERE [FKDate] IS NOT NULL
  AND (@since_date IS NULL OR [FKDate] >= @since_date)
ORDER BY [FKDate] DESC;

-- Breakdown by date (to understand data distribution)
SELECT 
    [FKDate] AS as_of_datetime,
    COUNT(*) AS record_count
FROM [DWOrchid].[dbo].[FactInventory]
WHERE [FKDate] IS NOT NULL
  AND (@since_date IS NULL OR [FKDate] >= @since_date)
GROUP BY [FKDate]
ORDER BY [FKDate] DESC;

