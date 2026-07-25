# Archived pipeline / SQL assets

These modules and scripts are **not** part of the live DistCore path (`SqlSnapshotPipeline` → `etl_usp_build_*`).

Kept for reference only:

- `pipeline_template.py` / `sales_template.py` — old Python extract → staging → publish
- `extract_cache.py`, `batch_reconciliation.py`, `stage_verification.py`, `staging_utils.py`
- SQL under `sql/_archive/` — staging load procs, `20_etl` extracts, `opt_usp_build_snapshot`, `rpt_usp_compare_batches`, optimizer IO views

Do not import from production code. Tests that still target these modules live under `tests/pipelines/_archive/`.
