# Archived SQL

Not deployed by `scripts/deploy_procedures.py` (only `sql/10_routines/procedures/`).

| Path | Why archived |
|------|----------------|
| `procedures/etl_load_stage_*` | Old staging loads; live path is direct `etl_usp_build_*` |
| `procedures/etl_run_*` | Old SQL-orchestrated pipeline |
| `procedures/opt_usp_build_snapshot.sql` | Product-only stub; optimizer uses Python `SnapshotDataLoader` |
| `procedures/rpt_usp_compare_batches.sql` | Depends on staging tables no longer populated |
| `20_etl/` | Extract templates for retired TemplatePipeline |
| `60_optimizer_io/` | Incomplete optimizer IO views |
