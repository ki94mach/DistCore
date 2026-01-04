/*
Purpose: Build factory inventory snapshots from staging ([Data].[stg_FactoryInventory]) into the snapshot table ([Data].[snp_FactoryInventorySnapshot]) for a given snapshot date.
Assumptions: T-SQL on SQL Server; staging table [Data].[stg_FactoryInventory] exists (see 020_stg_factory_inventory.sql); snapshot table [Data].[snp_FactoryInventorySnapshot] exists (see 030_snap_factory_inventory_snapshot.sql).
Usage: This stored procedure is typically called as part of an ETL pipeline after staging load. It aggregates staging data by product_id for today's date only, summing on_hand_qty (DQty) across all factories, and merges into the snapshot table. The procedure is idempotent: re-running with the same @batch_id and @snapshot_date will update existing records if staging data has changed, or leave them unchanged if data is identical. This allows safe reruns of the ETL pipeline without creating duplicate snapshots.
Parameters:
    @batch_id BIGINT - The batch identifier for the staging data to publish (must exist in [Data].[stg_FactoryInventory]).
    @snapshot_date DATE - The snapshot date to assign to published records. Only records with as_of_datetime equal to today's date (CAST(GETDATE() AS DATE)) are included in the aggregation.
Returns: A resultset with columns: inserted_count, updated_count, total_count (one row summary).
How to run: Execute via EXEC [Data].[etl_usp_build_factory_inventory_snapshot] @batch_id = 123, @snapshot_date = '2024-01-15'.
*/

CREATE OR ALTER PROCEDURE [Data].[etl_usp_build_factory_inventory_snapshot]
    @batch_id BIGINT,
    @snapshot_date DATE
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Validate parameters
    IF @batch_id IS NULL
    BEGIN
        THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;
    END;
    
    IF @snapshot_date IS NULL
    BEGIN
        THROW 50000, N'@snapshot_date cannot be NULL. Provide a valid snapshot date.', 1;
    END;
    
    -- Table variable to capture MERGE results
    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10),
        snapshot_date DATE,
        product_id INT
    );
    
    -- Get today's date for filtering
    DECLARE @today_date DATE = CAST(GETDATE() AS DATE);
    
    -- Build source dataset: aggregate staging data by product_id only
    -- Aggregation rule: SUM(on_hand_qty) - sums DQty across all factories for each product
    -- Filter to only today's date (as_of_datetime = @today_date)
    -- Filter out NULL keys to ensure snapshot grain integrity.
    WITH AggregatedStaging AS (
        SELECT 
            product_id,
            SUM(on_hand_qty) AS on_hand_qty
        FROM [Data].[stg_FactoryInventory]
        WHERE batch_id = @batch_id
          AND product_id IS NOT NULL
          AND as_of_datetime = @today_date
        GROUP BY product_id
    )
    -- MERGE into snapshot table
    MERGE [Data].[snp_FactoryInventorySnapshot] AS target
    USING AggregatedStaging AS source
        ON target.snapshot_date = @snapshot_date
       AND target.product_id = source.product_id
    WHEN MATCHED THEN
        UPDATE SET
            on_hand_qty = source.on_hand_qty,
            batch_id = @batch_id
            -- Note: created_at is not updated to preserve original creation timestamp
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (snapshot_date, product_id, on_hand_qty, batch_id)
        VALUES (@snapshot_date, source.product_id, source.on_hand_qty, @batch_id)
    OUTPUT 
        $action AS ActionType,
        inserted.snapshot_date,
        inserted.product_id
    INTO @MergeResults;
    
    -- Return ONE summary result set with columns: inserted_count, updated_count, total_count
    SELECT 
        SUM(CASE WHEN ActionType = N'INSERT' THEN 1 ELSE 0 END) AS inserted_count,
        SUM(CASE WHEN ActionType = N'UPDATE' THEN 1 ELSE 0 END) AS updated_count,
        COUNT(*) AS total_count
    FROM @MergeResults;
END;
GO
