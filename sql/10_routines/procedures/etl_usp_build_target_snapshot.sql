/*
Purpose: Build target snapshots from staging ([Data].[stg_Target]) into the snapshot table ([Data].[snp_TargetSnapshot]) for a given snapshot date.
Aggregation Logic: 
    - Direct mapping from staging to snapshot (no additional aggregation needed)
    - Data is already aggregated at (product_id, year, month) level in the extract query
    - Filters to records in staging for the given batch_id
    - Result: Target quantities per product, year, and month for the snapshot date
Grain: One row per (snapshot_date, product_id, year, month) in the snapshot table.
Assumptions: T-SQL on SQL Server; staging table [Data].[stg_Target] exists (see 023_stg_target.sql); snapshot table [Data].[snp_TargetSnapshot] exists (see 033_snap_target_snapshot.sql).
Usage: This stored procedure is typically called as part of an ETL pipeline after staging load. It merges staging data into the snapshot table. The procedure is idempotent: re-running with the same @batch_id and @snapshot_date will update existing records if staging data has changed, or leave them unchanged if data is identical. This allows safe reruns of the ETL pipeline without creating duplicate snapshots.
Parameters:
    @batch_id BIGINT - The batch identifier for the staging data to publish (must exist in [Data].[stg_Target]).
    @snapshot_date DATE - The snapshot date to assign to published records.
Returns: A resultset with columns: inserted_count, updated_count, total_count (one row summary).
How to run: Execute via EXEC [Data].[etl_usp_build_target_snapshot] @batch_id = 123, @snapshot_date = '2024-01-15'.
*/

CREATE OR ALTER PROCEDURE [Data].[etl_usp_build_target_snapshot]
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
        product_id INT,
        year INT,
        month INT
    );
    
    -- Build source dataset: select staging data for the batch
    -- Filter out NULL keys to ensure snapshot grain integrity
    WITH StagingData AS (
        SELECT 
            product_id,
            year,
            month,
            target_quantity
        FROM [Data].[stg_Target]
        WHERE batch_id = @batch_id
          AND product_id IS NOT NULL
          AND year IS NOT NULL
          AND month IS NOT NULL
    )
    -- MERGE into snapshot table
    MERGE [Data].[snp_TargetSnapshot] AS target
    USING StagingData AS source
        ON target.snapshot_date = @snapshot_date
       AND target.product_id = source.product_id
       AND target.year = source.year
       AND target.month = source.month
    WHEN MATCHED THEN
        UPDATE SET
            target_quantity = source.target_quantity,
            batch_id = @batch_id
            -- Note: created_at is not updated to preserve original creation timestamp
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (snapshot_date, product_id, year, month, target_quantity, batch_id)
        VALUES (@snapshot_date, source.product_id, source.year, source.month, source.target_quantity, @batch_id)
    OUTPUT 
        $action AS ActionType,
        inserted.snapshot_date,
        inserted.product_id,
        inserted.year,
        inserted.month
    INTO @MergeResults;
    
    -- Return ONE summary result set with columns: inserted_count, updated_count, total_count
    SELECT 
        SUM(CASE WHEN ActionType = N'INSERT' THEN 1 ELSE 0 END) AS inserted_count,
        SUM(CASE WHEN ActionType = N'UPDATE' THEN 1 ELSE 0 END) AS updated_count,
        COUNT(*) AS total_count
    FROM @MergeResults;
END;
GO

