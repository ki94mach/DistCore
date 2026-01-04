/*
Purpose: Load factory inventory data from source table [DWOrchid].[dbo].[FactInventory] into staging table [Data].[stg_FactoryInventory] for a given batch.
Assumptions: T-SQL on SQL Server; source table [DWOrchid].[dbo].[FactInventory] exists and is accessible; staging table [Data].[stg_FactoryInventory] already exists (see 020_stg_factory_inventory.sql); @batch_id corresponds to a valid batch run in [Data].[ctl_BatchRun].
Usage: This stored procedure is typically called as part of an ETL pipeline after starting a batch (via [Data].[ctl_usp_start_batch]). It loads factory inventory rows from the source system into staging, tagged with the provided batch_id. Supports incremental loading by default (only loads records after the latest date in staging). This allows multiple batch runs to coexist in staging without affecting each other.
Parameters:
    @batch_id BIGINT - The batch identifier from [Data].[ctl_BatchRun] to tag all inserted rows.
    @incremental BIT = 1 - If 1 (default), only loads records with as_of_datetime after the latest date in staging table. If 0, loads all records from source.
Returns: A resultset with columns: inserted_rows (count of rows inserted), load_type (either 'INCREMENTAL' or 'FULL'), since_date (the date used for filtering, NULL if full load).
How to run: Execute via EXEC [Data].[etl_usp_load_stage_factory_inventory] @batch_id = 123. Should be called after starting a batch and before running snapshot transformation steps.
*/

-- =============================================
-- Column Mapping Reference
-- =============================================
-- This section documents the assumed source column names and their mapping to staging columns.
-- IMPORTANT: The source column names in the INSERT...SELECT below are PLACEHOLDERS.
-- You MUST update them to match the actual source table schema before using this procedure.
--
-- Source Table: [DWOrchid].[dbo].[FactInventory]
-- Staging Table: [Data].[stg_FactoryInventory]
--
-- Mapping:
--   batch_id              -> @batch_id (parameter, applied to all rows)
--   [FkProvider]        -> factory_id (INT)
--   [FKProduct]        -> product_id (INT)
--   [BatchNo]        -> product_batch_no (NVARCHAR(200))
--   [FKDate]        -> as_of_datetime (DATE)
--   [DQty]        -> on_hand_qty (BIGINT)
--
-- =============================================

CREATE OR ALTER PROCEDURE [Data].[etl_usp_load_stage_factory_inventory]
    @batch_id BIGINT,
    @incremental BIT = 1
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Validate @batch_id is not NULL
    IF @batch_id IS NULL
    BEGIN
        THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;
    END;
    
    -- Declare variables for incremental loading
    DECLARE @since_date DATE = NULL;
    DECLARE @load_type NVARCHAR(20) = N'FULL';
    DECLARE @latest_date DATE;
    
    -- Get the latest date from staging table for incremental loading
    IF @incremental = 1
    BEGIN
        SELECT @latest_date = MAX(as_of_datetime)
        FROM [Data].[stg_FactoryInventory];
        
        IF @latest_date IS NOT NULL
        BEGIN
            -- Add 1 day to get only dates AFTER the latest date (not including it)
            SET @since_date = DATEADD(DAY, 1, @latest_date);
            SET @load_type = N'INCREMENTAL';
        END
        ELSE
        BEGIN
            -- No existing data, perform full load
            SET @load_type = N'FULL';
        END
    END
    
    -- Rerun-safe: delete any existing staging rows for this batch_id
    DELETE FROM [Data].[stg_FactoryInventory] WHERE batch_id = @batch_id;
    
    -- Insert from source table into staging
    -- This procedure runs on the source database (DWOrchid) to access source tables directly.
    -- The staging table [Data].[stg_FactoryInventory] must exist in the source database.
    -- If @since_date is not NULL, only load records with FKDate >= @since_date (incremental load)
    -- If @since_date is NULL, load all records (full load)

    INSERT INTO [Data].[stg_FactoryInventory] (batch_id, factory_id, product_id, product_batch_no, as_of_datetime, on_hand_qty)
    SELECT
        @batch_id,
        CAST([FkProvider] AS INT)      AS factory_id,         
        CAST([FKProduct] AS INT)      AS product_id,         
        CAST([BatchNo] AS NVARCHAR(200)) AS product_batch_no,
        CAST([FKDate] AS DATE) AS as_of_datetime,
        CAST([DQty] AS BIGINT) AS on_hand_qty    
    FROM [DWOrchid].[dbo].[FactInventory]
    WHERE FkProvider IS NOT NULL
      AND FKProduct IS NOT NULL
      AND (@since_date IS NULL OR [FKDate] >= @since_date);
    
    -- Return result set with inserted row count, load type, and since_date
    SELECT 
        @@ROWCOUNT AS inserted_rows,
        @load_type AS load_type,
        @since_date AS since_date;
END;
GO

/*
Example Execution:

-- Example 1: Load staging data for batch 123 (incremental by default)
EXEC [Data].[etl_usp_load_stage_factory_inventory] @batch_id = 123;

-- Example 1b: Load staging data for batch 123 (full load, all records)
EXEC [Data].[etl_usp_load_stage_factory_inventory] @batch_id = 123, @incremental = 0;

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
