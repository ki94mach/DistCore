"""Terminal access tool for ETL pipelines."""

import sys
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Set UTF-8 encoding for Windows terminal to display Farsi characters
if sys.platform == 'win32':
    # Method 1: Try to reconfigure stdout/stderr
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    if hasattr(sys.stderr, 'reconfigure'):
        try:
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass
    
    # Method 2: Set environment variables
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONLEGACYWINDOWSSTDIO'] = '0'
    
    # Method 3: Try to change console code page to UTF-8 (65001)
    try:
        import subprocess
        # Change console code page to UTF-8
        subprocess.run(['chcp', '65001'], shell=True, capture_output=True, check=False)
    except Exception:
        pass
    
    # Method 4: Set locale if available
    try:
        import locale
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except Exception:
        try:
            locale.setlocale(locale.LC_ALL, '')
        except Exception:
            pass

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.pipelines.distributor_inventory import DistributorInventoryPipeline
from src.orchestrator.pipelines.sales_snapshot import SalesSnapshotPipeline
from src.orchestrator.pipelines.target import TargetPipeline
from src.orchestrator.pipelines.distributor_deliveries import DistributorDeliveriesPipeline
from src.orchestrator.pipelines.utils.extract_cache import (
    EXTRACT_FILENAME,
    MANIFEST_FILENAME,
    ExtractCache,
    get_default_cache_root,
)
from src.orchestrator.pipelines.utils.stage_verification import StageVerificationError
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory
from src.orchestrator.services.sql_server_db.executors.sql_executor import SQLExecutor
from src.orchestrator.services.vpn import ensure_vpn_connected
from src.orchestrator.ui.terminal_ui import (
    Colors,
    print_header,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_action,
    print_menu_item,
    print_prompt,
    colorize
)


# Pipeline registry - easily extensible for future pipelines
PIPELINES = {
    '1': {
        'name': 'Factory Inventory',
        'class': FactoryInventoryPipeline,
        'batch_type': 'FACTORY_INVENTORY'
    },
    '2': {
        'name': 'Distributor Inventory',
        'class': DistributorInventoryPipeline,
        'batch_type': 'DISTRIBUTOR_INVENTORY'
    },
    '3': {
        'name': 'Sales Snapshot',
        'class': SalesSnapshotPipeline,
        'batch_type': 'SALES_SNAPSHOT'
    },
    '4': {
        'name': 'Target',
        'class': TargetPipeline,
        'batch_type': 'TARGET'
    },
    '5': {
        'name': 'Distributor Deliveries',
        'class': DistributorDeliveriesPipeline,
        'batch_type': 'DISTRIBUTOR_DELIVERIES'
    }
}

SQL_SOURCE_PIPELINES = frozenset({
    'Factory Inventory',
    'Distributor Inventory',
    'Sales Snapshot',
    'Target',
})


def is_sql_source_pipeline(pipeline_info) -> bool:
    return pipeline_info['name'] in SQL_SOURCE_PIPELINES


def prompt_force_extract() -> bool:
    choice = print_prompt("Force re-extract from source? (y/N): ").strip().lower()
    return choice == 'y'


def prompt_force_historical_reload() -> bool:
    choice = print_prompt(
        "Force full reload (erase ALL fact rows incl. 1404)? Normal runs keep 1404 (y/N): "
    ).strip().lower()
    return choice == 'y'


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {secs}s"


def format_file_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 ** 2:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 ** 3:
        return f"{num_bytes / (1024 ** 2):.1f} MB"
    return f"{num_bytes / (1024 ** 3):.2f} GB"


def make_pipeline_log_fn(pipeline_name: str):
    """Build a timestamped log callback for pipeline progress messages."""

    def log_fn(message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        print_info(f"[{pipeline_name}] [{stamp}] {message}")

    return log_fn


def print_kv(label: str, value: str, indent: int = 2) -> None:
    prefix = " " * indent
    print(colorize(f"{prefix}{label}: ", Colors.DIM) + colorize(str(value), Colors.WHITE))


STAGING_MODE_LABELS = {
    'full': 'Full staging (extract → cache → load → verify)',
    'extract_only': 'Extract to cache only',
    'load_from_cache': 'Load staging from cache',
}


def staging_mode_label(staging_mode: str) -> str:
    return STAGING_MODE_LABELS.get(staging_mode, staging_mode)


def prompt_snapshot_date() -> Optional[date]:
    """Ask for snapshot date; Enter means today (None → pipeline default)."""
    print_info("Snapshot date (used for filters and publish):")
    print(colorize("  Enter = today", Colors.DIM))
    raw = print_prompt("  YYYY-MM-DD or Enter: ").strip()
    if not raw:
        return None
    try:
        year, month, day = map(int, raw.split('-'))
        return date(year, month, day)
    except ValueError:
        print_warning("Invalid date — using today.")
        return None


def print_run_plan(
    pipeline_info,
    *,
    operation: str,
    batch_id: Optional[int] = None,
    snapshot_date: Optional[date] = None,
    config: Optional[dict] = None,
    staging_mode: Optional[str] = None,
) -> None:
    """Single pre-run summary (avoids repeated headers)."""
    print_header("Ready to run", Colors.BRIGHT_BLUE)
    print_kv("Pipeline", pipeline_info['name'])
    print_kv("Operation", operation)
    if batch_id is not None:
        print_kv("Batch ID", batch_id)
    snap = snapshot_date or (config or {}).get('snapshot_date') or date.today()
    print_kv("Snapshot date", snap.isoformat() if hasattr(snap, 'isoformat') else snap)

    if config and staging_mode:
        print_kv("Batch size", f"{config.get('batch_size', 10000):,}")
        if is_sql_source_pipeline(pipeline_info):
            print_kv("Verify retries", str(config.get('max_verification_retries', 3)))
            if staging_mode != 'load_from_cache':
                print_kv(
                    "Re-extract from source",
                    "yes" if config.get('force_extract') else "no (use cache if valid)",
                )
            if pipeline_info['name'] in ('Factory Inventory', 'Distributor Inventory'):
                if config.get('single_date_only'):
                    load_mode = "Single date only"
                elif config.get('incremental'):
                    load_mode = "Incremental"
                else:
                    load_mode = "Full load"
                print_kv("Data window", load_mode)
            elif pipeline_info['name'] == 'Distributor Deliveries':
                print_kv(
                    "Reload historical 1404",
                    "yes" if config.get('force_historical_reload') else "no (keep cached 1404)",
                )
            elif pipeline_info['name'] == 'Sales Snapshot':
                print_kv("Data window", "Rolling ~6 months to snapshot date")
            elif pipeline_info['name'] == 'Target':
                print_kv("Data window", "Current Jalali year")
    print()


def get_cache_for_pipeline(pipeline, batch_id: int) -> ExtractCache:
    cache_dir = getattr(
        pipeline,
        '_cache_dir',
        get_default_cache_root(
            Path(__file__).resolve().parent.parent
            / 'src'
            / 'orchestrator'
            / 'pipelines'
            / 'pipeline_template.py'
        ),
    )
    return ExtractCache(cache_dir, pipeline.batch_type, batch_id)


def print_cache_status(pipeline, batch_id: Optional[int] = None) -> None:
    """Print extract cache manifest and file sizes for a batch."""
    bid = batch_id if batch_id is not None else getattr(pipeline, 'batch_id', None)
    if not bid:
        print_warning("No batch ID available to inspect cache.")
        return

    cache = get_cache_for_pipeline(pipeline, bid)
    print_header(f"Extract cache — {pipeline.batch_type} / batch {bid}", Colors.BRIGHT_BLUE)
    print_kv("Cache directory", str(cache.batch_cache_dir))

    if not cache.batch_cache_dir.is_dir():
        print_warning("No cache directory found for this batch.")
        print_info("Run 'Extract to cache' or a full load to create cache files.")
        return

    manifest = cache.read_manifest()
    if manifest:
        print_kv("Status", manifest.get("status", "—"))
        print_kv("Last verified step", manifest.get("last_verified_step") or "—")
        print_kv("Row count", f"{manifest.get('row_count', 0):,}")
        if manifest.get("source_row_count") is not None:
            print_kv("Source row count (verified)", f"{manifest['source_row_count']:,}")
        print_kv("Created at", manifest.get("created_at", "—"))
        columns = manifest.get("column_names") or []
        if columns:
            print_kv("Columns", ", ".join(columns))
    else:
        print_warning(f"No {MANIFEST_FILENAME} in cache directory.")

    extract_path = cache.batch_cache_dir / EXTRACT_FILENAME
    if extract_path.is_file():
        print_kv("extract.pkl size", format_file_size(extract_path.stat().st_size))
    else:
        print_warning(f"{EXTRACT_FILENAME} not found.")
    print()


def print_run_footer(
    pipeline_info,
    pipeline,
    staging_mode: Optional[str],
    elapsed: float,
    success: bool,
) -> None:
    """Short result line plus cache hints only when useful."""
    outcome = colorize("OK", Colors.BRIGHT_GREEN) if success else colorize("FAILED", Colors.BRIGHT_RED)
    batch_id = getattr(pipeline, 'batch_id', '—')
    op = staging_mode_label(staging_mode) if staging_mode else "Publish"
    print()
    print(
        colorize(f"  {outcome}", Colors.WHITE)
        + colorize(f"  |  batch {batch_id}  |  {format_duration(elapsed)}  |  {op}", Colors.DIM)
    )

    if not is_sql_source_pipeline(pipeline_info) or not staging_mode:
        print()
        return

    if success and staging_mode == 'extract_only':
        print_info("Cache written for this batch (details below).")
        print_cache_status(pipeline)
    elif success and staging_mode in ('full', 'load_from_cache'):
        print_info("Cache cleared after successful load (normal).")
    elif not success and getattr(pipeline, 'batch_id', None):
        cache = get_cache_for_pipeline(pipeline, pipeline.batch_id)
        if cache.batch_cache_dir.is_dir():
            print_warning(
                "Extract cache may still exist — retry menu «Load staging from cache» "
                "with the same batch ID."
            )
            print_cache_status(pipeline)
        else:
            print_warning(
                "Extract cache is missing for this batch. Re-run «Extract to cache only» "
                "before loading staging."
            )
    print()


def build_pipeline_kwargs(pipeline_info, batch_id, snapshot_date, log: bool = True) -> dict:
    kwargs = {
        'batch_id': batch_id,
        'snapshot_date': snapshot_date,
        'triggered_by': 'MANUAL_TEST',
        'database_type': 'prod',
    }
    if pipeline_info['name'] == 'Distributor Deliveries':
        kwargs['log_fn'] = print_info if log else None
        kwargs['show_progress'] = log
    elif log:
        kwargs['log_fn'] = make_pipeline_log_fn(pipeline_info['name'])
        kwargs['show_progress'] = True
    return kwargs


def build_load_stage_kwargs(pipeline_info, config, staging_mode: str) -> dict:
    """Build load_stage keyword arguments for a pipeline and staging mode."""
    if is_sql_source_pipeline(pipeline_info):
        return {}

    kwargs = {
        'batch_size': config['batch_size'],
        'max_verification_retries': config.get('max_verification_retries', 3),
    }

    if pipeline_info['name'] in ('Factory Inventory', 'Distributor Inventory', 'Target'):
        kwargs['incremental'] = config['incremental']
        kwargs['single_date_only'] = config['single_date_only']

    if staging_mode == 'extract_only':
        kwargs['extract_only'] = True
        kwargs['force_extract'] = config.get('force_extract', False)
    elif staging_mode == 'load_from_cache':
        kwargs['load_from_cache_only'] = True
    elif staging_mode == 'full' and is_sql_source_pipeline(pipeline_info):
        kwargs['force_extract'] = config.get('force_extract', False)

    return kwargs


def invoke_load_stage(pipeline_info, pipeline, config, staging_mode: str = 'full') -> None:
    """Call load_stage with the correct kwargs for each pipeline type."""
    if is_sql_source_pipeline(pipeline_info):
        pipeline.load_stage(**build_load_stage_kwargs(pipeline_info, config, staging_mode))
    elif pipeline_info['name'] == 'Distributor Deliveries':
        pipeline.load_stage(
            batch_size=config['batch_size'],
            force_historical_reload=config.get('force_historical_reload', False),
        )
    else:
        pipeline.load_stage()


def start_new_batch(batch_type: str, triggered_by: str = 'MANUAL_TEST', database_type: str = 'prod', pipeline_name: str = None) -> int:
    """Start a new batch and return the batch_id."""
    connection_factory = DBConnectionFactory()
    sql_executor = SQLExecutor(connection_factory)

    result = sql_executor.execute_procedure_with_output(
        procedure_name=connection_factory.qualify('ctl_usp_start_batch', database_type),
        parameters={
            'batch_type': batch_type,
            'triggered_by': triggered_by
        },
        output_parameters=['batch_id'],
        database_type=database_type
    )
    
    batch_id = result['batch_id']
    if pipeline_name:
        print_success(f"[{pipeline_name}] Created new batch ID: {batch_id}")
    else:
        print_success(f"Created new batch ID: {batch_id}")
    return batch_id


def select_pipeline():
    """First layer: Select a pipeline."""
    print_header("Available Pipelines", Colors.BRIGHT_CYAN)
    for key, pipeline_info in PIPELINES.items():
        print_menu_item(key, pipeline_info['name'], Colors.BRIGHT_WHITE)
    print()
    print_menu_item('a', 'Full Automate Pipeline (Run All)', Colors.BRIGHT_GREEN)
    print_menu_item('q', 'Quit', Colors.BRIGHT_YELLOW)
    
    choice = print_prompt("\nSelect pipeline: ").strip().lower()
    if choice == 'q':
        return None
    if choice == 'a':
        return 'ALL'
    return PIPELINES.get(choice)


def select_operation(pipeline_info):
    """Choose what to run for the selected pipeline."""
    print_header(f"{pipeline_info['name']}", Colors.BRIGHT_CYAN)
    if is_sql_source_pipeline(pipeline_info):
        print(colorize("  Snapshot (reads DWOrchid directly via stored proc)", Colors.DIM))
        print_menu_item('1', 'Publish snapshot only', Colors.BRIGHT_WHITE)
        print_menu_item('2', 'Full pipeline (prepare batch + publish)', Colors.BRIGHT_WHITE)
    elif pipeline_info['name'] == 'Distributor Deliveries':
        print_menu_item('1', 'Load fact table from DMS', Colors.BRIGHT_WHITE)
        print_menu_item('2', 'Publish snapshot', Colors.BRIGHT_WHITE)
        print_menu_item('3', 'Full pipeline (load fact + publish)', Colors.BRIGHT_WHITE)
    print()
    print_menu_item('b', 'Back', Colors.BRIGHT_YELLOW)
    print_menu_item('q', 'Quit', Colors.BRIGHT_YELLOW)

    return print_prompt("\nChoice: ").strip().lower()


def configure_staging(pipeline_info, staging_mode: str = 'full'):
    """Run options; SQL pipelines only need snapshot date."""
    print_header("Options", Colors.BRIGHT_BLUE)

    snapshot_date = prompt_snapshot_date()

    if is_sql_source_pipeline(pipeline_info):
        return {'snapshot_date': snapshot_date}

    batch_size = 10000
    incremental = True
    single_date_only = False

    ask_load_window = (
        staging_mode in ('full', 'extract_only')
        and pipeline_info['name'] in ('Factory Inventory', 'Distributor Inventory')
    )
    ask_batch_size = (
        staging_mode in ('full', 'extract_only')
        and pipeline_info['name'] in (
            'Factory Inventory',
            'Distributor Inventory',
            'Sales Snapshot',
            'Target',
            'Distributor Deliveries',
        )
    )

    if ask_batch_size and pipeline_info['name'] in ('Factory Inventory', 'Distributor Inventory'):
        batch_size_str = print_prompt("Insert batch size (default 10000): ").strip()
        if batch_size_str:
            try:
                batch_size = int(batch_size_str)
            except ValueError:
                print_warning("Invalid — using 10000.")

    if ask_load_window:
        print_info("Data window:")
        print_menu_item('1', 'Incremental (after latest date in fact table)', Colors.WHITE)
        print_menu_item('2', 'Single snapshot date only', Colors.WHITE)
        print_menu_item('3', 'Full reload (all source rows)', Colors.WHITE)
        mode_choice = print_prompt("  1/2/3 (default 1): ").strip() or "1"
        if mode_choice == "2":
            incremental = False
            single_date_only = True
        elif mode_choice == "3":
            incremental = False
            single_date_only = False
    elif pipeline_info['name'] == 'Sales Snapshot' and staging_mode != 'load_from_cache':
        print_info("Data window: rolling ~6 months ending on snapshot date (fixed).")
        incremental = False
        single_date_only = False
    elif pipeline_info['name'] == 'Target' and staging_mode != 'load_from_cache':
        print_info("Data window: current Jalali year (fixed).")
        incremental = False
        single_date_only = False

    force_extract = False
    force_historical_reload = False
    max_verification_retries = 3
    if pipeline_info['name'] == 'Distributor Deliveries' and staging_mode == 'full':
        force_historical_reload = prompt_force_historical_reload()
    if is_sql_source_pipeline(pipeline_info):
        if staging_mode in ('full', 'extract_only'):
            force_extract = prompt_force_extract()
        if staging_mode != 'load_from_cache':
            retries_str = print_prompt("Verify retries if counts mismatch (default 3): ").strip()
        else:
            retries_str = print_prompt("Verify retries for cache↔staging (default 3): ").strip()
        if retries_str:
            try:
                max_verification_retries = max(1, int(retries_str))
            except ValueError:
                print_warning("Invalid — using 3.")

    return {
        'snapshot_date': snapshot_date,
        'batch_size': batch_size,
        'incremental': incremental,
        'single_date_only': single_date_only,
        'force_extract': force_extract,
        'force_historical_reload': force_historical_reload,
        'max_verification_retries': max_verification_retries,
    }


def configure_publish(pipeline_info):
    print_header("Publish options", Colors.BRIGHT_BLUE)
    return {'snapshot_date': prompt_snapshot_date()}


def configure_batch(pipeline_info, staging_mode: Optional[str] = None) -> Optional[int]:
    """Pick or create the batch ID for this run."""
    print_header("Batch", Colors.BRIGHT_BLUE)

    if staging_mode == 'load_from_cache':
        print_info("Use the batch that already has extract.pkl on disk.")
        batch_id_str = print_prompt("Batch ID: ").strip()
        try:
            return int(batch_id_str)
        except ValueError:
            print_error("A numeric batch ID is required.")
            raise ValueError("batch_id is required for load_from_cache")

    print_menu_item('1', 'Create new batch (recommended)', Colors.BRIGHT_WHITE)
    print_menu_item('2', 'Reuse existing batch ID', Colors.WHITE)
    choice = print_prompt("  1 or 2 (default 1): ").strip() or "1"

    if choice == "2":
        batch_id_str = print_prompt("Batch ID: ").strip()
        try:
            return int(batch_id_str)
        except ValueError:
            print_error("Invalid batch ID.")
            raise ValueError("invalid batch_id")

    print_action("Creating batch...")
    return start_new_batch(
        batch_type=pipeline_info['batch_type'],
        triggered_by='MANUAL_TEST',
        database_type='prod',
        pipeline_name=pipeline_info['name'],
    )


def run_staging(pipeline_info, config, staging_mode: str = 'full'):
    """Run the staging layer."""
    batch_id = configure_batch(pipeline_info, staging_mode)
    print_run_plan(
        pipeline_info,
        operation=staging_mode_label(staging_mode),
        batch_id=batch_id,
        config=config,
        staging_mode=staging_mode,
    )

    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, config['snapshot_date'])
    )

    if staging_mode == 'load_from_cache' and is_sql_source_pipeline(pipeline_info):
        print_cache_status(pipeline)

    started = time.monotonic()
    print_action("Running...")
    try:
        invoke_load_stage(pipeline_info, pipeline, config, staging_mode)
        elapsed = time.monotonic() - started
        print_run_footer(pipeline_info, pipeline, staging_mode, elapsed, success=True)
        return pipeline
    except Exception as e:
        elapsed = time.monotonic() - started
        print_run_footer(pipeline_info, pipeline, staging_mode, elapsed, success=False)
        if isinstance(e, StageVerificationError):
            print_warning("Retry: menu option 3 «Load staging from cache» with the same batch ID.")
        raise


def run_publish(pipeline_info, config):
    """Run the publish layer."""
    batch_id = configure_batch(pipeline_info)
    print_run_plan(
        pipeline_info,
        operation="Publish snapshot",
        batch_id=batch_id,
        snapshot_date=config.get('snapshot_date'),
    )

    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, config['snapshot_date'], log=False)
    )

    started = time.monotonic()
    print_action("Publishing...")
    try:
        pipeline.publish()
        elapsed = time.monotonic() - started
        print_run_footer(pipeline_info, pipeline, None, elapsed, success=True)
        return pipeline
    except Exception:
        elapsed = time.monotonic() - started
        print_run_footer(pipeline_info, pipeline, None, elapsed, success=False)
        raise


def run_full_pipeline(pipeline_info):
    """Run the full pipeline (load fact or prepare batch, then publish)."""
    staging_config = configure_staging(pipeline_info, staging_mode='full')
    batch_id = configure_batch(pipeline_info, staging_mode='full')
    if is_sql_source_pipeline(pipeline_info):
        operation = "Full pipeline (prepare batch + publish)"
    elif pipeline_info['name'] == 'Distributor Deliveries':
        operation = "Full pipeline (load fact + publish)"
    else:
        operation = "Full pipeline (staging + publish)"
    print_run_plan(
        pipeline_info,
        operation=operation,
        batch_id=batch_id,
        config=staging_config,
        staging_mode='full',
    )

    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, staging_config['snapshot_date'])
    )

    started = time.monotonic()
    try:
        pipeline.run()
        elapsed = time.monotonic() - started
        print_run_footer(pipeline_info, pipeline, 'full', elapsed, success=True)
        return pipeline
    except Exception as e:
        elapsed = time.monotonic() - started
        print_run_footer(pipeline_info, pipeline, 'full', elapsed, success=False)
        if isinstance(e, StageVerificationError):
            print_warning("Retry after fixing the error above.")
        raise


def run_full_automate_pipeline():
    """Run all pipelines with default settings (today's date, auto-batch, prod DB)."""
    print_header("Full Automate Pipeline - Running All Pipelines", Colors.BRIGHT_MAGENTA)
    print_info("All pipelines run with today's snapshot date and auto-created batches.")
    print()

    total = len(PIPELINES)
    succeeded = []
    failed = []

    for key, pipeline_info in PIPELINES.items():
        pipeline_name = pipeline_info['name']
        print_header(f"[{key}/{total}] {pipeline_name}", Colors.BRIGHT_CYAN)
        try:
            print_action(f"[{pipeline_name}] Creating batch...")
            batch_id = start_new_batch(
                batch_type=pipeline_info['batch_type'],
                triggered_by='MANUAL_TEST',
                database_type='prod',
                pipeline_name=pipeline_name
            )

            pipeline = pipeline_info['class'](
                **build_pipeline_kwargs(pipeline_info, batch_id, None)
            )
            step_started = time.monotonic()

            print_action(f"[{pipeline_name}] Running pipeline...")
            pipeline.run()

            elapsed = time.monotonic() - step_started
            print_success(
                f"[{pipeline_name}] Completed successfully in {format_duration(elapsed)}!"
            )
            succeeded.append(pipeline_name)

        except Exception as e:
            print_error(f"[{pipeline_name}] Failed: {e}")
            import traceback
            traceback.print_exc()
            failed.append(pipeline_name)

        print()  # blank line between pipelines

    # --- Summary ---
    print_header("Full Automate Pipeline - Summary", Colors.BRIGHT_MAGENTA)
    print_info(f"Total pipelines: {total}")
    if succeeded:
        print_success(f"Succeeded ({len(succeeded)}): {', '.join(succeeded)}")
    if failed:
        print_error(f"Failed    ({len(failed)}): {', '.join(failed)}")
    if not failed:
        print_success("All pipelines completed successfully!")


def handle_error(e):
    """Handle errors with helpful messages (caller already showed a short footer)."""
    error_msg = str(e)
    print_error(error_msg)

    if "Could not find stored procedure" in error_msg or "2812" in error_msg:
        print_header("PROCEDURE NOT FOUND", Colors.BRIGHT_RED)
        print(colorize("The stored procedure has not been deployed to the database yet.", Colors.YELLOW))
        print()
        print_info("To fix this, run the deployment script:")
        print(colorize("  python scripts/deploy_procedures.py", Colors.BRIGHT_WHITE))
        print()
        print(colorize("This will deploy all stored procedures to the 'prod' database.", Colors.DIM))
        print(colorize("If you need to deploy to a different database, use:", Colors.DIM))
        print(colorize("  python scripts/deploy_procedures.py <database_type>", Colors.BRIGHT_WHITE))
        print(colorize("  (where <database_type> is 'source' or 'prod')", Colors.DIM))
    
    if isinstance(e, StageVerificationError):
        print_warning("Row counts did not match — see log lines above for source/cache/staging details.")


def view_cache_status_interactive(pipeline_info):
    """Show extract cache for a batch (no pipeline run)."""
    print_header("Cache status", Colors.BRIGHT_CYAN)
    batch_id_str = print_prompt("Batch ID: ").strip()
    try:
        batch_id = int(batch_id_str)
    except ValueError:
        print_error("Invalid batch ID.")
        return

    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, None, log=False)
    )
    print_cache_status(pipeline, batch_id)


def main():
    """Main terminal interface for pipeline access."""
    print_header("ETL Pipeline Terminal Access", Colors.BRIGHT_CYAN)

    # SQL Server and DMS are behind the corporate VPN — make sure it is up.
    ensure_vpn_connected(log_fn=print_info, prompt_fn=print_prompt)

    while True:
        # First layer: Select pipeline
        pipeline_info = select_pipeline()
        if pipeline_info is None:
            print()
            print_info("Goodbye!")
            break
        
        # Handle full automate pipeline (run all)
        if pipeline_info == 'ALL':
            try:
                run_full_automate_pipeline()
            except Exception as e:
                handle_error(e)
            continue
        
        while True:
            choice = select_operation(pipeline_info)

            if choice == 'b':
                break
            elif choice == 'q':
                print()
                print_info("Goodbye!")
                sys.exit(0)

            sql = is_sql_source_pipeline(pipeline_info)

            try:
                if sql and choice == '1':
                    config = configure_publish(pipeline_info)
                    run_publish(pipeline_info, config)
                elif sql and choice == '2':
                    run_full_pipeline(pipeline_info)
                elif pipeline_info['name'] == 'Distributor Deliveries' and choice == '1':
                    config = configure_staging(pipeline_info, staging_mode='full')
                    run_staging(pipeline_info, config, staging_mode='full')
                elif pipeline_info['name'] == 'Distributor Deliveries' and choice == '2':
                    config = configure_publish(pipeline_info)
                    run_publish(pipeline_info, config)
                elif pipeline_info['name'] == 'Distributor Deliveries' and choice == '3':
                    run_full_pipeline(pipeline_info)
                else:
                    print_error("Invalid choice.")
                    continue
            except Exception as e:
                handle_error(e)
                import traceback
                traceback.print_exc()
            
            # Ask if user wants to continue with this pipeline
            continue_choice = print_prompt("\nContinue with this pipeline? (y/n, default=y): ").strip().lower()
            if continue_choice == 'n':
                break


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print_warning("Interrupted by user. Goodbye!")
        sys.exit(0)
