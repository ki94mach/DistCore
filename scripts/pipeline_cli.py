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


def staging_mode_label(staging_mode: str) -> str:
    return {
        'full': 'Full (extract + verify + load staging + verify)',
        'extract_only': 'Extract to cache only',
        'load_from_cache': 'Load staging from cache only',
    }.get(staging_mode, staging_mode)


def print_staging_config_summary(pipeline_info, config: dict, staging_mode: str) -> None:
    print_header("Run configuration", Colors.BRIGHT_BLUE)
    print_kv("Pipeline", pipeline_info['name'])
    print_kv("Operation", staging_mode_label(staging_mode))
    snapshot = config.get('snapshot_date') or date.today()
    print_kv("Snapshot date", snapshot.isoformat())
    print_kv("Batch size", f"{config.get('batch_size', 10000):,}")
    if is_sql_source_pipeline(pipeline_info):
        print_kv("Progress bars", "enabled (extract, staging DB load, verify)")
        print_kv("Force re-extract", "yes" if config.get('force_extract') else "no")
        if pipeline_info['name'] in ('Factory Inventory', 'Distributor Inventory', 'Target'):
            if config.get('single_date_only'):
                mode = "Single date only"
            elif config.get('incremental'):
                mode = "Incremental"
            else:
                mode = "Full load"
            print_kv("Load mode", mode)
    print()


def get_cache_for_pipeline(pipeline, batch_id: int) -> ExtractCache:
    cache_dir = getattr(pipeline, '_cache_dir', get_default_cache_root(
        Path(__file__).resolve().parent.parent / 'src' / 'orchestrator' / 'pipelines'
    ))
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


def print_run_result(
    pipeline_info,
    pipeline,
    staging_mode: str,
    elapsed: float,
    success: bool,
) -> None:
    print_header("Run summary", Colors.BRIGHT_GREEN if success else Colors.BRIGHT_RED)
    print_kv("Pipeline", pipeline_info['name'])
    print_kv("Batch ID", getattr(pipeline, 'batch_id', '—'))
    print_kv("Operation", staging_mode_label(staging_mode))
    print_kv("Elapsed", format_duration(elapsed))
    print_kv("Outcome", "SUCCESS" if success else "FAILED")

    if success and is_sql_source_pipeline(pipeline_info):
        if staging_mode == 'extract_only':
            print_cache_status(pipeline)
        elif staging_mode in ('full', 'load_from_cache'):
            print_info(
                "Extract cache was removed after a successful staging load "
                "(expected when load + verify completes)."
            )
    print()


def build_pipeline_kwargs(pipeline_info, batch_id, snapshot_date, log: bool = True) -> dict:
    kwargs = {
        'batch_id': batch_id,
        'snapshot_date': snapshot_date,
        'triggered_by': 'MANUAL_TEST',
        'database_type': 'test',
    }
    if pipeline_info['name'] == 'Distributor Deliveries':
        kwargs['log_fn'] = print_info if log else None
    elif log:
        kwargs['log_fn'] = make_pipeline_log_fn(pipeline_info['name'])
        kwargs['show_progress'] = True
    return kwargs


def build_load_stage_kwargs(pipeline_info, config, staging_mode: str) -> dict:
    """Build load_stage keyword arguments for a pipeline and staging mode."""
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


def start_new_batch(batch_type: str, triggered_by: str = 'MANUAL_TEST', database_type: str = 'test', pipeline_name: str = None) -> int:
    """Start a new batch and return the batch_id."""
    connection_factory = DBConnectionFactory()
    sql_executor = SQLExecutor(connection_factory)
    
    result = sql_executor.execute_procedure_with_output(
        procedure_name='[Data].[ctl_usp_start_batch]',
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


def select_layer(pipeline_info):
    """Second layer: Select a layer/operation."""
    print_header(f"{pipeline_info['name']} - Available Layers", Colors.BRIGHT_CYAN)
    if is_sql_source_pipeline(pipeline_info):
        print_menu_item('1', 'Load Stage (extract + staging)', Colors.BRIGHT_WHITE)
        print_menu_item('4', 'Extract to cache only', Colors.BRIGHT_WHITE)
        print_menu_item('5', 'Load staging from cache', Colors.BRIGHT_WHITE)
        print_menu_item('6', 'View extract cache status', Colors.BRIGHT_WHITE)
    else:
        print_menu_item('1', 'Load Stage (staging layer)', Colors.BRIGHT_WHITE)
    print_menu_item('2', 'Publish (publish layer)', Colors.BRIGHT_WHITE)
    print_menu_item('3', 'Run Full Pipeline (load_stage + publish)', Colors.BRIGHT_WHITE)
    print_menu_item('b', 'Back to pipelines', Colors.BRIGHT_YELLOW)
    print_menu_item('q', 'Quit', Colors.BRIGHT_YELLOW)
    
    choice = print_prompt("\nSelect layer: ").strip().lower()
    return choice


def configure_staging(pipeline_info):
    """Configure staging layer parameters (date control)."""
    print_header("Staging Layer Configuration", Colors.BRIGHT_BLUE)
    
    # Date configuration
    print_info("\nSnapshot Date:")
    print(colorize("  - Press Enter to use today's date", Colors.DIM))
    print(colorize("  - Enter a date (YYYY-MM-DD) to use a specific date", Colors.DIM))
    snapshot_date_str = print_prompt("Enter snapshot date (YYYY-MM-DD) or press Enter for today: ").strip()
    
    snapshot_date = None
    if snapshot_date_str:
        try:
            year, month, day = map(int, snapshot_date_str.split('-'))
            snapshot_date = date(year, month, day)
        except ValueError:
            print_error("Invalid date format. Using today's date.")
            snapshot_date = None
    
    # Additional staging parameters for FactoryInventoryPipeline
    batch_size = 10000
    incremental = True
    single_date_only = False
    
    if pipeline_info['name'] == 'Factory Inventory' or pipeline_info['name'] == 'Distributor Inventory':
        print_info("\nBatch Size:")
        print(colorize("  - Press Enter for default (10000)", Colors.DIM))
        batch_size_str = print_prompt("Enter batch size (default: 10000): ").strip()
        if batch_size_str:
            try:
                batch_size = int(batch_size_str)
            except ValueError:
                print_error("Invalid batch size. Using default (10000).")
        
        print_info("\nLoad Mode:")
        print_menu_item('1', 'Incremental (load data after latest date in staging)', Colors.WHITE)
        print_menu_item('2', 'Single date only (load only snapshot_date)', Colors.WHITE)
        print_menu_item('3', 'Full load (load all data)', Colors.WHITE)
        mode_choice = print_prompt("Select mode (1/2/3, default=1): ").strip() or "1"
        
        if mode_choice == "2":
            incremental = False
            single_date_only = True
        elif mode_choice == "3":
            incremental = False
            single_date_only = False
    elif pipeline_info['name'] == 'Sales Snapshot':
        print_info("\nLoad Mode:")
        print(colorize(
            "  - Sales snapshots load a rolling six-month window ending on the snapshot date.",
            Colors.DIM
        ))
        incremental = False
        single_date_only = False
    elif pipeline_info['name'] == 'Target':
        print_info("\nLoad Mode:")
        print(colorize(
            "  - Target pipeline loads data for the current Jalali year only.",
            Colors.DIM
        ))
        incremental = False
        single_date_only = False

    force_extract = False
    max_verification_retries = 3
    if is_sql_source_pipeline(pipeline_info):
        force_extract = prompt_force_extract()
        retries_str = print_prompt(
            "Max verification retries per step (default=3): "
        ).strip()
        if retries_str:
            try:
                max_verification_retries = max(1, int(retries_str))
            except ValueError:
                print_error("Invalid value. Using default (3).")

    return {
        'snapshot_date': snapshot_date,
        'batch_size': batch_size,
        'incremental': incremental,
        'single_date_only': single_date_only,
        'force_extract': force_extract,
        'max_verification_retries': max_verification_retries,
    }


def configure_publish(pipeline_info):
    """Configure publish layer parameters."""
    print_header("Publish Layer Configuration", Colors.BRIGHT_BLUE)
    
    # Date configuration (needed for publish too)
    print_info("\nSnapshot Date:")
    print(colorize("  - Press Enter to use today's date", Colors.DIM))
    print(colorize("  - Enter a date (YYYY-MM-DD) to use a specific date", Colors.DIM))
    snapshot_date_str = print_prompt("Enter snapshot date (YYYY-MM-DD) or press Enter for today: ").strip()
    
    snapshot_date = None
    if snapshot_date_str:
        try:
            year, month, day = map(int, snapshot_date_str.split('-'))
            snapshot_date = date(year, month, day)
        except ValueError:
            print_error("Invalid date format. Using today's date.")
            snapshot_date = None
    
    # Additional publish parameters can be added here for future pipelines
    publish_params = {}
    
    if pipeline_info['name'] == 'Factory Inventory' or pipeline_info['name'] == 'Distributor Inventory':
        # Currently FactoryInventoryPipeline.publish() doesn't take additional parameters
        # But we can add them here for future extensibility
        pass
    
    return {
        'snapshot_date': snapshot_date,
        **publish_params
    }


def configure_batch(pipeline_info):
    """Configure batch options."""
    print_header("Batch Configuration", Colors.BRIGHT_BLUE)
    print_menu_item('1', 'Create new batch automatically (recommended)', Colors.BRIGHT_WHITE)
    print_menu_item('2', 'Use existing batch ID', Colors.WHITE)
    print_menu_item('3', 'Let pipeline create batch automatically', Colors.WHITE)
    
    choice = print_prompt("\nSelect option (1/2/3, default=1): ").strip() or "1"
    
    batch_id = None
    if choice == "1":
        print_action("Creating new batch...")
        batch_id = start_new_batch(
            batch_type=pipeline_info['batch_type'],
            triggered_by='MANUAL_TEST',
            database_type='test',
            pipeline_name=pipeline_info['name']
        )
    elif choice == "2":
        batch_id_str = print_prompt("\nEnter existing batch ID: ").strip()
        try:
            batch_id = int(batch_id_str)
        except ValueError:
            print_error("Invalid batch ID. Will create new batch automatically.")
            batch_id = None
    else:  # choice == "3"
        print_action("Pipeline will create batch automatically...")
        batch_id = None
    
    return batch_id


def run_staging(pipeline_info, config, staging_mode: str = 'full'):
    """Run the staging layer."""
    mode_labels = {
        'full': 'Running Staging Layer',
        'extract_only': 'Extracting to Cache',
        'load_from_cache': 'Loading Staging from Cache',
    }
    print_header(mode_labels.get(staging_mode, 'Running Staging Layer'), Colors.BRIGHT_GREEN)
    print_staging_config_summary(pipeline_info, config, staging_mode)

    batch_id = configure_batch(pipeline_info)
    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, config['snapshot_date'])
    )

    if is_sql_source_pipeline(pipeline_info) and batch_id:
        print_cache_status(pipeline, batch_id)

    started = time.monotonic()
    print_action("Starting pipeline work...")
    try:
        if is_sql_source_pipeline(pipeline_info):
            pipeline.load_stage(**build_load_stage_kwargs(pipeline_info, config, staging_mode))
        elif pipeline_info['name'] == 'Distributor Deliveries':
            pipeline.load_stage(batch_size=config['batch_size'])
        else:
            pipeline.load_stage()

        elapsed = time.monotonic() - started
        print_run_result(pipeline_info, pipeline, staging_mode, elapsed, success=True)
        success_labels = {
            'full': 'Load stage completed successfully!',
            'extract_only': 'Extract to cache completed successfully!',
            'load_from_cache': 'Load staging from cache completed successfully!',
        }
        print_success(
            f"[{pipeline_info['name']}] {success_labels.get(staging_mode, 'Load stage completed successfully!')}"
        )
        return pipeline
    except Exception as e:
        elapsed = time.monotonic() - started
        print_run_result(pipeline_info, pipeline, staging_mode, elapsed, success=False)
        if is_sql_source_pipeline(pipeline_info) and isinstance(e, StageVerificationError):
            print_warning(
                "Verification failed. If extract cache still exists, use menu option "
                "'5 — Load staging from cache' with the same batch ID."
            )
            if getattr(pipeline, 'batch_id', None):
                print_cache_status(pipeline)
        print_error(f"Error: {str(e)}")
        raise


def run_publish(pipeline_info, config):
    """Run the publish layer."""
    print_header("Running Publish Layer", Colors.BRIGHT_GREEN)
    print_kv("Pipeline", pipeline_info['name'])
    snapshot = config.get('snapshot_date') or date.today()
    print_kv("Snapshot date", snapshot.isoformat())
    print()

    batch_id = configure_batch(pipeline_info)
    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, config['snapshot_date'], log=False)
    )
    print_kv("Batch ID", getattr(pipeline, 'batch_id', batch_id))

    started = time.monotonic()
    print_action("Publishing to snapshot...")
    try:
        pipeline.publish()
        elapsed = time.monotonic() - started
        print_kv("Elapsed", format_duration(elapsed))
        print_success(f"[{pipeline_info['name']}] Publish completed successfully!")
        return pipeline
    except Exception as e:
        print_error(f"Error: {str(e)}")
        raise


def run_full_pipeline(pipeline_info):
    """Run the full pipeline."""
    print_header("Running Full Pipeline", Colors.BRIGHT_GREEN)

    staging_config = configure_staging(pipeline_info)
    print_staging_config_summary(pipeline_info, staging_config, 'full')

    batch_id = configure_batch(pipeline_info)
    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, staging_config['snapshot_date'])
    )

    started = time.monotonic()
    try:
        print_header("Step 1/2 — Load stage", Colors.BRIGHT_CYAN)
        if is_sql_source_pipeline(pipeline_info):
            pipeline.load_stage(
                **build_load_stage_kwargs(pipeline_info, staging_config, 'full')
            )
        elif pipeline_info['name'] == 'Distributor Deliveries':
            pipeline.load_stage(batch_size=staging_config['batch_size'])
        else:
            pipeline.load_stage()
        print_success("Load stage finished.")

        print_header("Step 2/2 — Publish", Colors.BRIGHT_CYAN)
        pipeline.publish()
        print_success("Publish finished.")

        if hasattr(pipeline, 'batch_id') and pipeline.batch_id:
            pipeline.finish_batch(pipeline.batch_id, 'SUCCESS', 'OK')

        elapsed = time.monotonic() - started
        print_run_result(pipeline_info, pipeline, 'full', elapsed, success=True)
        print_success(f"[{pipeline_info['name']}] Full pipeline completed successfully!")
        return pipeline
    except Exception as e:
        if hasattr(pipeline, 'batch_id') and pipeline.batch_id:
            try:
                pipeline.finish_batch(pipeline.batch_id, 'FAILED', str(e))
            except Exception:
                pass
        elapsed = time.monotonic() - started
        print_run_result(pipeline_info, pipeline, 'full', elapsed, success=False)
        if is_sql_source_pipeline(pipeline_info) and isinstance(e, StageVerificationError):
            print_warning(
                "Try 'Load staging from cache' (option 5) with the same batch ID after fixing the issue."
            )
            if getattr(pipeline, 'batch_id', None):
                print_cache_status(pipeline)
        print_error(f"Error: {str(e)}")
        raise


def run_full_automate_pipeline():
    """Run all pipelines fully automated with default settings.
    
    Each pipeline runs with:
    - snapshot_date: today's date (None -> defaults to today inside the pipeline)
    - batch_size: 10000 (default)
    - incremental: True (default)
    - single_date_only: False (default)
    - batch: auto-created per pipeline
    - triggered_by: MANUAL_TEST
    - database_type: test
    """
    print_header("Full Automate Pipeline - Running All Pipelines", Colors.BRIGHT_MAGENTA)
    print_info("All pipelines will run with default settings (today's date, incremental, auto-batch).")
    print()

    total = len(PIPELINES)
    succeeded = []
    failed = []

    for key, pipeline_info in PIPELINES.items():
        pipeline_name = pipeline_info['name']
        print_header(f"[{key}/{total}] {pipeline_name}", Colors.BRIGHT_CYAN)
        try:
            # Create batch
            print_action(f"[{pipeline_name}] Creating batch...")
            batch_id = start_new_batch(
                batch_type=pipeline_info['batch_type'],
                triggered_by='MANUAL_TEST',
                database_type='test',
                pipeline_name=pipeline_name
            )

            pipeline = pipeline_info['class'](
                **build_pipeline_kwargs(pipeline_info, batch_id, None)
            )
            step_started = time.monotonic()

            # --- Load stage ---
            print_action(f"[{pipeline_name}] Loading stage...")
            if pipeline_name in ('Factory Inventory', 'Distributor Inventory'):
                pipeline.load_stage(
                    batch_size=10000,
                    incremental=True,
                    single_date_only=False
                )
            elif pipeline_name == 'Sales Snapshot':
                pipeline.load_stage(batch_size=10000)
            elif pipeline_name == 'Target':
                pipeline.load_stage(
                    batch_size=10000,
                    incremental=True,
                    single_date_only=False
                )
            elif pipeline_name == 'Distributor Deliveries':
                pipeline.load_stage(batch_size=10000)
            else:
                pipeline.load_stage()

            # --- Publish ---
            print_action(f"[{pipeline_name}] Publishing...")
            pipeline.publish()

            # Finish batch
            if hasattr(pipeline, 'batch_id') and pipeline.batch_id:
                pipeline.finish_batch(pipeline.batch_id, 'SUCCESS', 'OK')

            elapsed = time.monotonic() - step_started
            print_success(
                f"[{pipeline_name}] Completed successfully in {format_duration(elapsed)}!"
            )
            succeeded.append(pipeline_name)

        except Exception as e:
            print_error(f"[{pipeline_name}] Failed: {e}")
            # Try to mark batch as failed
            try:
                if 'pipeline' in locals() and hasattr(pipeline, 'batch_id') and pipeline.batch_id:
                    pipeline.finish_batch(pipeline.batch_id, 'FAILED', str(e))
            except Exception:
                pass
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
    """Handle errors with helpful messages."""
    error_msg = str(e)
    print_error(f"Error: {error_msg}")
    
    # Check if it's a procedure not found error
    if "Could not find stored procedure" in error_msg or "2812" in error_msg:
        print_header("PROCEDURE NOT FOUND", Colors.BRIGHT_RED)
        print(colorize("The stored procedure has not been deployed to the database yet.", Colors.YELLOW))
        print()
        print_info("To fix this, run the deployment script:")
        print(colorize("  python scripts/deploy_procedures.py", Colors.BRIGHT_WHITE))
        print()
        print(colorize("This will deploy all stored procedures to the 'test' database.", Colors.DIM))
        print(colorize("If you need to deploy to a different database, use:", Colors.DIM))
        print(colorize("  python scripts/deploy_procedures.py <database_type>", Colors.BRIGHT_WHITE))
        print(colorize("  (where <database_type> is 'source' or 'test')", Colors.DIM))
    
    if isinstance(e, StageVerificationError):
        print_warning(
            "Row-count verification failed between source, cache, and/or staging. "
            "Check the progress log above for attempt details."
        )

    import traceback
    traceback.print_exc()


def view_cache_status_interactive(pipeline_info):
    """Prompt for batch ID and show extract cache status."""
    print_header("View Extract Cache Status", Colors.BRIGHT_CYAN)
    batch_id_str = print_prompt("Enter batch ID: ").strip()
    try:
        batch_id = int(batch_id_str)
    except ValueError:
        print_error("Invalid batch ID.")
        return

    snapshot_date = None
    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, snapshot_date, log=False)
    )
    print_cache_status(pipeline, batch_id)


def main():
    """Main terminal interface for pipeline access."""
    print_header("ETL Pipeline Terminal Access", Colors.BRIGHT_CYAN)
    
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
        
        # Second layer: Select layer/operation
        while True:
            layer_choice = select_layer(pipeline_info)
            
            if layer_choice == 'b':
                break
            elif layer_choice == 'q':
                print()
                print_info("Goodbye!")
                sys.exit(0)
            elif layer_choice == '1':
                # Staging layer (full extract + load for SQL pipelines)
                try:
                    config = configure_staging(pipeline_info)
                    run_staging(pipeline_info, config, staging_mode='full')
                except Exception as e:
                    handle_error(e)
            elif layer_choice == '4' and is_sql_source_pipeline(pipeline_info):
                try:
                    config = configure_staging(pipeline_info)
                    run_staging(pipeline_info, config, staging_mode='extract_only')
                except Exception as e:
                    handle_error(e)
            elif layer_choice == '5' and is_sql_source_pipeline(pipeline_info):
                try:
                    config = configure_staging(pipeline_info)
                    config['force_extract'] = False
                    run_staging(pipeline_info, config, staging_mode='load_from_cache')
                except Exception as e:
                    handle_error(e)
            elif layer_choice == '6' and is_sql_source_pipeline(pipeline_info):
                try:
                    view_cache_status_interactive(pipeline_info)
                except Exception as e:
                    handle_error(e)
            elif layer_choice == '2':
                # Publish layer
                try:
                    config = configure_publish(pipeline_info)
                    run_publish(pipeline_info, config)
                except Exception as e:
                    handle_error(e)
            elif layer_choice == '3':
                # Full pipeline
                try:
                    run_full_pipeline(pipeline_info)
                except Exception as e:
                    handle_error(e)
            else:
                print_error("Invalid choice. Please try again.")
            
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
