/*
Purpose: Create persistent fact table for distributor deliveries loaded from DMS Excel files.
Assumptions: T-SQL on SQL Server; [Data] schema already exists on prod database.
Usage: Replaces [$(prod_schema)].[stg_DistributorDeliveries] in production. Historical 1404 rows are retained;
       current-year 1405 rows are refreshed on each pipeline run.
How to run: Execute against prod database (Analytics_Stage on source server); script is idempotent.
*/

IF OBJECT_ID(N'[$(prod_schema)].[fact_DistributorDeliveries]', 'U') IS NULL
BEGIN
    CREATE TABLE [$(prod_schema)].[fact_DistributorDeliveries] (
        loaded_at DATETIME2 NOT NULL CONSTRAINT DF_FactDistributorDeliveries_loaded_at DEFAULT SYSUTCDATETIME(),
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
        source_system NVARCHAR(50) NULL CONSTRAINT DF_FactDistributorDeliveries_source_system DEFAULT N'DMS',
        source_table NVARCHAR(128) NULL CONSTRAINT DF_FactDistributorDeliveries_source_table DEFAULT N'DeliveryFiles',
        row_hash VARBINARY(32) NULL
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[fact_DistributorDeliveries]', 'U')
      AND i.name = N'CI_FactDistributorDeliveries_DeliveryDate'
)
BEGIN
    CREATE CLUSTERED INDEX CI_FactDistributorDeliveries_DeliveryDate
        ON [$(prod_schema)].[fact_DistributorDeliveries] (delivery_date);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[fact_DistributorDeliveries]', 'U')
      AND i.name = N'IX_FactDistributorDeliveries_SourceFile'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_FactDistributorDeliveries_SourceFile
        ON [$(prod_schema)].[fact_DistributorDeliveries] (source_file)
        INCLUDE (product_name, distributor_name, delivered_quantity, [month]);
END;
GO
