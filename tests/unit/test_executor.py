"""Tests for query execution path and error mapping."""

from __future__ import annotations

import time
from pathlib import Path

import duckdb
import pytest

from mini_data_platform_agent.adapter.base import QueryExecutionError
from mini_data_platform_agent.adapter.duckdb import DuckDBAdapter
from mini_data_platform_agent.adapter import PlatformAdapter
from mini_data_platform_agent.config import AppConfig
from mini_data_platform_agent.executor import ExecutionError, ExecutionTimeoutError, execute_query
from mini_data_platform_agent.types import PlatformContext, QueryResult


class ErrorAdapter(PlatformAdapter):
    def health_check(self) -> bool:
        return True

    def load_context(self) -> PlatformContext:
        return PlatformContext()

    def _execute_select(self, sql: str, limit: int) -> QueryResult:
        raise QueryExecutionError("syntax error near 'FROM'")


class SlowAdapter(PlatformAdapter):
    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        self.calls: list[tuple[str, int]] = []

    def health_check(self) -> bool:
        return True

    def load_context(self) -> PlatformContext:
        return PlatformContext()

    def _execute_select(self, sql: str, limit: int) -> QueryResult:
        self.calls.append((sql, limit))
        time.sleep(0.02)
        return QueryResult(
            columns=["x"],
            rows=[{"x": 1}],
            row_count=1,
            duration_ms=1,
            truncated=False,
        )


def _seed_db(path: Path) -> None:
    con = duckdb.connect(path)
    con.execute("CREATE TABLE fct_orders (order_id INTEGER, total_revenue DOUBLE)")
    con.execute("INSERT INTO fct_orders VALUES (1, 10.0), (2, 20.0), (3, 30.0)")
    con.execute("CREATE TABLE empty_table (id INTEGER)")
    con.close()


def test_successful_execution_returns_rows_and_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "data.duckdb"
    _seed_db(db_path)

    result = execute_query(
        'SELECT SUM(total_revenue) AS revenue FROM fct_orders',
        adapter=DuckDBAdapter(AppConfig(db_path=db_path)),
        limit=5,
        timeout_ms=10_000,
    )

    assert result.row_count == 1
    assert result.columns == ["revenue"]
    assert result.duration_ms >= 0


def test_empty_result_set_is_handled_gracefully(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.duckdb"
    _seed_db(db_path)

    result = execute_query(
        "SELECT * FROM empty_table WHERE id = 999",
        adapter=DuckDBAdapter(AppConfig(db_path=db_path)),
        limit=10,
    )
    assert result.row_count == 0
    assert result.rows == []
    assert result.truncated is False


def test_errors_map_to_friendly_messages() -> None:
    adapter = ErrorAdapter(AppConfig())
    with pytest.raises(ExecutionError) as exc:
        execute_query("SELECT bad", adapter=adapter)

    assert "syntax" in str(exc.value).lower() or "failed to execute" in str(exc.value).lower()


def test_timeout_wrapper_is_respected() -> None:
    config = AppConfig(default_limit=200, max_limit=200, query_timeout_ms=1)
    adapter = SlowAdapter(config)
    with pytest.raises(ExecutionTimeoutError) as exc:
        execute_query("SELECT 1", adapter=adapter, timeout_ms=1)
    assert "timed out" in str(exc.value).lower()


def test_row_cap_is_respected(tmp_path: Path) -> None:
    config = AppConfig(default_limit=2, max_limit=2, query_timeout_ms=10_000)
    db_path = tmp_path / "executor_cap.duckdb"
    con = duckdb.connect(db_path)
    con.execute("CREATE TABLE t (id INTEGER)")
    con.execute("INSERT INTO t VALUES (1), (2), (3), (4)")
    con.close()

    result = execute_query(
        "SELECT id FROM t",
        adapter=DuckDBAdapter(AppConfig(db_path=db_path, default_limit=2, max_limit=2)),
        limit=10,
    )
    assert result.row_count <= 2
