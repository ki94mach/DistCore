/*
Purpose: Count rows in the source table grouped by FKDate, filtered by the ingestion WHERE clause.
Assumptions: Run this query on the source database (DWOrchid).
Usage: Returns the count of records for each FKDate value in the source table, filtered to show data from the last few days.
       Adjust @days_ago to change how many days back to look (default is 7 days).
*/

-- Set the number of days to look back (adjust as needed)
DECLARE @days_ago INT = 7;  -- Change this value to look back more or fewer days
DECLARE @since_date DATE = DATEADD(DAY, -@days_ago, CAST(GETDATE() AS DATE));

-- Count rows grouped by FKDate (with ingestion WHERE clause)
SELECT 
    [FKDate] AS fk_date,
    COUNT(*) AS row_count
FROM [DWOrchid].[dbo].[FactInventory]
WHERE [FKDate] IS NOT NULL
  AND [FKDate] >= @since_date
GROUP BY [FKDate]
ORDER BY [FKDate] DESC;

-- Summary statistics (with ingestion WHERE clause)
SELECT 
    COUNT(*) AS total_rows,
    COUNT(DISTINCT [FKDate]) AS distinct_fk_dates,
    MIN([FKDate]) AS min_fk_date,
    MAX([FKDate]) AS max_fk_date,
    @since_date AS filter_since_date,
    @days_ago AS days_ago_filter
FROM [DWOrchid].[dbo].[FactInventory]
WHERE [FKDate] IS NOT NULL
  AND [FKDate] >= @since_date;

