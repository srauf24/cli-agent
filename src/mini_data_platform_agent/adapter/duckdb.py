"""DuckDB adapter implementation."""

from __future__ import annotations

import time
from pathlib import Path

import duckdb

from .base import PlatformAdapter, QueryExecutionError
from ..config import AppConfig
from ..context import discover_platform_context
from ..types import QueryResult


class DuckDBAdapter(PlatformAdapter):
    """Storage adapter for DuckDB-backed mini platform warehouses."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        self._path = Path(config.db_path)

    def health_check(self) -> bool:
        if not self._path.exists():
            return False
        try:
            with duckdb.connect(str(self._path), read_only=True) as con:
                con.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def load_context(self):
        return discover_platform_context(self.config)

    def _execute_select(self, sql: str, limit: int) -> QueryResult:
        start = time.perf_counter()
        try:
            with duckdb.connect(str(self._path), read_only=True) as con:
                cursor = con.execute(sql)
                columns = [desc[0] for desc in (cursor.description or [])]
                raw_rows = cursor.fetchmany(limit + 1)
        except Exception as exc:
            raise QueryExecutionError("Query execution failed.") from exc

        truncated = len(raw_rows) > limit
        rows = raw_rows[:limit]
        duration_ms = int((time.perf_counter() - start) * 1000)
        payload = [dict(zip(columns, row)) for row in rows]
        return QueryResult(
            columns=columns,
            rows=payload,
            row_count=len(payload),
            duration_ms=duration_ms,
            truncated=truncated,
        )

