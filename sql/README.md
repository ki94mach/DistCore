# SQL Server Development Guide

This repository organizes T-SQL assets by execution phase and purpose. Follow the order and conventions below to keep deployments predictable.

## Folder purpose (top-level)

- `00_migrations`: schema changes (tables, indexes) and reference data seeds; files prefixed with ordered numbers (e.g., `001_create_tables.sql`). All table creation scripts belong here.
  - **Prod cutover:** run `python scripts/migrations.py --prod` to apply ctl, snapshot, and fact tables only (skips `stg_*` migrations). See `00_migrations_prod/README.md`.
- `10_routines`: stored procedures, functions, and views that depend on schema being in place. **All stored procedures go in `10_routines/procedures/`, regardless of their purpose (ETL, reporting, optimization, etc.).**
- `20_etl`: batch and snapshot load scripts (queries, templates); orchestrated after routines exist. Contains extraction queries and ETL templates used by pipelines.
- `50_policy`: policy- or rules-engine artifacts that drive downstream logic.
- `60_optimizer_io`: performance helpers (indexes, stats refresh, IO tuning) and optimizer input/output views. Table creation scripts go in `00_migrations`.
- `90_queries`: diagnostic and ad-hoc query scripts for data validation, inspection, and troubleshooting. These are not part of the automated pipeline execution.
- `_archive`: retired or historical scripts; not executed automatically.

## Execution order

1. Run `00_migrations` in numeric order.
2. Deploy `10_routines`.
3. Execute pipelines: `20_etl` → `50_policy` → `60_optimizer_io`.
4. Use `90_queries` for ad-hoc diagnostics and validation (not part of automated execution).
5. `_archive` is excluded from regular runs.

## Naming conventions

- Migrations use numeric prefixes (`###_description.sql`) to enforce ordering.
- Use `snake_case` for object names and files.
- Schemas by layer: `ctl` (control), `stg` (staging), `snp` (snapshot), `etl` (processing), `pol` (policy), `opt` (optimizer/IO), `rpt` (reporting).

## ETL parameterization

- ETL scripts expect parameters such as `@batch_id` (unique load identifier) and `@snapshot_date` (date for point-in-time loads). Provide them via `sqlcmd` variables or SSMS/Azure Data Studio query parameters. Default to `NULL` only when the script explicitly supports it.

## How to run locally

- **sqlcmd** (Windows): `sqlcmd -S <server> -d <database> -i 00_migrations\001_create_tables.sql -v batch_id=123 snapshot_date="2024-01-01"`
- **SSMS**: open the script, set database, use Query Parameters (`Ctrl+Shift+M`) to fill `batch_id`, `snapshot_date`, then execute.
- **Azure Data Studio**: open the script, set connection, use Run With Parameters to supply `batch_id`/`snapshot_date`, then run.
