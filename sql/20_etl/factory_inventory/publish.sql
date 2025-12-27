/*
Purpose: Publish validated factory inventory data from staging (stg.FactoryInventory) into curated snapshot table (cur.FactoryInventorySnapshot) for a given snapshot date.
Assumptions: T-SQL on SQL Server; staging table stg.FactoryInventory exists (see 020_stg_factory_inventory.sql); curated table cur.FactoryInventorySnapshot exists (see 030_cur_factory_inventory_snapshot.sql); data has been validated (via validate.sql) before publishing.
Usage: This script is typically called as part of an ETL pipeline after validation (via validate.sql). It aggregates staging data by (factory_id, product_id) and merges into the curated snapshot table. The script is idempotent: re-running with the same @batch_id and @snapshot_date will update existing records if staging data has changed, or leave them unchanged if data is identical. This allows safe reruns of the ETL pipeline without creating duplicate snapshots.
Idempotency: The MERGE statement uses (snapshot_date, factory_id, product_id) as the key. Re-running this script for the same snapshot_date will update existing rows with new batch_id and on_hand_qty values if staging data differs, or perform no-op if data is unchanged. This ensures consistent state regardless of how many times the script is executed.
Parameters:
    @batch_id BIGINT - The batch identifier for the staging data to publish (must exist in stg.FactoryInventory).
    @snapshot_date DATE - The snapshot date to assign to published records. Typically corresponds to the as-of date for inventory levels (e.g., end-of-week date).
How to run: Execute in SSMS or via sqlcmd. Should be called after validate.sql succeeds. Returns summary counts of inserted and updated rows.
*/

CREATE OR ALTER PROCEDURE etl.usp_publish_factory_inventory_snapshot
  @batch_id BIGINT,
  @snapshot_date DATE
AS
BEGIN
  SET NOCOUNT ON;

  -- Validate parameters
  IF @batch_id IS NULL
    THROW 50000, '@batch_id cannot be NULL. Provide a valid batch identifier.', 1;

  IF @snapshot_date IS NULL
    THROW 50000, '@snapshot_date cannot be NULL. Provide a valid snapshot date.', 1;

  -- Guard: Ensure staging has rows for this batch
  IF NOT EXISTS (SELECT 1 FROM stg.FactoryInventory WHERE batch_id = @batch_id)
    THROW 50000, 'No staging data found for batch_id. This should have been caught by validation (FI_EMPTY_LOAD).', 1;

  -- Table variable to capture MERGE results
  DECLARE @MergeResults TABLE (
    ActionType NVARCHAR(10),
    snapshot_date DATE,
    factory_id INT,
    product_id INT
  );

  -- Build source dataset: aggregate staging data by (factory_id, product_id)
  -- Aggregation rule: MAX(on_hand_qty) - assumes we want the peak/maximum inventory level for the snapshot.
  -- Filter out NULL keys and NULL quantities (defensive; FI_NULL_QTY validation should catch NULL quantities before this procedure runs).
  WITH AggregatedStaging AS (
    SELECT 
      factory_id,
      product_id,
      MAX(on_hand_qty) AS on_hand_qty
    FROM stg.FactoryInventory
    WHERE batch_id = @batch_id
      AND factory_id IS NOT NULL
      AND product_id IS NOT NULL
      AND on_hand_qty IS NOT NULL  -- Defensive filter: cur.FactoryInventorySnapshot.on_hand_qty is NOT NULL; FI_NULL_QTY validation should catch NULLs before publish
    GROUP BY factory_id, product_id
  )
  -- MERGE into curated snapshot table
  MERGE cur.FactoryInventorySnapshot AS target
  USING AggregatedStaging AS source
    ON target.snapshot_date = @snapshot_date
   AND target.factory_id = source.factory_id
   AND target.product_id = source.product_id
  WHEN MATCHED THEN
    UPDATE SET
      on_hand_qty = source.on_hand_qty,
      batch_id = @batch_id
      -- Note: created_at is not updated to preserve original creation timestamp
  WHEN NOT MATCHED BY TARGET THEN
    INSERT (snapshot_date, factory_id, product_id, on_hand_qty, batch_id)
    VALUES (@snapshot_date, source.factory_id, source.product_id, source.on_hand_qty, @batch_id)
  OUTPUT 
    $action AS ActionType,
    inserted.snapshot_date,
    inserted.factory_id,
    inserted.product_id
  INTO @MergeResults;

  -- Return summary counts
  SELECT 
    SUM(CASE WHEN ActionType = 'INSERT' THEN 1 ELSE 0 END) AS rows_inserted,
    SUM(CASE WHEN ActionType = 'UPDATE' THEN 1 ELSE 0 END) AS rows_updated,
    COUNT(*) AS total
  FROM @MergeResults;
END

/*
Example Execution:

-- Example 1: Publish batch 123 for snapshot date 2024-01-15
EXEC etl.usp_publish_factory_inventory_snapshot @batch_id = 123, @snapshot_date = '2024-01-15';

-- Example 2: Verify published data
SELECT 
    snapshot_date,
    factory_id,
    product_id,
    on_hand_qty,
    batch_id,
    created_at
FROM cur.FactoryInventorySnapshot
WHERE snapshot_date = '2024-01-15'
ORDER BY factory_id, product_id;

-- Example 3: Check for discrepancies between staging and curated
SELECT 
    'Missing in curated' AS issue_type,
    stg.factory_id,
    stg.product_id
FROM (
    SELECT DISTINCT factory_id, product_id
    FROM stg.FactoryInventory
    WHERE batch_id = 123
) AS stg
LEFT JOIN cur.FactoryInventorySnapshot AS cur
    ON cur.snapshot_date = '2024-01-15'
   AND cur.factory_id = stg.factory_id
   AND cur.product_id = stg.product_id
WHERE cur.factory_id IS NULL

UNION ALL

SELECT 
    'Extra in curated' AS issue_type,
    cur.factory_id,
    cur.product_id
FROM cur.FactoryInventorySnapshot AS cur
LEFT JOIN (
    SELECT DISTINCT factory_id, product_id
    FROM stg.FactoryInventory
    WHERE batch_id = 123
) AS stg
    ON stg.factory_id = cur.factory_id
   AND stg.product_id = cur.product_id
WHERE cur.snapshot_date = '2024-01-15'
  AND stg.factory_id IS NULL;

-- Example 4: Rerun publish (idempotent - will update if data changed, no-op if unchanged)
EXEC etl.usp_publish_factory_inventory_snapshot @batch_id = 123, @snapshot_date = '2024-01-15';
-- Safe to rerun - will update existing records or leave unchanged if data is identical
*/

