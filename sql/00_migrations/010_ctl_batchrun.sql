/*
Purpose: Create control tables for batch tracking and optional source watermarks.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create [Data].[ctl_BatchRun] if missing
IF OBJECT_ID(N'[Data].[ctl_BatchRun]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[ctl_BatchRun] (
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
    WHERE i.object_id = OBJECT_ID(N'[Data].[ctl_BatchRun]', 'U')
      AND i.name = N'IX_BatchRun_StartedAt_Status'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_BatchRun_StartedAt_Status
        ON [Data].[ctl_BatchRun] (started_at DESC, status);
END;
GO

-- Optional: Create [Data].[ctl_SourceWatermark] if missing
IF OBJECT_ID(N'[Data].[ctl_SourceWatermark]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[ctl_SourceWatermark] (
        source_name NVARCHAR(200) NOT NULL CONSTRAINT PK_SourceWatermark PRIMARY KEY,
        watermark_column NVARCHAR(128) NULL,
        last_success_watermark DATETIME2 NULL,
        last_batch_id BIGINT NULL,
        updated_at DATETIME2 NOT NULL CONSTRAINT DF_SourceWatermark_updated_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

