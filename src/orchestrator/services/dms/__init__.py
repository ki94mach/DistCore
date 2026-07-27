"""DMS file share service for accessing files from internal SharePoint folders."""

from .client import DmsClient, resolve_dms_auth
from .config import DmsConfigLoader

__all__ = ["DmsClient", "DmsConfigLoader", "resolve_dms_auth"]
