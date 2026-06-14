/*
Purpose: Create stored procedures for starting and finishing batch runs in the control table.
Assumptions: T-SQL on SQL Server; [Data] schema and [$(prod_schema)].[ctl_BatchRun] table already exist (see 010_ctl_batchrun.sql); requires permissions to create procedures and insert/update on [$(prod_schema)].[ctl_BatchRun].
Usage: These procedures provide a standardized way to track batch execution lifecycle. Use [$(prod_schema)].[ctl_usp_start_batch] at the beginning of a batch process and [$(prod_schema)].[ctl_usp_finish_batch] at the end (success or failure).
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent using CREATE OR ALTER.
*/

-- =============================================
-- Procedure: [$(prod_schema)].[ctl_usp_start_batch]
-- Purpose: Insert a new batch run record and return the generated batch_id
-- =============================================
CREATE OR ALTER PROCEDURE [$(prod_schema)].[ctl_usp_start_batch]
    @batch_type NVARCHAR(50),
    @triggered_by NVARCHAR(100) = NULL,
    @batch_id BIGINT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    
    BEGIN TRY
        -- Validate required parameter
        IF @batch_type IS NULL OR LEN(LTRIM(RTRIM(@batch_type))) = 0
        BEGIN
            THROW 50000, N'@batch_type cannot be NULL or empty', 1;
        END;
        
        -- Insert new batch run record
        INSERT INTO [$(prod_schema)].[ctl_BatchRun] (
            batch_type,
            triggered_by,
            started_at,
            status
        )
        VALUES (
            @batch_type,
            @triggered_by,
            SYSUTCDATETIME(),
            N'RUNNING'
        );
        
        -- Return the generated batch_id
        SET @batch_id = SCOPE_IDENTITY();
        
        IF @batch_id IS NULL
        BEGIN
            THROW 50000, N'Failed to generate batch_id. Check that [$(prod_schema)].[ctl_BatchRun].batch_id is an IDENTITY column.', 1;
        END;
        
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END;
GO

-- =============================================
-- Procedure: [$(prod_schema)].[ctl_usp_finish_batch]
-- Purpose: Update a batch run record with completion status and message
-- =============================================
CREATE OR ALTER PROCEDURE [$(prod_schema)].[ctl_usp_finish_batch]
    @batch_id BIGINT,
    @status NVARCHAR(20),
    @message NVARCHAR(4000) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @started_transaction BIT = 0;
    
    BEGIN TRY
        IF XACT_STATE() = -1
        BEGIN
            THROW 50000, N'Cannot finish batch while transaction is uncommittable (XACT_STATE() = -1). Roll back the transaction and retry outside of it.', 1;
        END;

        IF XACT_STATE() = 1
        BEGIN
            THROW 50000, N'Cannot finish batch inside an active transaction. Commit or roll back the transaction first, then retry outside of it.', 1;
        END;

        BEGIN TRANSACTION;
        SET @started_transaction = 1;

        -- Validate required parameters
        IF @batch_id IS NULL
        BEGIN
            THROW 50000, N'@batch_id cannot be NULL', 1;
        END;
        
        IF @status IS NULL OR LEN(LTRIM(RTRIM(@status))) = 0
        BEGIN
            THROW 50000, N'@status cannot be NULL or empty', 1;
        END;
        
        -- Validate that batch exists
        IF NOT EXISTS (SELECT 1 FROM [$(prod_schema)].[ctl_BatchRun] WHERE batch_id = @batch_id)
        BEGIN
            DECLARE @error_msg1 NVARCHAR(4000) = N'Batch ID ' + CAST(@batch_id AS NVARCHAR(20)) + N' does not exist in [$(prod_schema)].[ctl_BatchRun]';
            THROW 50000, @error_msg1, 1;
        END;
        
        -- Update batch run record
        UPDATE [$(prod_schema)].[ctl_BatchRun]
        SET finished_at = SYSUTCDATETIME(),
            status = @status,
            message = @message
        WHERE batch_id = @batch_id;
        
        IF @@ROWCOUNT = 0
        BEGIN
            DECLARE @error_msg2 NVARCHAR(4000) = N'Failed to update batch ID ' + CAST(@batch_id AS NVARCHAR(20)) + N'. No rows were affected.';
            THROW 50000, @error_msg2, 1;
        END;

        COMMIT TRANSACTION;
        SET @started_transaction = 0;
    END TRY
    BEGIN CATCH
        IF @started_transaction = 1 AND XACT_STATE() <> 0
        BEGIN
            ROLLBACK TRANSACTION;
        END;

        THROW;
    END CATCH;
END;
GO

/*
Example Usage:

-- Start a batch
DECLARE @NewBatchId BIGINT;
EXEC [$(prod_schema)].[ctl_usp_start_batch] 
    @batch_type = N'INVENTORY_LOAD',
    @triggered_by = N'SCHEDULED_JOB',
    @batch_id = @NewBatchId OUTPUT;

PRINT N'Started batch ID: ' + CAST(@NewBatchId AS NVARCHAR(20));

-- ... perform batch operations ...

-- Finish the batch successfully
EXEC [$(prod_schema)].[ctl_usp_finish_batch] 
    @batch_id = @NewBatchId,
    @status = N'SUCCESS',
    @message = N'Batch completed successfully. Processed 1,234 records.';

-- Or finish with failure
EXEC [$(prod_schema)].[ctl_usp_finish_batch] 
    @batch_id = @NewBatchId,
    @status = N'FAILED',
    @message = N'Batch failed: Connection timeout after 30 seconds.';
*/
