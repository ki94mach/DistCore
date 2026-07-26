/*
Purpose: Create snapshot table for target data used by optimization logic.
Grain: One row per (snapshot_date, product_id, year, month) combination.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
Usage: This table stores point-in-time snapshots of target quantities built by
       etl_usp_build_target_snapshot from DWOrchid FactTarget for the Jalali year/month of snapshot_date.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create [$(prod_schema)].[snp_TargetSnapshot] if missing
IF OBJECT_ID(N'[$(prod_schema)].[snp_TargetSnapshot]', 'U') IS NULL
BEGIN
    CREATE TABLE [$(prod_schema)].[snp_TargetSnapshot] (
        snapshot_date DATE NOT NULL,
        product_id INT NOT NULL,
        year INT NOT NULL,
        month INT NOT NULL,
        target_quantity BIGINT NULL,
        batch_id BIGINT NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_TargetSnapshot_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_TargetSnapshot PRIMARY KEY (snapshot_date, product_id, year, month)
    );
END;
GO

-- Index to support queries for latest snapshot by date
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_TargetSnapshot]', 'U')
      AND i.name = N'IX_TargetSnapshot_SnapshotDate'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_TargetSnapshot_SnapshotDate
        ON [$(prod_schema)].[snp_TargetSnapshot] (snapshot_date DESC);
END;
GO

-- Index to support queries by product and year/month
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_TargetSnapshot]', 'U')
      AND i.name = N'IX_TargetSnapshot_Product_Year_Month'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_TargetSnapshot_Product_Year_Month
        ON [$(prod_schema)].[snp_TargetSnapshot] (product_id, year, month);
END;
GO

