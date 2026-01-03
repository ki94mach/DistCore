/*
Purpose: Load factory inventory data from source table [DWOrchid].[dbo].[FactFactoryInventory] into staging table [Data].[stg_FactoryInventory] for a given batch.
Assumptions: T-SQL on SQL Server; source table [DWOrchid].[dbo].[FactFactoryInventory] exists and is accessible; staging table [Data].[stg_FactoryInventory] already exists (see 020_stg_factory_inventory.sql); @batch_id corresponds to a valid batch run in [Data].[ctl_BatchRun].
Usage: This stored procedure is typically called as part of an ETL pipeline after starting a batch (via [Data].[ctl_usp_start_batch]). It loads all current factory inventory rows from the source system into staging, tagged with the provided batch_id. This allows multiple batch runs to coexist in staging without affecting each other.
Parameters:
    @batch_id BIGINT - The batch identifier from [Data].[ctl_BatchRun] to tag all inserted rows.
Returns: A resultset with columns: inserted_rows (count of rows inserted).
How to run: Execute via EXEC [Data].[etl_usp_load_stage_factory_inventory] @batch_id = 123. Should be called after starting a batch and before running snapshot transformation steps.
*/

-- =============================================
-- Column Mapping Reference
-- =============================================
-- This section documents the assumed source column names and their mapping to staging columns.
-- IMPORTANT: The source column names in the INSERT...SELECT below are PLACEHOLDERS.
-- You MUST update them to match the actual source table schema before using this procedure.
--
-- Source Table: [DWOrchid].[dbo].[FactFactoryInventory]
-- Staging Table: [Data].[stg_FactoryInventory]
--
-- Mapping:
--   batch_id              -> @batch_id (parameter, applied to all rows)
--   [FKVendor]        -> factory_id (INT)
--   [FKProduct]        -> product_id (INT)
--   [BatchNo]        -> product_batch_no (NVARCHAR(200))
--   [FKDate]        -> as_of_datetime (DATE)
--   [DQty]        -> on_hand_qty (BIGINT)
--
-- =============================================

CREATE OR ALTER PROCEDURE [Data].[etl_usp_load_stage_factory_inventory]
    @batch_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Validate @batch_id is not NULL
    IF @batch_id IS NULL
    BEGIN
        THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;
    END;
    
    -- Rerun-safe: delete any existing staging rows for this batch_id
    DELETE FROM [Data].[stg_FactoryInventory] WHERE batch_id = @batch_id;
    
    -- Insert from source table into staging
    -- This procedure runs on the source database (DWOrchid) to access source tables directly.
    -- The staging table [Data].[stg_FactoryInventory] must exist in the source database.

    INSERT INTO [Data].[stg_FactoryInventory] (batch_id, factory_id, product_id, product_batch_no, as_of_datetime, on_hand_qty)
    SELECT
        @batch_id,
        CAST([FKVendor] AS INT)      AS factory_id,         
        CAST([FKProduct] AS INT)      AS product_id,         
        CAST([BatchNo] AS NVARCHAR(200)) AS product_batch_no,
        CAST([FKDate] AS DATE) AS as_of_datetime,
        CAST([DQty] AS BIGINT) AS on_hand_qty    
    FROM [DWOrchid].[dbo].[FactInventory]
    WHERE [FKDate] IS NOT NULL;
    
    -- Return result set with inserted row count
    SELECT @@ROWCOUNT AS inserted_rows;
END;
GO

/*
Example Execution:

-- Example 1: Load staging data for batch 123
EXEC [Data].[etl_usp_load_stage_factory_inventory] @batch_id = 123;

-- Example 2: Verify loaded data
SELECT 
    batch_id,
    COUNT(*) AS row_count,
    MIN(ingested_at) AS first_ingested,
    MAX(ingested_at) AS last_ingested
FROM [Data].[stg_FactoryInventory]
WHERE batch_id = 123
GROUP BY batch_id;

-- Example 3: Check for NULL keys (review before snapshot build)
SELECT 
    batch_id,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN factory_id IS NULL OR product_id IS NULL THEN 1 ELSE 0 END) AS null_key_rows
FROM [Data].[stg_FactoryInventory]
WHERE batch_id = 123
GROUP BY batch_id;
*/
