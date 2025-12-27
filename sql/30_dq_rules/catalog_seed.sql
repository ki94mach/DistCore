/*
Purpose: Seed dq.RuleCatalog with initial Factory Inventory data quality rules.
Assumptions: T-SQL on SQL Server; `dq` schema and dq.RuleCatalog table exist (see 040_dq_tables.sql); requires permissions to INSERT/UPDATE into dq.RuleCatalog.
Usage: This script is idempotent: re-running will update existing rules if metadata has changed, or leave them unchanged if identical. Safe to execute multiple times.
How to run: Execute in SSMS or via sqlcmd against the target database. Should be run after 040_dq_tables.sql migration.
*/

-- Seed Factory Inventory rules using MERGE for idempotent upsert
MERGE dq.RuleCatalog AS target
USING (
    SELECT N'FI_NULL_KEYS' AS rule_name, N'stg.FactoryInventory' AS target_object, N'HARD' AS severity, 
           N'Validates that factory_id and product_id are not NULL. Ensures key columns are populated for referential integrity and data completeness.' AS description, 
           1 AS is_enabled
    UNION ALL
    SELECT N'FI_NEGATIVE_QTY', N'stg.FactoryInventory', N'HARD', 
           N'Validates that on_hand_qty is not negative. Prevents invalid inventory quantities that could cause downstream calculation errors.', 
           1
    UNION ALL
    SELECT N'FI_DUP_KEYS', N'stg.FactoryInventory', N'HARD', 
           N'Validates that there are no duplicate (factory_id, product_id) combinations within a batch. Ensures data uniqueness for snapshot creation.', 
           1
    UNION ALL
    SELECT N'FI_EMPTY_LOAD', N'stg.FactoryInventory', N'HARD', 
           N'Validates that at least one row was loaded for the batch. Prevents empty data loads that may indicate ETL pipeline failures.', 
           1
    UNION ALL
    SELECT N'FI_NULL_QTY', N'stg.FactoryInventory', N'HARD', 
           N'Validates that on_hand_qty is not NULL for any row in the batch. Prevents curated NOT NULL violations.', 
           1
) AS source
ON target.rule_name = source.rule_name
WHEN MATCHED THEN
    UPDATE SET
        target_object = source.target_object,
        severity = source.severity,
        description = source.description,
        is_enabled = source.is_enabled
        -- Note: created_at is preserved to maintain original creation timestamp
WHEN NOT MATCHED BY TARGET THEN
    INSERT (rule_name, target_object, severity, description, is_enabled)
    VALUES (source.rule_name, source.target_object, source.severity, source.description, source.is_enabled);

-- Return summary of seeded rules
SELECT 
    rule_name,
    target_object,
    severity,
    description,
    is_enabled,
    created_at
FROM dq.RuleCatalog
WHERE rule_name LIKE N'FI_%'
ORDER BY rule_name;

/*
Example Execution:

-- Execute the entire script to seed/update Factory Inventory rules

-- Example 1: Verify all Factory Inventory rules are present
SELECT 
    rule_name,
    target_object,
    severity,
    description,
    is_enabled,
    created_at
FROM dq.RuleCatalog
WHERE target_object = N'stg.FactoryInventory'
ORDER BY rule_name;

-- Example 2: Check rule status
SELECT 
    rule_name,
    severity,
    CASE WHEN is_enabled = 1 THEN 'ENABLED' ELSE 'DISABLED' END AS status,
    description
FROM dq.RuleCatalog
WHERE rule_name LIKE N'FI_%'
ORDER BY severity, rule_name;

-- Example 3: Re-run seed (idempotent - safe to execute multiple times)
-- Execute the entire script again - will update if metadata changed, no-op if unchanged
*/
