"""General pipeline utility functions."""

from typing import Optional


def has_valid_batch_id(batch_id: Optional[int]) -> bool:
    """
    Check if a batch ID is valid (not None or 0).
    
    Args:
        batch_id: Batch ID to validate
        
    Returns:
        True if batch_id is valid, False otherwise
        
    Example:
        >>> has_valid_batch_id(123)
        True
        >>> has_valid_batch_id(None)
        False
        >>> has_valid_batch_id(0)
        False
    """
    return batch_id not in (None, 0)

