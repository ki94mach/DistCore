/*
Purpose: Build distributor deliveries snapshots from staging ([Data].[stg_DistributorDeliveries]) into the snapshot table ([Data].[snp_DistributorDeliveriesSnapshot]) for a given snapshot date.
Aggregation Logic:
    - Aggregates by (product_name, distributor_name) from staging data.
    - Calculates 6-month moving average of delivered quantity (excluding current month).
    - Sets flag indicating if there was any delivery in the last 6 months.
    - Includes all product-distributor combinations from staging data.
Grain: One row per (snapshot_date, product_name, distributor_name) in the snapshot table.
Assumptions: T-SQL on SQL Server; staging table [Data].[stg_DistributorDeliveries] exists (see 024_stg_distributor_deliveries.sql); snapshot table [Data].[snp_DistributorDeliveriesSnapshot] exists (see 034_snap_distributor_deliveries_snapshot.sql).
Usage: This stored procedure is typically called as part of an ETL pipeline after staging load. It aggregates staging data by product_name and distributor_name, computes 6-month moving averages, and merges into the snapshot table. The procedure is idempotent: re-running with the same @batch_id and @snapshot_date will update existing records if staging data has changed, or leave them unchanged if data is identical.
Parameters:
    @batch_id BIGINT - The batch identifier for the staging data to publish (must exist in [Data].[stg_DistributorDeliveries]).
    @snapshot_date DATE - Gregorian snapshot date to assign to published records. Moving averages are calculated up to this date.
    @snapshot_jalali_yyyymm INT - Optional Jalali year-month (YYYYMM). If provided, it is converted to Gregorian date
        using [Analytics_Stage].[Data].[DimDate] (ShamsiYearMonth, ShamsiDay=1) and overrides @snapshot_date.
Returns: A resultset with columns: inserted_count, updated_count, total_count (one row summary).
How to run: Execute via EXEC [Data].[etl_usp_build_distributor_deliveries_snapshot] @batch_id = 123, @snapshot_date = '2024-01-15'.
             Or EXEC [Data].[etl_usp_build_distributor_deliveries_snapshot] @batch_id = 123, @snapshot_jalali_yyyymm = 140409.
*/

CREATE OR ALTER PROCEDURE [Data].[etl_usp_build_distributor_deliveries_snapshot]
    @batch_id BIGINT,
    @snapshot_date DATE,
    @snapshot_jalali_yyyymm INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- Validate parameters
    IF @batch_id IS NULL
    BEGIN
        THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;
    END;

    IF @snapshot_date IS NULL AND @snapshot_jalali_yyyymm IS NULL
    BEGIN
        THROW 50000, N'@snapshot_date cannot be NULL unless @snapshot_jalali_yyyymm is provided.', 1;
    END;

    -- Resolve effective snapshot date (Gregorian). If Jalali YYYYMM is provided, map to DateID via DimDate.
    DECLARE @effective_snapshot_date DATE = @snapshot_date;
    IF @snapshot_jalali_yyyymm IS NOT NULL
    BEGIN
        DECLARE @snapshot_jalali_yyyymm_char NVARCHAR(6) =
            RIGHT('000000' + CAST(@snapshot_jalali_yyyymm AS VARCHAR(6)), 6);

        SELECT TOP (1)
            @effective_snapshot_date = DateID
        FROM [Analytics_Stage].[Data].[DimDate]
        WHERE (
            REPLACE(REPLACE(LTRIM(RTRIM(ShamsiYearMonth)), '/', ''), '-', '') = @snapshot_jalali_yyyymm_char
            OR REPLACE(REPLACE(LTRIM(RTRIM(LongShamsiYearMonth)), '/', ''), '-', '') = @snapshot_jalali_yyyymm_char
        )
          AND ShamsiDay = 1;

        IF @effective_snapshot_date IS NULL
        BEGIN
            THROW 50000, N'Invalid @snapshot_jalali_yyyymm. No matching DateID in [Analytics_Stage].[Data].[DimDate].', 1;
        END;
    END;

    -- Table variable to capture MERGE results
    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10),
        snapshot_date DATE,
        product_name NVARCHAR(500),
        distributor_name NVARCHAR(200)
    );

    -- Calculate date range for last 6 months (excluding current month)
    -- Last 6 months: from 6 months ago to 1 month ago (relative to effective snapshot date)
    DECLARE @six_months_ago DATE = DATEADD(MONTH, -6, @effective_snapshot_date);
    DECLARE @one_month_ago DATE = DATEADD(MONTH, -1, @effective_snapshot_date);
    DECLARE @snapshot_month_start DATE = DATEFROMPARTS(YEAR(@effective_snapshot_date), MONTH(@effective_snapshot_date), 1);

    -- CTE 1: Monthly aggregated deliveries by product and distributor
    WITH MonthlyDeliveries AS (
        SELECT
            product_name,
            distributor_name,
            DATEFROMPARTS(YEAR(delivery_date), MONTH(delivery_date), 1) AS delivery_month,
            SUM(delivered_quantity) AS monthly_delivered_qty
        FROM [Data].[stg_DistributorDeliveries]
        WHERE batch_id = @batch_id
          AND product_name IS NOT NULL
          AND distributor_name IS NOT NULL
          AND delivery_date IS NOT NULL
          AND delivered_quantity IS NOT NULL
          AND delivered_quantity <> 0
          AND receipt_status = N'رسید شده'
          AND delivery_date >= @six_months_ago
          AND delivery_date < @snapshot_month_start  -- Exclude current month
        GROUP BY
            product_name,
            distributor_name,
            DATEFROMPARTS(YEAR(delivery_date), MONTH(delivery_date), 1)
    ),
    -- CTE 2: Calculate 6-month moving average for each month
    -- Moving average is calculated over the last 6 months (6 months ago to 1 month ago)
    MonthlyWithMovingAverage AS (
        SELECT
            product_name,
            distributor_name,
            delivery_month,
            monthly_delivered_qty,
            -- Calculate moving average over last 6 months (excluding current month)
            -- For each month, average the previous 6 months (if available)
            AVG(CAST(monthly_delivered_qty AS DECIMAL(18, 4))) OVER (
                PARTITION BY product_name, distributor_name
                ORDER BY delivery_month
                ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
            ) AS delivered_qty_ma_6
        FROM MonthlyDeliveries
        WHERE delivery_month <= @one_month_ago  -- Only include months up to 1 month ago
    ),
    -- CTE 3: Get the latest moving average for each product-distributor combination
    LatestMovingAverage AS (
        SELECT
            product_name,
            distributor_name,
            delivered_qty_ma_6,
            ROW_NUMBER() OVER (
                PARTITION BY product_name, distributor_name
                ORDER BY delivery_month DESC
            ) AS rn
        FROM MonthlyWithMovingAverage
    ),
    -- CTE 4: Check if there was any delivery in the last 6 months
    DeliveryFlag AS (
        SELECT
            product_name,
            distributor_name,
            CASE 
                WHEN COUNT(*) > 0 THEN 1
                ELSE 0
            END AS has_delivery_last_6m
        FROM [Data].[stg_DistributorDeliveries]
        WHERE batch_id = @batch_id
          AND product_name IS NOT NULL
          AND distributor_name IS NOT NULL
          AND delivery_date IS NOT NULL
          AND delivered_quantity IS NOT NULL
          AND delivered_quantity <> 0
          AND receipt_status = N'رسید شده'
          AND delivery_date >= @six_months_ago
          AND delivery_date < @snapshot_month_start  -- Exclude current month
        GROUP BY product_name, distributor_name
    ),
    -- CTE 5: Get all unique product-distributor combinations from staging
    AllProductDistributors AS (
        SELECT DISTINCT
            product_name,
            distributor_name
        FROM [Data].[stg_DistributorDeliveries]
        WHERE batch_id = @batch_id
          AND product_name IS NOT NULL
          AND distributor_name IS NOT NULL
          AND delivered_quantity IS NOT NULL
          AND delivered_quantity <> 0
          AND receipt_status = N'رسید شده'
    )
    -- MERGE into snapshot table
    MERGE [Data].[snp_DistributorDeliveriesSnapshot] AS target
    USING (
        SELECT
            apd.product_name,
            apd.distributor_name,
            ISNULL(lma.delivered_qty_ma_6, 0) AS delivered_qty_ma_6,
            ISNULL(df.has_delivery_last_6m, 0) AS has_delivery_last_6m
        FROM AllProductDistributors AS apd
        LEFT JOIN LatestMovingAverage AS lma
            ON lma.product_name = apd.product_name
           AND lma.distributor_name = apd.distributor_name
           AND lma.rn = 1
        LEFT JOIN DeliveryFlag AS df
            ON df.product_name = apd.product_name
           AND df.distributor_name = apd.distributor_name
    ) AS source
        ON target.snapshot_date = @effective_snapshot_date
       AND target.product_name = source.product_name
       AND target.distributor_name = source.distributor_name
    WHEN MATCHED THEN
        UPDATE SET
            delivered_qty_ma_6 = source.delivered_qty_ma_6,
            has_delivery_last_6m = source.has_delivery_last_6m,
            batch_id = @batch_id
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (snapshot_date, product_name, distributor_name, delivered_qty_ma_6, has_delivery_last_6m, batch_id, product_id, distributor_id)
        VALUES (@effective_snapshot_date, source.product_name, source.distributor_name, source.delivered_qty_ma_6, source.has_delivery_last_6m, @batch_id, NULL, NULL)
    OUTPUT
        $action AS ActionType,
        inserted.snapshot_date,
        inserted.product_name,
        inserted.distributor_name
    INTO @MergeResults;

    -- Return ONE summary result set with columns: inserted_count, updated_count, total_count
    SELECT
        SUM(CASE WHEN ActionType = N'INSERT' THEN 1 ELSE 0 END) AS inserted_count,
        SUM(CASE WHEN ActionType = N'UPDATE' THEN 1 ELSE 0 END) AS updated_count,
        COUNT(*) AS total_count
    FROM @MergeResults;
END;
GO

