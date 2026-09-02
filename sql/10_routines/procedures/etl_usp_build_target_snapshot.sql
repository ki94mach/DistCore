/*
Purpose: Build target snapshots from [$(prod_schema)].[Data0_Target_Dosage].
Grain: One row per (snapshot_date, product_id, year, month) for the Jalali month of @snapshot_date.
Parameters:
    @batch_id BIGINT - Audit lineage stamped on snapshot rows.
    @snapshot_date DATE - Used to resolve Jalali year/month via [$(source_database)].[$(source_schema)].[DimDate].
*/

CREATE OR ALTER PROCEDURE [$(prod_schema)].[etl_usp_build_target_snapshot]
    @batch_id BIGINT,
    @snapshot_date DATE
AS
BEGIN
    SET NOCOUNT ON;

    IF @batch_id IS NULL
        THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;

    IF @snapshot_date IS NULL
        THROW 50000, N'@snapshot_date cannot be NULL. Provide a valid snapshot date.', 1;

    DECLARE @target_year INT;
    DECLARE @target_month INT;

    SELECT TOP (1)
        @target_year = ShamsiYear,
        @target_month = ShamsiMonth
    FROM [$(source_database)].[$(source_schema)].[DimDate]
    WHERE DateID = @snapshot_date;

    IF @target_year IS NULL OR @target_month IS NULL
        THROW 50000, N'Could not resolve Jalali year/month from [$(source_database)].[$(source_schema)].[DimDate] for @snapshot_date.', 1;

    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10),
        snapshot_date DATE,
        product_id INT,
        year INT,
        month INT
    );

    TRUNCATE TABLE [$(prod_schema)].[snp_TargetSnapshot];

    WITH SourceData AS (
        SELECT
            CAST(t.[FK_Product_ID] AS INT) AS product_id,
            @target_year AS year,
            @target_month AS month,
            SUM(CAST(t.[TargetQuantity] AS BIGINT)) AS target_quantity
        FROM [$(prod_schema)].[Data0_Target_Dosage] AS t
        INNER JOIN [$(source_database)].[$(source_schema)].[DimDate] AS d
            ON d.DateID = CAST(t.[FK_Date_ID] AS DATE)
        WHERE d.ShamsiYear = @target_year
          AND d.ShamsiMonth = @target_month
          AND t.[FK_Product_ID] IS NOT NULL
          AND t.[FK_Date_ID] IS NOT NULL
          AND t.[TargetQuantity] IS NOT NULL
        GROUP BY t.[FK_Product_ID]
    )
    MERGE [$(prod_schema)].[snp_TargetSnapshot] AS target
    USING SourceData AS source
        ON target.snapshot_date = @snapshot_date
       AND target.product_id = source.product_id
       AND target.year = source.year
       AND target.month = source.month
    WHEN MATCHED THEN
        UPDATE SET
            target_quantity = source.target_quantity,
            batch_id = @batch_id
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

    SELECT
        SUM(CASE WHEN ActionType = N'INSERT' THEN 1 ELSE 0 END) AS inserted_count,
        SUM(CASE WHEN ActionType = N'UPDATE' THEN 1 ELSE 0 END) AS updated_count,
        COUNT(*) AS total_count
    FROM @MergeResults;
END;
GO
