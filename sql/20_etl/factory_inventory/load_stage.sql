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
-- IMPORTANT: The source column names in the INSERT...SELECT below are PLACEHOLDERS.
-- You MUST update them to match the actual source table schema before using this procedure.
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

CREATE OR ALTER PROCEDURE etl.usp_load_stage_factory_inventory
  @batch_id BIGINT
AS
BEGIN
  SET NOCOUNT ON;

  -- Validate @batch_id
  IF @batch_id IS NULL
    THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;

  -- Rerun-safe: delete any existing staging rows for this batch_id
  DELETE FROM stg.FactoryInventory WHERE batch_id = @batch_id;

  -- Insert from source table into staging
  -- TODO: Replace placeholder column names with actual source table column names
  --       Verify the actual column names in [DWOrchid].[dbo].[FactFactoryInventory]
  --       Common variations: FactoryId, FactoryID, ProductId, ProductID, AsOfDateTime, OnHandQty, etc.
  INSERT INTO stg.FactoryInventory (batch_id, factory_id, product_id, as_of_datetime, on_hand_qty)
  SELECT
    @batch_id,
    CAST([factory_id] AS INT)      AS factory_id,          -- TODO: Replace [factory_id] with actual source column name
    CAST([product_id] AS INT)      AS product_id,          -- TODO: Replace [product_id] with actual source column name
    CAST([as_of_datetime] AS DATETIME2) AS as_of_datetime, -- TODO: Replace [as_of_datetime] with actual source column name
    CAST([on_hand_qty] AS DECIMAL(18,3)) AS on_hand_qty    -- TODO: Replace [on_hand_qty] with actual source column name
  FROM [DWOrchid].[dbo].[FactFactoryInventory];

  SELECT @@ROWCOUNT AS inserted_rows;
END

