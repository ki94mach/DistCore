/*
Purpose: Load factory inventory data from source table [DWOrchid].[dbo].[FactFactoryInventory] into staging table stg.FactoryInventory for a given batch.
Assumptions: T-SQL on SQL Server; source table [DWOrchid].[dbo].[FactFactoryInventory] exists and is accessible; staging table stg.FactoryInventory already exists (see 020_stg_factory_inventory.sql); @batch_id corresponds to a valid batch run in ctl.BatchRun.
Usage: This script is typically called as part of an ETL pipeline after starting a batch (via ctl.usp_start_batch). It loads all current factory inventory rows from the source system into staging, tagged with the provided batch_id. This allows multiple batch runs to coexist in staging without affecting each other.
Parameters:
    @batch_id BIGINT - The batch identifier from ctl.BatchRun to tag all inserted rows.
How to run: Execute in SSMS or via sqlcmd. Should be called after starting a batch and before running validation/transformation steps.
*/

-- =============================================
-- Column Mapping Reference
-- =============================================
-- This section documents the assumed source column names and their mapping to staging columns.
-- TODO: Verify and update the source column names in the INSERT...SELECT below if they differ.
--
-- Source Table: [DWOrchid].[dbo].[FactFactoryInventory]
-- Staging Table: stg.FactoryInventory
--
-- Mapping:
--   batch_id              -> @batch_id (parameter, applied to all rows)
--   [SourceColumn]        -> factory_id (INT)
--   [SourceColumn]        -> product_id (INT)
--   [SourceColumn]        -> as_of_datetime (DATETIME2)
--   [SourceColumn]        -> on_hand_qty (DECIMAL(18, 3))
--
-- Common source column name variations to check:
--   Factory ID: FactoryId, FactoryID, factory_id, Factory_Id
--   Product ID: ProductId, ProductID, product_id, Product_Id
--   As Of DateTime: AsOfDateTime, AsOfDate, as_of_datetime, As_Of_DateTime, SnapshotDate
--   On Hand Qty: OnHandQty, OnHandQuantity, on_hand_qty, On_Hand_Qty, Quantity, Qty
-- =============================================

DECLARE @batch_id BIGINT = NULL;  -- TODO: Set this parameter when calling (e.g., from stored procedure or variable)

-- Validate @batch_id is provided
IF @batch_id IS NULL
BEGIN
    RAISERROR('@batch_id cannot be NULL. Provide a valid batch identifier.', 16, 1);
    RETURN;
END;

-- Insert rows from source into staging, tagged with the provided batch_id
INSERT INTO stg.FactoryInventory (
    batch_id,
    factory_id,
    product_id,
    as_of_datetime,
    on_hand_qty
)
SELECT 
    @batch_id AS batch_id,
    -- TODO: Replace placeholder column names with actual source column names
    -- Example mappings (uncomment and adapt):
    -- CAST([FactoryId] AS INT) AS factory_id,
    -- CAST([ProductId] AS INT) AS product_id,
    -- CAST([AsOfDateTime] AS DATETIME2) AS as_of_datetime,
    -- CAST([OnHandQty] AS DECIMAL(18, 3)) AS on_hand_qty
    CAST([factory_id] AS INT) AS factory_id,                    -- TODO: Update to actual source column
    CAST([product_id] AS INT) AS product_id,                    -- TODO: Update to actual source column
    CAST([as_of_datetime] AS DATETIME2) AS as_of_datetime,      -- TODO: Update to actual source column
    CAST([on_hand_qty] AS DECIMAL(18, 3)) AS on_hand_qty        -- TODO: Update to actual source column
FROM 
    [DWOrchid].[dbo].[FactFactoryInventory];

-- Return the number of rows inserted for this batch
SELECT @@ROWCOUNT AS inserted_rows;

