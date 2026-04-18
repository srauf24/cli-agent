"""Tests for DuckDB adapter behavior."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from mini_data_platform_agent.adapter import DuckDBAdapter
from mini_data_platform_agent.adapter.base import UnsupportedQueryError
from mini_data_platform_agent.config import AppConfig


def _create_sample_db(path: Path) -> None:
    con = duckdb.connect(path)
    con.execute("CREATE TABLE users(user_id INTEGER, country VARCHAR)")
    con.execute("INSERT INTO users VALUES (1, 'US'), (2, 'IE')")
    con.execute("CREATE TABLE orders(order_id INTEGER, user_id INTEGER, total DOUBLE)")
    con.execute("INSERT INTO orders VALUES (11, 1, 19.99), (12, 2, 8.5), (13, 1, 7.25)")
    con.execute("CREATE TABLE dim_customers(user_id INTEGER, country VARCHAR)")
    con.execute("INSERT INTO dim_customers VALUES (1, 'US'), (2, 'IE')")
    con.close()


def test_duckdb_health_check_reflects_access(tmp_path: Path) -> None:
    db_path = tmp_path / "data.duckdb"
    _create_sample_db(db_path)

    ok_adapter = DuckDBAdapter(AppConfig(db_path=db_path))
    assert ok_adapter.health_check() is True

    missing_adapter = DuckDBAdapter(AppConfig(db_path=tmp_path / "missing.duckdb"))
    assert missing_adapter.health_check() is False


def test_load_context_discovers_schema_and_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "warehouse.duckdb"
    _create_sample_db(db_path)
    adapter = DuckDBAdapter(AppConfig(db_path=db_path))

    context = adapter.load_context()

    assert "main" in context.schemas
    assert context.tables["main.orders"].columns[0].name == "order_id"
    assert context.tables["main.orders"].row_count == 3
    assert context.candidate_dim_tables == ["dim_customers"]
    assert context.candidate_fact_tables == []


def test_run_select_blocks_non_select_statements(tmp_path: Path) -> None:
    db_path = tmp_path / "block.duckdb"
    _create_sample_db(db_path)
    adapter = DuckDBAdapter(AppConfig(db_path=db_path))

    with pytest.raises(UnsupportedQueryError):
        adapter.run_select("INSERT INTO users VALUES (3, 'CA')")

