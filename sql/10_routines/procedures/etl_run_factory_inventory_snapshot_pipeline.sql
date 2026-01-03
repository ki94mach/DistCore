/*
Purpose: Orchestrate the complete factory inventory ETL pipeline from staging load through snapshot publication.
Assumptions: T-SQL on SQL Server; all referenced procedures exist ([Data].[ctl_usp_start_batch], [Data].[ctl_usp_finish_batch], [Data].[etl_usp_load_stage_factory_inventory], [Data].[etl_usp_build_factory_inventory_snapshot]); staging and snapshot tables exist; [Data].[ctl_BatchRun] table exists.
Usage: This is the main entry point for running the factory inventory ETL pipeline. It coordinates all steps: batch tracking, staging load, and snapshot publication. Errors bubble up via THROW for Python callers to handle.
Parameters:
    @snapshot_date DATE - The snapshot date to assign to published records in [Data].[snp_FactoryInventorySnapshot] (required).
    @triggered_by NVARCHAR(100) = NULL - Optional identifier for who/what triggered this pipeline run (e.g., 'SCHEDULED_JOB', 'MANUAL', 'API').
Returns: A resultset with columns: batch_id, snapshot_date, status. On success, status is 'SUCCESS'. On failure, an error is thrown and the batch is marked as 'FAILED' in [Data].[ctl_BatchRun].
How to run: Execute via EXEC [Data].[etl_usp_run_factory_inventory_snapshot_pipeline] @snapshot_date = '2024-01-15', @triggered_by = 'SCHEDULED_JOB'. Errors are thrown and should be caught by the calling application (e.g., Python).
*/

-- =============================================
-- Procedure: [Data].[etl_usp_run_factory_inventory_snapshot_pipeline]
-- Purpose: Orchestrate the complete factory inventory ETL pipeline
-- =============================================
CREATE OR ALTER PROCEDURE [Data].[etl_usp_run_factory_inventory_snapshot_pipeline]
  @snapshot_date DATE,
  @triggered_by NVARCHAR(100) = NULL
AS
BEGIN
  SET NOCOUNT ON;

  DECLARE @batch_id BIGINT;

  BEGIN TRY
    -- Start batch
    EXEC [Data].[ctl_usp_start_batch]
      @batch_type = N'FACTORY_INVENTORY',
      @triggered_by = @triggered_by,
      @batch_id = @batch_id OUTPUT;

    IF @batch_id IS NULL
      THROW 51000, N'Batch start failed: no batch id was returned.', 1;

    -- Load staging
    EXEC [Data].[etl_usp_load_stage_factory_inventory] @batch_id = @batch_id;

    -- Build snapshot
    EXEC [Data].[etl_usp_build_factory_inventory_snapshot] @batch_id = @batch_id, @snapshot_date = @snapshot_date;

    -- Finish batch success
    EXEC [Data].[ctl_usp_finish_batch] @batch_id = @batch_id, @status = N'SUCCESS', @message = N'OK';

    -- Return: batch_id, snapshot_date, and a small summary (you can SELECT values)
    SELECT @batch_id AS batch_id, @snapshot_date AS snapshot_date, N'SUCCESS' AS status;

  END TRY
  BEGIN CATCH
    DECLARE @msg NVARCHAR(4000) = ERROR_MESSAGE();
    IF @batch_id IS NULL
      THROW 51000, CONCAT(N'Batch failed before batch id assignment: ', @msg), 1;

    EXEC [Data].[ctl_usp_finish_batch] @batch_id = @batch_id, @status = N'FAILED', @message = @msg;
    THROW;
  END CATCH
END;
GO

/*
Example Usage:

-- Example 1: Run pipeline with default settings (negative quantities not allowed)
EXEC [Data].[etl_usp_run_factory_inventory_snapshot_pipeline] 
  @snapshot_date = '2024-01-15',
  @triggered_by = 'SCHEDULED_JOB';

-- Example 2: Run pipeline allowing negative quantities
EXEC [Data].[etl_usp_run_factory_inventory_snapshot_pipeline] 
  @snapshot_date = '2024-01-15',
  @triggered_by = 'MANUAL';

-- Example 3: Run pipeline with minimal parameters (uses defaults)
EXEC [Data].[etl_usp_run_factory_inventory_snapshot_pipeline] 
  @snapshot_date = '2024-01-15';

-- Example 4: Check batch status after execution
SELECT 
    batch_id,
    batch_type,
    triggered_by,
    started_at,
    finished_at,
    status,
    message
FROM [Data].[ctl_BatchRun]
WHERE batch_id = 123  -- Use the batch_id returned from the procedure
ORDER BY started_at DESC;

-- Example 5: Verify published snapshot data
SELECT 
    snapshot_date,
    factory_id,
    product_id,
    on_hand_qty,
    batch_id,
    created_at
FROM [Data].[snp_FactoryInventorySnapshot]
WHERE snapshot_date = '2024-01-15'
ORDER BY factory_id, product_id;
*/
