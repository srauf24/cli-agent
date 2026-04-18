"""Base adapter contract for storage/query execution."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from ..config import AppConfig
from ..types import PlatformContext, QueryResult


_SELECT_RE = re.compile(r"^\s*(?:select|with)\b", re.IGNORECASE | re.DOTALL)


class AdapterError(RuntimeError):
    """Base exception raised by adapter operations."""


class UnsupportedQueryError(AdapterError):
    """Raised when a non-read-only SQL statement is requested."""


class QueryExecutionError(AdapterError):
    """Raised when the platform cannot execute a valid read query."""


class PlatformAdapter(ABC):
    """Abstract platform adapter contract.

    Concrete adapters implement platform-specific metadata discovery and SQL execution.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @abstractmethod
    def health_check(self) -> bool:
        """Return True when platform access is currently healthy."""

    @abstractmethod
    def load_context(self) -> PlatformContext:
        """Discover platform tables/schemas and metadata."""

    @abstractmethod
    def _execute_select(self, sql: str, limit: int) -> QueryResult:
        """Execute a validated read-only statement and return normalized results."""

    def run_select(self, sql: str, limit: int | None = None) -> QueryResult:
        """Run read-only SQL with a safe query guard."""

        if not _SELECT_RE.match(sql or ""):
            raise UnsupportedQueryError("Only SELECT-style queries are allowed.")

        effective_limit = self.config.effective_limit(limit)
        return self._execute_select(sql=sql, limit=effective_limit)
