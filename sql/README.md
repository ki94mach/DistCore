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

## How to run locally

- **sqlcmd** (Windows): `sqlcmd -S <server> -d <database> -i 00_migrations\000_init_schemas.sql`
- **SSMS** / **Azure Data Studio**: open the script, set database, run.
- **Python**: `python scripts/migrations.py` or `python scripts/migrations.py --prod`
