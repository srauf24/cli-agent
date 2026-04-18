"""Query execution layer with timing and bounded safety enforcement."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .adapter import PlatformAdapter
from .adapter.base import AdapterError, QueryExecutionError
from .types import QueryResult


@dataclass(frozen=True)
class ExecutionError(RuntimeError):
    """Raised when a query cannot be executed safely or successfully."""

    message: str
    cause: str | None = None

    def __str__(self) -> str:
        if self.cause:
            return f"{self.message}: {self.cause}"
        return self.message


@dataclass(frozen=True)
class ExecutionTimeoutError(ExecutionError):
    """Raised when query execution exceeds the configured timeout."""

    message: str = "Query execution timed out."
    elapsed_ms: int = 0


def _map_execution_error(exc: Exception) -> ExecutionError:
    if isinstance(exc, QueryExecutionError) and "syntax" in str(exc).lower():
        return ExecutionError(
            message="Query failed due to a SQL syntax issue.",
            cause=str(exc),
        )
    if isinstance(exc, (AdapterError, QueryExecutionError)):
        return ExecutionError(
            message="Unable to execute the query against the platform.",
            cause=str(exc),
        )
    return ExecutionError(
        message="Unexpected error during query execution.",
        cause=str(exc),
    )


def execute_query(
    sql: str,
    adapter: PlatformAdapter,
    *,
    limit: int | None = None,
    timeout_ms: int | None = None,
) -> QueryResult:
    """Execute a validated SQL query with timing and bounded output handling."""

    effective_limit = adapter.config.effective_limit(limit)
    timeout_budget_ms = timeout_ms if timeout_ms is not None else adapter.config.query_timeout_ms

    start_ms = int(time.perf_counter() * 1000)
    try:
        raw = adapter.run_select(sql, limit=effective_limit)
    except Exception as exc:  # pragma: no cover - mapping boundary
        raise _map_execution_error(exc) from exc

    elapsed_ms = int(time.perf_counter() * 1000) - start_ms
    if timeout_budget_ms is not None and elapsed_ms > timeout_budget_ms:
        raise ExecutionTimeoutError(
            message="Query execution timed out.",
            elapsed_ms=elapsed_ms,
        )

    bounded_rows = raw.rows[:effective_limit]
    truncated = raw.truncated or (len(raw.rows) > effective_limit)
    return QueryResult(
        columns=raw.columns,
        rows=bounded_rows,
        row_count=len(bounded_rows),
        duration_ms=raw.duration_ms,
        truncated=truncated,
    )
