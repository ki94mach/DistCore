/*
Purpose: Create staging landing table for historical distributor deliveries from Dropbox files.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
Note: Staging accepts imperfect rows (nullable keys) to enable snapshot transformation before the snapshot layer. Snapshot tables enforce constraints.
*/

-- Create [Data].[stg_DistributorDeliveries] if missing
IF OBJECT_ID(N'[Data].[stg_DistributorDeliveries]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[stg_DistributorDeliveries] (
        batch_id BIGINT NOT NULL,
        ingested_at DATETIME2 NOT NULL CONSTRAINT DF_DistributorDeliveries_ingested_at DEFAULT SYSUTCDATETIME(),
        drug_code NVARCHAR(100) NULL,
        product_name NVARCHAR(500) NULL,
        distributor_name NVARCHAR(200) NULL,
        batch_number NVARCHAR(200) NULL,
        expiry_date DATE NULL,
        delivered_quantity BIGINT NULL,
        delivered_quantity_round_up BIGINT NULL,
        delivered_quantity_round_down BIGINT NULL,
        request_date DATE NULL,
        delivery_date DATE NULL,
        month INT NULL,
        warehouse_exit_letter_number NVARCHAR(200) NULL,
        warehouse_exit_quantity BIGINT NULL,
        warehouse_exit_details NVARCHAR(1000) NULL,
        receipt_status NVARCHAR(100) NULL,
        release_date DATE NULL,
        days_between_delivery_release INT NULL,
        routine_delivery_quantity BIGINT NULL,
        supply_chain_request_quantity BIGINT NULL,
        factory_name NVARCHAR(200) NULL,
        company_name NVARCHAR(200) NULL,
        description NVARCHAR(1000) NULL,
        source_file NVARCHAR(500) NULL,
        source_system NVARCHAR(50) NULL CONSTRAINT DF_DistributorDeliveries_source_system DEFAULT N'Dropbox',
        source_table NVARCHAR(128) NULL CONSTRAINT DF_DistributorDeliveries_source_table DEFAULT N'DeliveryFiles',
        row_hash VARBINARY(32) NULL
    );
END;
GO

-- Clustered index for batch and dimensional access patterns
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[stg_DistributorDeliveries]', 'U')
      AND i.name = N'CI_DistributorDeliveries_Batch_DeliveryDate'
)
BEGIN
    CREATE CLUSTERED INDEX CI_DistributorDeliveries_Batch_DeliveryDate
        ON [Data].[stg_DistributorDeliveries] (batch_id, delivery_date);
END;
GO

-- Nonclustered index to support lookups by delivery date
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[stg_DistributorDeliveries]', 'U')
      AND i.name = N'IX_DistributorDeliveries_DeliveryDate'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_DistributorDeliveries_DeliveryDate
        ON [Data].[stg_DistributorDeliveries] (delivery_date)
        INCLUDE (distributor_name, product_name, delivered_quantity);
END;
GO

-- Nonclustered index to support lookups by company and factory
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[stg_DistributorDeliveries]', 'U')
      AND i.name = N'IX_DistributorDeliveries_Company_Factory'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_DistributorDeliveries_Company_Factory
        ON [Data].[stg_DistributorDeliveries] (company_name, factory_name)
        INCLUDE (delivery_date, delivered_quantity);
END;
GO

