"""DMS file share service for accessing files from internal SharePoint folders."""

from .client import DmsClient
from .config import DmsConfigLoader

__all__ = ['DmsClient', 'DmsConfigLoader']
