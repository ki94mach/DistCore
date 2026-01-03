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



SELECT 

    [FkVendor] AS factory_id,
    [FKProduct] AS product_id,
    [BatchNo] AS product_batch_no,
    [FKDate] AS as_of_datetime,
    [DQty] AS on_hand_qty
FROM 
    [DWOrchid].[dbo].[FactInventory]
WHERE
    [FKVendor] IS NOT NULL
    AND [FKProduct] IS NOT NULL
    (@since IS NULL OR [FKDate] >= @since)
    AND [FKDate] IS NOT NULL;
