"""Adapter interfaces and platform implementations."""

from .base import PlatformAdapter, QueryExecutionError, UnsupportedQueryError
from .duckdb import DuckDBAdapter

__all__ = [
    "PlatformAdapter",
    "QueryExecutionError",
    "UnsupportedQueryError",
    "DuckDBAdapter",
]

