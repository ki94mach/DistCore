/*
Purpose: Update default source_system for distributor deliveries staging to DMS on existing databases.
Assumptions: [Data].[stg_DistributorDeliveries] already exists (024_stg_distributor_deliveries.sql).
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

IF OBJECT_ID(N'[Data].[stg_DistributorDeliveries]', 'U') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1
        FROM sys.default_constraints dc
        INNER JOIN sys.columns c
            ON c.default_object_id = dc.object_id
        WHERE dc.parent_object_id = OBJECT_ID(N'[Data].[stg_DistributorDeliveries]', 'U')
          AND c.name = N'source_system'
          AND dc.name = N'DF_DistributorDeliveries_source_system'
    )
    BEGIN
        ALTER TABLE [Data].[stg_DistributorDeliveries]
            DROP CONSTRAINT DF_DistributorDeliveries_source_system;
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints dc
        INNER JOIN sys.columns c
            ON c.default_object_id = dc.object_id
        WHERE dc.parent_object_id = OBJECT_ID(N'[Data].[stg_DistributorDeliveries]', 'U')
          AND c.name = N'source_system'
    )
    BEGIN
        ALTER TABLE [Data].[stg_DistributorDeliveries]
            ADD CONSTRAINT DF_DistributorDeliveries_source_system
                DEFAULT N'DMS' FOR source_system;
    END;
END;
GO
