/*
Purpose: Extract current factory inventory rows from the source table [DWOrchid].[dbo].[FactFactoryInventory].
Assumptions: T-SQL on SQL Server; source table [DWOrchid].[dbo].[FactFactoryInventory] exists and is accessible.
Usage: This query extracts factory inventory data with specified column aliases. Can be used with incremental filtering via @since parameter.
Parameters:
    @since DATETIME2 = NULL - Optional timestamp for incremental extraction (e.g., ModifiedAt >= @since). 
                               If NULL, extracts all records.
How to run: Execute in SSMS or via sqlcmd. Can be used as part of an ETL pipeline or as a standalone query.
*/

DECLARE @since DATETIME2 = NULL;  -- Set to a specific datetime for incremental extraction, or NULL for full load

-- TODO: Verify and adapt column names to match the actual source table structure
--       If column names differ from the aliases below, update the SELECT clause accordingly.
--       Common variations might include:
--       - FactoryId vs FactoryID vs factory_id
--       - ProductId vs ProductID vs product_id
--       - AsOfDateTime vs AsOfDate vs as_of_datetime
--       - OnHandQty vs OnHandQuantity vs on_hand_qty

SELECT 
    -- TODO: Replace placeholder_column_name with actual source column name
    -- Example: FactoryId AS factory_id,
    --          ProductId AS product_id,
    --          AsOfDateTime AS as_of_datetime,
    --          OnHandQty AS on_hand_qty
    [factory_id] AS factory_id,          -- TODO: Update to actual source column (e.g., FactoryId)
    [product_id] AS product_id,          -- TODO: Update to actual source column (e.g., ProductId)
    [as_of_datetime] AS as_of_datetime,  -- TODO: Update to actual source column (e.g., AsOfDateTime)
    [on_hand_qty] AS on_hand_qty         -- TODO: Update to actual source column (e.g., OnHandQty)
FROM 
    [DWOrchid].[dbo].[FactFactoryInventory]
WHERE 
    -- Optional incremental filter: uncomment and adapt based on actual source table structure
    -- TODO: Replace ModifiedAt with the actual column name that tracks record changes (e.g., ModifiedDate, UpdatedAt, LastModified)
    -- (@since IS NULL OR ModifiedAt >= @since)
    1=1  -- Placeholder: remove this and uncomment the incremental filter above when ready
;

