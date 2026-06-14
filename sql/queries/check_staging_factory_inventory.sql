/*
Purpose: Check the count of imported records in staging table for Factory Inventory.
Assumptions: Run this query on the staging database (where [$(prod_schema)].[stg_FactoryInventory] exists).
Usage: Check record counts by batch_id, with optional filtering by batch_id.
*/

-- Option 1: Count by batch_id (all batches)
SELECT 
    batch_id,
    COUNT(*) AS imported_record_count,
    MIN(ingested_at) AS first_ingested,
    MAX(ingested_at) AS last_ingested,
    MIN(as_of_datetime) AS min_as_of_datetime,
    MAX(as_of_datetime) AS max_as_of_datetime
FROM [$(prod_schema)].[stg_FactoryInventory]
GROUP BY batch_id
ORDER BY batch_id DESC;

-- Option 2: Count for a specific batch_id (replace 123 with your batch_id)
DECLARE @batch_id BIGINT = 123;  -- Replace with your batch_id

SELECT 
    batch_id,
    COUNT(*) AS imported_record_count,
    MIN(ingested_at) AS first_ingested,
    MAX(ingested_at) AS last_ingested,
    MIN(as_of_datetime) AS min_as_of_datetime,
    MAX(as_of_datetime) AS max_as_of_datetime,
    -- Additional quality checks
    SUM(CASE WHEN factory_id IS NULL OR product_id IS NULL THEN 1 ELSE 0 END) AS null_key_count,
    SUM(CASE WHEN on_hand_qty < 0 THEN 1 ELSE 0 END) AS negative_qty_count
FROM [$(prod_schema)].[stg_FactoryInventory]
WHERE batch_id = @batch_id
GROUP BY batch_id;

-- Option 3: Total count across all batches
SELECT 
    COUNT(*) AS total_imported_records,
    COUNT(DISTINCT batch_id) AS total_batches,
    MIN(ingested_at) AS earliest_ingested,
    MAX(ingested_at) AS latest_ingested
FROM [$(prod_schema)].[stg_FactoryInventory];

-- Option 4: Latest batch details (most recent batch)
SELECT TOP 1
    batch_id,
    COUNT(*) AS imported_record_count,
    MIN(ingested_at) AS first_ingested,
    MAX(ingested_at) AS last_ingested,
    MIN(as_of_datetime) AS min_as_of_datetime,
    MAX(as_of_datetime) AS max_as_of_datetime
FROM [$(prod_schema)].[stg_FactoryInventory]
GROUP BY batch_id
ORDER BY batch_id DESC;

