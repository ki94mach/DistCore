"""Staging table utility functions."""

# This module previously contained functions for deduplication and incremental loading
# that were used by the distributor_deliveries pipeline. These have been removed as
# the pipeline now uses a simple full refresh approach (delete all + insert all).
#
# If similar functionality is needed in the future, it can be re-implemented here.

