/*
Purpose: Create optimization run registry table to track optimization runs and link them to data snapshots.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
Usage: This table registers each optimization run execution, recording the snapshot date and inventory batch used, along with run status and metadata. Enables tracking of which optimization runs used which data snapshots for audit and reproducibility.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create [Data].[opt_RunRegistry] if missing
IF OBJECT_ID(N'[Data].[opt_RunRegistry]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[opt_RunRegistry] (
        run_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_RunRegistry PRIMARY KEY,
        run_type NVARCHAR(50) NOT NULL CONSTRAINT DF_RunRegistry_run_type DEFAULT N'WEEKLY',
        created_at DATETIME2 NOT NULL CONSTRAINT DF_RunRegistry_created_at DEFAULT SYSUTCDATETIME(),
        snapshot_date DATE NOT NULL,
        inventory_batch_id BIGINT NOT NULL,
        policy_version NVARCHAR(50) NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_RunRegistry_status DEFAULT N'CREATED',
        message NVARCHAR(4000) NULL
    );
END;
GO

-- Index on created_at DESC for recent runs
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[opt_RunRegistry]', 'U')
      AND i.name = N'IX_RunRegistry_CreatedAt'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_RunRegistry_CreatedAt
        ON [Data].[opt_RunRegistry] (created_at DESC);
END;
GO

-- Index on snapshot_date DESC for snapshot-based queries
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[opt_RunRegistry]', 'U')
      AND i.name = N'IX_RunRegistry_SnapshotDate'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_RunRegistry_SnapshotDate
        ON [Data].[opt_RunRegistry] (snapshot_date DESC);
END;
GO

