/*
Purpose: Create optimization output tables to store solver results and decisions. This script creates the initial table structure for recording optimization decisions made by the solver engine.
Grain: One row per optimization decision. A single optimization run may produce multiple decisions (e.g., multiple product allocations, transfers between factories and distributors).
Assumptions: T-SQL on SQL Server; `opt` schema already exists (see 000_init_schemas.sql); requires permissions to create tables and indexes. The run_id column references opt.RunRegistry.run_id (see 050_run_registry.sql).
Usage: This table stores the output decisions from optimization solver runs. Each decision represents an allocation, transfer, or other action determined by the solver. The decision_type field categorizes the type of decision (e.g., 'ALLOCATE', 'TRANSFER', 'HOLD'). Decisions are linked to a specific optimization run via run_id for traceability and audit purposes.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create opt.OptimizationDecision if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'opt' AND t.name = N'OptimizationDecision'
)
BEGIN
    CREATE TABLE opt.OptimizationDecision (
        decision_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_OptimizationDecision PRIMARY KEY,
        run_id BIGINT NOT NULL,
        decision_type NVARCHAR(50) NOT NULL,
        from_factory_id INT NULL,
        to_distributor_id INT NULL,
        product_id INT NOT NULL,
        qty DECIMAL(18, 3) NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_OptimizationDecision_created_at DEFAULT SYSUTCDATETIME()
        
        -- TODO: Add foreign key constraint to opt.RunRegistry once table relationship is confirmed
        -- CONSTRAINT FK_OptimizationDecision_RunRegistry FOREIGN KEY (run_id) REFERENCES opt.RunRegistry (run_id)
        
        -- TODO: Consider additional columns for future enhancements:
        --   - Priority or ranking score from solver
        --   - Cost or objective function value
        --   - Constraint binding indicators (which constraints were active)
        --   - Execution status (PENDING, EXECUTED, CANCELLED)
        --   - Execution timestamp (when decision was acted upon)
        --   - Override flags or manual adjustments
        --   - Unit of measure (if qty needs UOM context)
        --   - Comments or notes field
    );
END;
GO

-- Composite index on (run_id, product_id) for efficient lookups by run and product
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.tables t ON i.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'opt' AND t.name = N'OptimizationDecision' AND i.name = N'IX_OptimizationDecision_RunId_ProductId'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_OptimizationDecision_RunId_ProductId
        ON opt.OptimizationDecision (run_id, product_id);
END;
GO

-- TODO: Consider additional indexes based on query patterns:
--   - Index on decision_type if filtering by decision type is common
--   - Index on (from_factory_id, to_distributor_id) if querying by transfer paths
--   - Index on created_at for time-based queries
--   - Composite index on (run_id, decision_type) if filtering by both is common

/*
Example Usage:

-- Example 1: Insert optimization decisions for a run
-- Note: In practice, this would typically be done via bulk insert or from the solver output
INSERT INTO opt.OptimizationDecision (run_id, decision_type, from_factory_id, to_distributor_id, product_id, qty)
VALUES 
    (1, N'ALLOCATE', 101, 201, 1001, 500.000),
    (1, N'ALLOCATE', 101, 202, 1001, 300.000),
    (1, N'TRANSFER', 102, NULL, 1002, 200.000);

-- Example 2: Query decisions for a specific run
SELECT 
    decision_id,
    run_id,
    decision_type,
    from_factory_id,
    to_distributor_id,
    product_id,
    qty,
    created_at
FROM opt.OptimizationDecision
WHERE run_id = 1
ORDER BY product_id, decision_type;

-- Example 3: Aggregate decisions by product for a run
SELECT 
    run_id,
    product_id,
    decision_type,
    SUM(qty) AS total_qty,
    COUNT(*) AS decision_count
FROM opt.OptimizationDecision
WHERE run_id = 1
GROUP BY run_id, product_id, decision_type
ORDER BY product_id, decision_type;

-- Example 4: Join with RunRegistry to get run context
SELECT 
    d.decision_id,
    d.run_id,
    r.snapshot_date,
    r.status AS run_status,
    d.decision_type,
    d.product_id,
    d.qty,
    d.created_at
FROM opt.OptimizationDecision AS d
INNER JOIN opt.RunRegistry AS r
    ON d.run_id = r.run_id
WHERE r.snapshot_date = '2024-01-15'
ORDER BY d.product_id, d.decision_type;
*/

