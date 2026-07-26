/*
Purpose: Create snapshot table for distributor deliveries metrics.
Grain: One row per (snapshot_date, product_id, distributor_id) combination.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
Usage: This table stores point-in-time snapshots of distributor delivery metrics, including the
       6-month moving average of monthly delivery totals (DelMA6) and delivery flags. Used by
       downstream optimization processes that require consistent snapshot inputs.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create [$(prod_schema)].[snp_DistributorDeliveriesSnapshot] if missing
IF OBJECT_ID(N'[$(prod_schema)].[snp_DistributorDeliveriesSnapshot]', 'U') IS NULL
BEGIN
    CREATE TABLE [$(prod_schema)].[snp_DistributorDeliveriesSnapshot] (
        snapshot_date DATE NOT NULL,
        product_id INT NOT NULL,
        distributor_id INT NOT NULL,
        delivered_qty_ma_6 DECIMAL(18, 4) NULL,  -- Avg of monthly delivery totals over last 6 Jalali months (DelMA6)
        has_delivery_last_6m BIT NOT NULL DEFAULT 0,  -- Flag: 1 if there was a delivery in last 6 months, 0 otherwise
        batch_id BIGINT NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_DistributorDeliveriesSnapshot_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_DistributorDeliveriesSnapshot PRIMARY KEY (snapshot_date, product_id, distributor_id)
    );
END;
GO

-- Index to support queries for latest snapshot by date
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_DistributorDeliveriesSnapshot]', 'U')
      AND i.name = N'IX_DistributorDeliveriesSnapshot_SnapshotDate'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_DistributorDeliveriesSnapshot_SnapshotDate
        ON [$(prod_schema)].[snp_DistributorDeliveriesSnapshot] (snapshot_date DESC);
END;
GO

-- Index to support queries by product and distributor
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_DistributorDeliveriesSnapshot]', 'U')
      AND i.name = N'IX_DistributorDeliveriesSnapshot_Product_Distributor'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_DistributorDeliveriesSnapshot_Product_Distributor
        ON [$(prod_schema)].[snp_DistributorDeliveriesSnapshot] (product_id, distributor_id);
END;
GO

