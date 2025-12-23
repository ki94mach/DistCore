# SQL Server Development Guide

This repository organizes T-SQL assets by execution phase and purpose. Follow the order and conventions below to keep deployments predictable.

## Folder purpose (top-level)

- `00_migrations`: schema changes and reference data seeds; files prefixed with ordered numbers (e.g., `001_create_tables.sql`).
- `10_routines`: stored procedures, functions, and views that depend on schema being in place.
- `20_etl`: batch and snapshot load scripts; orchestrated after routines exist.
- `30_dq_rules`: data-quality checks (profiling, constraints, exception logging).
- `40_snapshot_builder`: logic to assemble curated snapshots from staged data.
- `50_policy`: policy- or rules-engine artifacts that drive downstream logic.
- `60_optimizer_io`: performance helpers (indexes, stats refresh, IO tuning).
- `90_reporting`: reporting/serving layer objects.
- `_archive`: retired or historical scripts; not executed automatically.

## Execution order

1. Run `00_migrations` in numeric order.
2. Deploy `10_routines`.
3. Execute pipelines: `20_etl` → `30_dq_rules` → `40_snapshot_builder` → `50_policy` → `60_optimizer_io` → `90_reporting`.
4. `_archive` is excluded from regular runs.

## Naming conventions

- Migrations use numeric prefixes (`###_description.sql`) to enforce ordering.
- Use `snake_case` for object names and files.
- Schemas by layer: `ctl` (control), `stg` (staging), `cur` (curated), `dq` (data quality), `etl` (processing), `pol` (policy), `opt` (optimizer/IO), `rpt` (reporting).

## ETL parameterization

- ETL scripts expect parameters such as `@batch_id` (unique load identifier) and `@snapshot_date` (date for point-in-time loads). Provide them via `sqlcmd` variables or SSMS/Azure Data Studio query parameters. Default to `NULL` only when the script explicitly supports it.

## How to run locally

- **sqlcmd** (Windows): `sqlcmd -S <server> -d <database> -i 00_migrations\001_create_tables.sql -v batch_id=123 snapshot_date="2024-01-01"`
- **SSMS**: open the script, set database, use Query Parameters (`Ctrl+Shift+M`) to fill `batch_id`, `snapshot_date`, then execute.
- **Azure Data Studio**: open the script, set connection, use Run With Parameters to supply `batch_id`/`snapshot_date`, then run.
