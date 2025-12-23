/*
Purpose: Create control tables for batch tracking and optional source watermarks.
Assumptions: T-SQL on SQL Server; `ctl` schema already exists (see 000_init_schemas.sql); requires permissions to create tables and indexes.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create ctl.BatchRun if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'ctl' AND t.name = N'BatchRun'
)
BEGIN
    CREATE TABLE ctl.BatchRun (
        batch_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_BatchRun PRIMARY KEY,
        batch_type NVARCHAR(50) NOT NULL,
        started_at DATETIME2 NOT NULL CONSTRAINT DF_BatchRun_started_at DEFAULT SYSUTCDATETIME(),
        finished_at DATETIME2 NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_BatchRun_status DEFAULT N'RUNNING', -- RUNNING/SUCCESS/FAILED/PARTIAL
        message NVARCHAR(4000) NULL,
        triggered_by NVARCHAR(100) NULL,
        source_watermarks NVARCHAR(MAX) NULL -- JSON text allowed
    );
END;
GO

-- Index for recent batches by time and status
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.tables t ON i.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'ctl' AND t.name = N'BatchRun' AND i.name = N'IX_BatchRun_StartedAt_Status'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_BatchRun_StartedAt_Status
        ON ctl.BatchRun (started_at DESC, status);
END;
GO

-- Optional: Create ctl.SourceWatermark if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'ctl' AND t.name = N'SourceWatermark'
)
BEGIN
    CREATE TABLE ctl.SourceWatermark (
        source_name NVARCHAR(200) NOT NULL CONSTRAINT PK_SourceWatermark PRIMARY KEY,
        watermark_column NVARCHAR(128) NULL,
        last_success_watermark DATETIME2 NULL,
        last_batch_id BIGINT NULL,
        updated_at DATETIME2 NOT NULL CONSTRAINT DF_SourceWatermark_updated_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

