/*
Purpose: Create snapshot table for distributor sales metrics at a monthly grain.
Grain: One row per (snapshot_month, distributor_id, product_id) combination.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
Usage: This table stores month-level sales metrics built by etl_usp_build_sales_snapshot from
       DWOrchid Flat_Fact_Sale, including month-to-date totals and moving averages.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create [$(prod_schema)].[snp_SalesSnapshot] if missing
IF OBJECT_ID(N'[$(prod_schema)].[snp_SalesSnapshot]', 'U') IS NULL
BEGIN
    CREATE TABLE [$(prod_schema)].[snp_SalesSnapshot] (
        snapshot_month DATE NOT NULL,
        product_id INT NOT NULL,
        distributor_id INT NOT NULL,
        jalali_year INT NULL,
        jalali_month INT NULL,
        sales_mtd BIGINT NULL,
        sales_ma_3 DECIMAL(18, 4) NULL,
        sales_ma_6 DECIMAL(18, 4) NULL,
        batch_id BIGINT NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_SalesSnapshot_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_SalesSnapshot PRIMARY KEY (snapshot_month, product_id, distributor_id)
    );
END;
GO

-- Add Jalali year/month columns if missing (idempotent)
IF NOT EXISTS (
    SELECT 1
    FROM sys.columns c
    WHERE c.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_SalesSnapshot]', 'U')
      AND c.name = N'jalali_year'
)
BEGIN
    ALTER TABLE [$(prod_schema)].[snp_SalesSnapshot]
        ADD jalali_year INT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.columns c
    WHERE c.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_SalesSnapshot]', 'U')
      AND c.name = N'jalali_month'
)
BEGIN
    ALTER TABLE [$(prod_schema)].[snp_SalesSnapshot]
        ADD jalali_month INT NULL;
END;
GO

-- Index to support queries for latest snapshot by month
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_SalesSnapshot]', 'U')
      AND i.name = N'IX_SalesSnapshot_SnapshotMonth'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_SalesSnapshot_SnapshotMonth
        ON [$(prod_schema)].[snp_SalesSnapshot] (snapshot_month DESC);
END;
GO
