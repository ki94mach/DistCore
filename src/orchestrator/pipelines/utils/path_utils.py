"""Path utility functions for pipelines."""

from pathlib import Path


def get_sql_folder_path(reference_file: Path) -> Path:
    """
    Get the path to the sql folder relative to a reference file.
    
    Assumes the sql folder is at the project root. Navigates up from the
    reference file to find the project root, then locates the sql folder.
    
    Args:
        reference_file: Path to a file in the project (used as reference point)
        
    Returns:
        Path to the sql folder
        
    Example:
        >>> from pathlib import Path
        >>> sql_folder = get_sql_folder_path(Path(__file__))
        >>> sql_folder.exists()
        True
    """
    # Navigate up from reference file to project root
    # Typical structure: reference_file -> ... -> src -> project_root
    current = reference_file.parent
    
    # Try to find project root by looking for sql folder
    # Go up to 6 levels (should be enough for most structures)
    for _ in range(6):
        sql_folder = current / 'sql'
        if sql_folder.exists() and sql_folder.is_dir():
            return sql_folder
        current = current.parent
    
    # Fallback: assume sql folder is at project root (4 levels up from pipelines/)
    # This matches: pipelines -> orchestrator -> src -> project_root
    project_root = reference_file.parent.parent.parent.parent
    sql_folder = project_root / 'sql'
    
    # Final fallback: try one more level up
    if not sql_folder.exists():
        sql_folder = project_root.parent / 'sql'
    
    return sql_folder

