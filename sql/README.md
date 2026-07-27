# SQL Server Development Guide

This repository organizes T-SQL assets by execution phase and purpose. Follow the order and conventions below to keep deployments predictable.

## Folder purpose (top-level)

- `00_migrations`: schema changes (tables, indexes) and reference data seeds; files prefixed with ordered numbers (e.g., `001_create_tables.sql`). All table creation scripts belong here.
  - **Prod cutover:** run `python scripts/migrations.py --prod` to apply ctl, snapshot, and fact tables only (skips `stg_*` migrations). See `00_migrations_prod/README.md`.
  - **Note:** `stg_*` migrations (020–024, 035) are legacy from the old Python extract→staging path. Live pipelines use `SqlSnapshotPipeline` (DWOrchid → snapshot procs) or DMS → fact → snapshot. Prefer `--prod` for new environments.
- `10_routines`: stored procedures that depend on schema being in place. Live ETL publish procs are `etl_usp_build_*`. Control procs: `ctl_usp_start_batch` / `ctl_usp_finish_batch`.
- `_archive`: retired scripts (old staging load procs, extract SQL, optimizer stub, compare-batches). Not deployed by `deploy_procedures.py`.
- `queries`: diagnostic and ad-hoc query scripts for data validation (not part of automated pipeline execution).

## Live ETL flow

1. Run `00_migrations` (or `--prod`).
2. Deploy `10_routines/procedures` via `python scripts/deploy_procedures.py`.
3. Run pipelines via `python scripts/pipeline_cli.py`:
   - Factory / Distributor inventory, Sales, Target: `ctl_usp_start_batch` → `etl_usp_build_*` (reads DWOrchid) → `ctl_usp_finish_batch`
   - Distributor Deliveries: DMS Excel → `fact_DistributorDeliveries` → `etl_usp_build_distributor_deliveries_snapshot`
4. Optimization loads `snp_*` tables via Python `SnapshotDataLoader` (not SQL `opt_usp_*`).

## Naming conventions

- Migrations use numeric prefixes (`###_description.sql`) to enforce ordering.
- Use `snake_case` for object names and files.
- Schemas by layer: `ctl` (control), `stg` (staging, legacy), `snp` (snapshot), `etl` (processing).
- Procedure files and objects use the `etl_usp_*` / `ctl_usp_*` prefix.

## ETL parameterization

- Build procs expect `@batch_id` and `@snapshot_date`. Inventory procs filter source `FKDate = @snapshot_date`.

## db.yml placeholders (Python deploy path)

When SQL files are executed via `scripts/migrations.py`, `scripts/deploy_procedures.py`, or `SQLExecutor.execute_sql_file`, DistCore substitutes `$(variable)` tokens from `src/orchestrator/config/db.yml` **before** sending the script to SQL Server.

| Placeholder | From db.yml | Example use |
|-------------|-------------|-------------|
| `$(prod_schema)` | `prod.schema` | `[$(prod_schema)].[snp_SalesSnapshot]` |
| `$(prod_database)` | `prod.database` | comments / cross-db (rare on prod) |
| `$(source_database)` | `source.database` | `[$(source_database)].[dbo].[FactInventory]` |
| `$(source_schema)` | `source.schema` | `[$(source_database)].[$(source_schema)].[DimDate]` (dims; usually `dbo`) |
| `$(schema)` | schema for the connection running the script | same as `prod_schema` when deploying to prod |
| `$(database)` | database for the connection running the script | same as `prod_database` when deploying to prod |

Example in a stored procedure:

```sql
CREATE OR ALTER PROCEDURE [$(prod_schema)].[etl_usp_build_factory_inventory_snapshot]
...
FROM [$(source_database)].[dbo].[FactInventory]
...
MERGE [$(prod_schema)].[snp_FactoryInventorySnapshot] AS target
```

Run migrations/procs against prod:

```bash
python scripts/migrations.py --prod
python scripts/deploy_procedures.py prod
```

**SSMS / sqlcmd:** placeholders are **not** expanded automatically. Either run through the Python scripts above, or manually replace `$(prod_schema)` etc. with values from your `db.yml`.


## How to run locally

- **sqlcmd** (Windows): `sqlcmd -S <server> -d <database> -i 00_migrations\000_init_schemas.sql`
- **SSMS** / **Azure Data Studio**: open the script, set database, run.
- **Python**: `python scripts/migrations.py` or `python scripts/migrations.py --prod`
