/* 
Purpose: Ensure required database schemas exist for DistCore.
Dependencies: Requires connection to target SQL Server database with permissions to create schemas.
How to run: Execute this script in SQL Server Management Studio (SSMS) or via sqlcmd against the desired database.
*/

-- Create schemas if they do not already exist
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ctl')
    EXEC('CREATE SCHEMA [ctl]');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'stg')
    EXEC('CREATE SCHEMA [stg]');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cur')
    EXEC('CREATE SCHEMA [cur]');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'dq')
    EXEC('CREATE SCHEMA [dq]');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'etl')
    EXEC('CREATE SCHEMA [etl]');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'pol')
    EXEC('CREATE SCHEMA [pol]');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'opt')
    EXEC('CREATE SCHEMA [opt]');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'rpt')
    EXEC('CREATE SCHEMA [rpt]');
GO

