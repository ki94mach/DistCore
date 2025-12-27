/*
Purpose: Orchestrate the complete factory inventory ETL pipeline from staging load through validation to curated snapshot publication.
Assumptions: T-SQL on SQL Server; all referenced procedures exist (ctl.usp_start_batch, ctl.usp_finish_batch, etl.usp_load_stage_factory_inventory, etl.usp_validate_factory_inventory, etl.usp_publish_factory_inventory_snapshot); staging and curated tables exist; ctl.BatchRun table exists.
Usage: This is the main entry point for running the factory inventory ETL pipeline. It coordinates all steps: batch tracking, staging load, validation, and snapshot publication. Errors bubble up via THROW for Python callers to handle.
Parameters:
    @snapshot_date DATE - The snapshot date to assign to published records in cur.FactoryInventorySnapshot (required).
    @triggered_by NVARCHAR(100) = NULL - Optional identifier for who/what triggered this pipeline run (e.g., 'SCHEDULED_JOB', 'MANUAL', 'API').
    @allow_negative BIT = 0 - If 1, allows negative on_hand_qty values during validation. If 0, treats negative quantities as validation failures.
Returns: A resultset with columns: batch_id, snapshot_date, status. On success, status is 'SUCCESS'. On failure, an error is thrown and the batch is marked as 'FAILED' in ctl.BatchRun.
How to run: Execute via EXEC etl.usp_run_factory_inventory_pipeline @snapshot_date = '2024-01-15', @triggered_by = 'SCHEDULED_JOB', @allow_negative = 0. Errors are thrown and should be caught by the calling application (e.g., Python).
*/

-- =============================================
-- Procedure: etl.usp_run_factory_inventory_pipeline
-- Purpose: Orchestrate the complete factory inventory ETL pipeline
-- =============================================
CREATE OR ALTER PROCEDURE etl.usp_run_factory_inventory_pipeline
  @snapshot_date DATE,
  @triggered_by NVARCHAR(100) = NULL,
  @allow_negative BIT = 0
AS
BEGIN
  SET NOCOUNT ON;

  DECLARE @batch_id BIGINT;

  BEGIN TRY
    -- Start batch
    EXEC ctl.usp_start_batch
      @batch_type = N'FACTORY_INVENTORY',
      @triggered_by = @triggered_by,
      @batch_id = @batch_id OUTPUT;

    -- Load staging
    EXEC etl.usp_load_stage_factory_inventory @batch_id = @batch_id;

    -- Validate staging
    EXEC etl.usp_validate_factory_inventory @batch_id = @batch_id, @allow_negative = @allow_negative;

    -- Publish curated snapshot
    EXEC etl.usp_publish_factory_inventory_snapshot @batch_id = @batch_id, @snapshot_date = @snapshot_date;

    -- Finish batch success
    EXEC ctl.usp_finish_batch @batch_id = @batch_id, @status = N'SUCCESS', @message = N'OK';

    -- Return: batch_id, snapshot_date, and a small summary (you can SELECT values)
    SELECT @batch_id AS batch_id, @snapshot_date AS snapshot_date, N'SUCCESS' AS status;

  END TRY
  BEGIN CATCH
    DECLARE @msg NVARCHAR(4000) = ERROR_MESSAGE();
    IF @batch_id IS NOT NULL
      EXEC ctl.usp_finish_batch @batch_id = @batch_id, @status = N'FAILED', @message = @msg;
    THROW;
  END CATCH
END;
GO

/*
Example Usage:

-- Example 1: Run pipeline with default settings (negative quantities not allowed)
EXEC etl.usp_run_factory_inventory_pipeline 
  @snapshot_date = '2024-01-15',
  @triggered_by = 'SCHEDULED_JOB',
  @allow_negative = 0;

-- Example 2: Run pipeline allowing negative quantities
EXEC etl.usp_run_factory_inventory_pipeline 
  @snapshot_date = '2024-01-15',
  @triggered_by = 'MANUAL',
  @allow_negative = 1;

-- Example 3: Run pipeline with minimal parameters (uses defaults)
EXEC etl.usp_run_factory_inventory_pipeline 
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
FROM ctl.BatchRun
WHERE batch_id = 123  -- Use the batch_id returned from the procedure
ORDER BY started_at DESC;

-- Example 5: Review validation results for the batch
SELECT 
    rule_name,
    severity,
    failed_count,
    sample_query,
    created_at
FROM dq.ValidationResult
WHERE batch_id = 123  -- Use the batch_id returned from the procedure
ORDER BY created_at DESC;

-- Example 6: Verify published snapshot data
SELECT 
    snapshot_date,
    factory_id,
    product_id,
    on_hand_qty,
    batch_id,
    created_at
FROM cur.FactoryInventorySnapshot
WHERE snapshot_date = '2024-01-15'
ORDER BY factory_id, product_id;
*/

