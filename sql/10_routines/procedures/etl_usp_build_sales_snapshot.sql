/*
Purpose: Build sales snapshots directly from [$(source_database)].[dbo].[Flat_Fact_Sale].
Uses a rolling window ending on @snapshot_date (7 months of data for MA6 support).
Parameters:
    @batch_id BIGINT - Audit lineage stamped on snapshot rows.
    @snapshot_date DATE - Snapshot date; Jalali month resolved via [$(source_database)].[$(source_schema)].[DimDate].
*/

CREATE OR ALTER PROCEDURE [$(prod_schema)].[etl_usp_build_sales_snapshot]
    @batch_id BIGINT,
    @snapshot_date DATE
AS
BEGIN
    SET NOCOUNT ON;

    IF @batch_id IS NULL
        THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;

    IF @snapshot_date IS NULL
        THROW 50000, N'@snapshot_date cannot be NULL. Provide a valid snapshot date.', 1;

    DECLARE @snapshot_jalali_yyyymm INT;
    DECLARE @snapshot_jalali_year INT;
    DECLARE @snapshot_jalali_month INT;
    DECLARE @snapshot_month DATE;
    DECLARE @window_start DATE;
    DECLARE @window_start_jalali INT;
    DECLARE @y INT;
    DECLARE @m INT;

    SELECT TOP (1)
        @snapshot_jalali_yyyymm = TRY_CONVERT(INT, LongShamsiYearMonth),
        @snapshot_jalali_year = ShamsiYear,
        @snapshot_jalali_month = ShamsiMonth
    FROM [$(source_database)].[dbo].[DimDate]
    WHERE DateID = @snapshot_date;

    IF @snapshot_jalali_yyyymm IS NULL OR @snapshot_jalali_year IS NULL OR @snapshot_jalali_month IS NULL
        THROW 50000, N'Could not resolve Jalali year/month from [$(source_database)].[dbo].[DimDate] for @snapshot_date.', 1;

    -- Normalize day-level YYYYMMDD to month-level YYYYMM when DimDate stores 8 digits
    IF @snapshot_jalali_yyyymm >= 1000000
        SET @snapshot_jalali_yyyymm = @snapshot_jalali_yyyymm / 100;

    SELECT TOP (1)
        @snapshot_month = DateID
    FROM [$(source_database)].[dbo].[DimDate]
    WHERE ShamsiDay = 1
      AND (
            CASE
                WHEN TRY_CONVERT(INT, LongShamsiYearMonth) >= 1000000
                    THEN TRY_CONVERT(INT, LongShamsiYearMonth) / 100
                ELSE TRY_CONVERT(INT, LongShamsiYearMonth)
            END
          ) = @snapshot_jalali_yyyymm;

    IF @snapshot_month IS NULL
        THROW 50000, N'Could not resolve Jalali month start date from [$(source_database)].[$(source_schema)].[DimDate] for @snapshot_date.', 1;

    -- 7 Jalali months inclusive (current + 6 prior) for MA6 support
    SET @y = @snapshot_jalali_yyyymm / 100;
    SET @m = @snapshot_jalali_yyyymm % 100;
    SET @m = @m - 6;
    IF @m < 1 BEGIN SET @m = @m + 12; SET @y = @y - 1; END;
    SET @window_start_jalali = @y * 100 + @m;

    SELECT TOP (1)
        @window_start = DateID
    FROM [$(source_database)].[dbo].[DimDate]
    WHERE ShamsiDay = 1
      AND (
            CASE
                WHEN TRY_CONVERT(INT, LongShamsiYearMonth) >= 1000000
                    THEN TRY_CONVERT(INT, LongShamsiYearMonth) / 100
                ELSE TRY_CONVERT(INT, LongShamsiYearMonth)
            END
          ) = @window_start_jalali;

    IF @window_start IS NULL
        THROW 50000, N'Could not resolve Jalali window start from [$(source_database)].[dbo].[DimDate].', 1;

    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10),
        snapshot_month DATE,
        product_id INT,
        distributor_id INT
    );

    DELETE FROM [$(prod_schema)].[snp_SalesSnapshot];

    WITH SourceMapped AS (
        SELECT
            CAST(s.[FkDistributor] AS INT) AS distributor_id,
            CAST(s.[FKProduct] AS INT) AS product_id,
            CAST(s.[FKDate] AS DATE) AS as_of_datetime,
            CAST(s.[DQty] AS BIGINT) AS sales_qty,
            d.LongShamsiYearMonth AS jalali_yyyymm
        FROM [$(source_database)].[dbo].[Flat_Fact_Sale] AS s
        INNER JOIN [$(source_database)].[dbo].[DimDate] AS d
            ON d.DateID = CAST(s.[FKDate] AS DATE)
        WHERE s.[FkDistributor] IS NOT NULL
          AND s.[FkCenter] IS NOT NULL
          AND s.[FKProduct] IS NOT NULL
          AND s.[FKDate] IS NOT NULL
          AND s.[DQty] <> 0
          AND CAST(s.[FKDate] AS DATE) >= @window_start
          AND CAST(s.[FKDate] AS DATE) <= @snapshot_date
    ),
    DailyTotals AS (
        SELECT
            distributor_id,
            product_id,
            as_of_datetime,
            SUM(sales_qty) AS sales_qty,
            jalali_yyyymm
        FROM SourceMapped
        GROUP BY distributor_id, product_id, as_of_datetime, jalali_yyyymm
    ),
    MonthlyTotals AS (
        SELECT
            product_id,
            distributor_id,
            month_start.DateID AS snapshot_month,
            SUM(sales_qty) AS monthly_sales
        FROM DailyTotals AS sm
        INNER JOIN [$(source_database)].[dbo].[DimDate] AS month_start
            ON month_start.ShamsiDay = 1
           AND (
                CASE
                    WHEN TRY_CONVERT(INT, month_start.LongShamsiYearMonth) >= 1000000
                        THEN TRY_CONVERT(INT, month_start.LongShamsiYearMonth) / 100
                    ELSE TRY_CONVERT(INT, month_start.LongShamsiYearMonth)
                END
               ) = sm.jalali_yyyymm
        GROUP BY product_id, distributor_id, month_start.DateID
    ),
    ZeroCurrentMonth AS (
        SELECT DISTINCT mt.product_id, mt.distributor_id
        FROM MonthlyTotals AS mt
        WHERE mt.snapshot_month < @snapshot_month
        EXCEPT
        SELECT product_id, distributor_id
        FROM MonthlyTotals
        WHERE snapshot_month = @snapshot_month
    ),
    MonthlyTotalsWithZeros AS (
        SELECT product_id, distributor_id, snapshot_month, monthly_sales
        FROM MonthlyTotals
        UNION ALL
        SELECT product_id, distributor_id, @snapshot_month AS snapshot_month, 0 AS monthly_sales
        FROM ZeroCurrentMonth
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
                ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
            ) AS sales_ma_3,
            AVG(CAST(monthly_sales AS DECIMAL(18, 4))) OVER (
                PARTITION BY product_id, distributor_id
                ORDER BY snapshot_month
                ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING
            ) AS sales_ma_6
        FROM MonthlyTotalsWithZeros
    ),
    SnapshotMonth AS (
        SELECT product_id, distributor_id, snapshot_month, sales_ma_3, sales_ma_6
        FROM MonthlyWithAverages
        WHERE snapshot_month = @snapshot_month
    ),
    MonthToDate AS (
        SELECT product_id, distributor_id, SUM(sales_qty) AS sales_mtd
        FROM DailyTotals
        WHERE as_of_datetime >= @snapshot_month
          AND as_of_datetime <= @snapshot_date
        GROUP BY product_id, distributor_id
    )
    MERGE [$(prod_schema)].[snp_SalesSnapshot] AS target
    USING (
        SELECT
            snapshot.snapshot_month,
            snapshot.product_id,
            snapshot.distributor_id,
            @snapshot_jalali_year AS jalali_year,
            @snapshot_jalali_month AS jalali_month,
            COALESCE(mtd.sales_mtd, 0) AS sales_mtd,
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
            jalali_year = source.jalali_year,
            jalali_month = source.jalali_month,
            batch_id = @batch_id
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (snapshot_month, product_id, distributor_id, jalali_year, jalali_month, sales_mtd, sales_ma_3, sales_ma_6, batch_id)
        VALUES (source.snapshot_month, source.product_id, source.distributor_id, source.jalali_year, source.jalali_month, source.sales_mtd, source.sales_ma_3, source.sales_ma_6, @batch_id)
    OUTPUT
        $action AS ActionType,
        inserted.snapshot_month,
        inserted.product_id,
        inserted.distributor_id
    INTO @MergeResults;

    SELECT
        SUM(CASE WHEN ActionType = N'INSERT' THEN 1 ELSE 0 END) AS inserted_count,
        SUM(CASE WHEN ActionType = N'UPDATE' THEN 1 ELSE 0 END) AS updated_count,
        COUNT(*) AS total_count
    FROM @MergeResults;
END;
GO
