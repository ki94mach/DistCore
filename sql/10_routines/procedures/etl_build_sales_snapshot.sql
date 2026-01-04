/*
Purpose: Build sales snapshots from staging ([Data].[stg_Sales]) into the snapshot table ([Data].[snp_SalesSnapshot]) for a given snapshot date.
Aggregation Logic:
    - Aggregates by (product_id, distributor_id, snapshot_month) from staging data.
    - Calculates monthly sales totals and moving averages over monthly totals.
    - Calculates month-to-date sales for the snapshot month up to the snapshot date.
Grain: One row per (snapshot_month, distributor_id, product_id) in the snapshot table.
Assumptions: T-SQL on SQL Server; staging table [Data].[stg_Sales] exists (see 022_stg_sales.sql); snapshot table [Data].[snp_SalesSnapshot] exists (see 032_snap_sales_snapshot.sql).
Usage: This stored procedure is typically called as part of an ETL pipeline after staging load. It aggregates staging data by product_id and distributor_id by month, computes moving averages, and merges into the snapshot table. The procedure is idempotent: re-running with the same @batch_id and @snapshot_date will update existing records if staging data has changed, or leave them unchanged if data is identical.
Parameters:
    @batch_id BIGINT - The batch identifier for the staging data to publish (must exist in [Data].[stg_Sales]).
    @snapshot_date DATE - The snapshot date to assign to published records. Month-to-date totals are computed up to this date.
Returns: A resultset with columns: inserted_count, updated_count, total_count (one row summary).
How to run: Execute via EXEC [Data].[etl_usp_build_sales_snapshot] @batch_id = 123, @snapshot_date = '2024-01-15'.
*/

CREATE OR ALTER PROCEDURE [Data].[etl_usp_build_sales_snapshot]
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

    DECLARE @snapshot_month DATE = DATEFROMPARTS(YEAR(@snapshot_date), MONTH(@snapshot_date), 1);

    -- Table variable to capture MERGE results
    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10),
        snapshot_month DATE,
        product_id INT,
        distributor_id INT
    );

    WITH MonthlyTotals AS (
        SELECT
            product_id,
            distributor_id,
            DATEFROMPARTS(YEAR(as_of_datetime), MONTH(as_of_datetime), 1) AS snapshot_month,
            SUM(sales_qty) AS monthly_sales
        FROM [Data].[stg_Sales]
        WHERE product_id IS NOT NULL
          AND distributor_id IS NOT NULL
          AND as_of_datetime IS NOT NULL
        GROUP BY
            product_id,
            distributor_id,
            DATEFROMPARTS(YEAR(as_of_datetime), MONTH(as_of_datetime), 1)
    ),
    MonthlyWithAverages AS (
        SELECT
            product_id,
            distributor_id,
            snapshot_month,
            monthly_sales,
            AVG(CAST(monthly_sales AS DECIMAL(18, 4))) OVER (
                PARTITION BY product_id, distributor_id
                ORDER BY snapshot_month
                ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
            ) AS sales_ma_3,
            AVG(CAST(monthly_sales AS DECIMAL(18, 4))) OVER (
                PARTITION BY product_id, distributor_id
                ORDER BY snapshot_month
                ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
            ) AS sales_ma_6
        FROM MonthlyTotals
    ),
    SnapshotMonth AS (
        SELECT
            product_id,
            distributor_id,
            snapshot_month,
            sales_ma_3,
            sales_ma_6
        FROM MonthlyWithAverages
        WHERE snapshot_month = @snapshot_month
    ),
    MonthToDate AS (
        SELECT
            product_id,
            distributor_id,
            SUM(sales_qty) AS sales_mtd
        FROM [Data].[stg_Sales]
        WHERE product_id IS NOT NULL
          AND distributor_id IS NOT NULL
          AND as_of_datetime >= @snapshot_month
          AND as_of_datetime <= @snapshot_date
        GROUP BY product_id, distributor_id
    )
    MERGE [Data].[snp_SalesSnapshot] AS target
    USING (
        SELECT
            snapshot.snapshot_month,
            snapshot.product_id,
            snapshot.distributor_id,
            mtd.sales_mtd,
            snapshot.sales_ma_3,
            snapshot.sales_ma_6
        FROM SnapshotMonth AS snapshot
        LEFT JOIN MonthToDate AS mtd
            ON mtd.product_id = snapshot.product_id
           AND mtd.distributor_id = snapshot.distributor_id
    ) AS source
        ON target.snapshot_month = source.snapshot_month
       AND target.product_id = source.product_id
       AND target.distributor_id = source.distributor_id
    WHEN MATCHED THEN
        UPDATE SET
            sales_mtd = source.sales_mtd,
            sales_ma_3 = source.sales_ma_3,
            sales_ma_6 = source.sales_ma_6,
            batch_id = @batch_id
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (snapshot_month, product_id, distributor_id, sales_mtd, sales_ma_3, sales_ma_6, batch_id)
        VALUES (source.snapshot_month, source.product_id, source.distributor_id, source.sales_mtd, source.sales_ma_3, source.sales_ma_6, @batch_id)
    OUTPUT
        $action AS ActionType,
        inserted.snapshot_month,
        inserted.product_id,
        inserted.distributor_id
    INTO @MergeResults;

    -- Return ONE summary result set with columns: inserted_count, updated_count, total_count
    SELECT
        SUM(CASE WHEN ActionType = N'INSERT' THEN 1 ELSE 0 END) AS inserted_count,
        SUM(CASE WHEN ActionType = N'UPDATE' THEN 1 ELSE 0 END) AS updated_count,
        COUNT(*) AS total_count
    FROM @MergeResults;
END;
GO
