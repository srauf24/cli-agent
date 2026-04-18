"""Tests for DuckDB platform metadata discovery."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from mini_data_platform_agent.config import AppConfig
from mini_data_platform_agent.context import discover_platform_context


def _init_test_warehouse(path: Path) -> None:
    con = duckdb.connect(path)
    try:
        con.execute("CREATE SCHEMA raw")
        con.execute(
            """
            CREATE TABLE raw.transactions(
                transaction_id INTEGER,
                product_id INTEGER,
                customer_id INTEGER
            )
            """
        )
        con.execute("INSERT INTO raw.transactions VALUES (1, 10, 100), (2, 20, 200)")

        con.execute("CREATE SCHEMA marts")
        con.execute(
            """
            CREATE TABLE marts.fct_orders(
                order_id INTEGER,
                customer_id INTEGER,
                order_total DOUBLE,
                order_ts TIMESTAMP
            )
            """
        )
        con.execute("INSERT INTO marts.fct_orders VALUES (10, 100, 29.99, NOW())")

        con.execute(
            """
            CREATE TABLE marts.dim_customers(
                customer_id INTEGER,
                country VARCHAR
            )
            """
        )
        con.execute("INSERT INTO marts.dim_customers VALUES (100, 'US')")

        con.execute("CREATE SCHEMA staging")
        con.execute(
            "CREATE VIEW staging.stg_transactions AS "
            "SELECT transaction_id, product_id FROM raw.transactions"
        )
        con.execute("INSERT INTO raw.transactions VALUES (3, 30, 300)")
    finally:
        con.close()


def _init_dbt_models(path: Path) -> None:
    (path / "models" / "marts").mkdir(parents=True, exist_ok=True)
    (path / "models" / "marts" / "fct_orders.sql").write_text("SELECT * FROM staging.fct_orders")
    (path / "models" / "marts" / "dim_customers.sql").write_text("SELECT * FROM raw.users")
    (path / "models" / "marts" / "dim_products.sql").write_text("SELECT * FROM raw.products")


@pytest.fixture
def sample_paths(tmp_path: Path):
    db_path = tmp_path / "data.duckdb"
    _init_test_warehouse(db_path)
    dbt_path = tmp_path / "dbt_project"
    dbt_path.mkdir()
    _init_dbt_models(dbt_path)
    return db_path, dbt_path


def test_discover_platform_context_reads_metadata(sample_paths: tuple[Path, Path]) -> None:
    db_path, dbt_path = sample_paths

    config = AppConfig(db_path=db_path, dbt_path=dbt_path)
    context = discover_platform_context(config)

    assert "raw" in context.schemas
    assert "marts" in context.schemas
    assert "staging.stg_transactions" in context.tables
    assert context.tables["marts.fct_orders"].row_count == 1
    assert context.tables["raw.transactions"].fqn == "raw.transactions"
    assert context.tables["raw.transactions"].columns[0].name == "transaction_id"
    assert context.tables["raw.transactions"].columns[0].dtype.startswith("INTEGER")

    assert context.candidate_fact_tables == ["fct_orders"]
    assert context.candidate_dim_tables == ["dim_customers"]
    assert context.recommended_models[:3] == [
        "fct_orders",
        "dim_customers",
        "dim_products",
    ]

    # staging view is discovered and marked as view
    assert context.tables["staging.stg_transactions"].is_view is True


def test_discover_platform_context_missing_db_raises(tmp_path: Path) -> None:
    missing_db = tmp_path / "does_not_exist.duckdb"
    config = AppConfig(db_path=missing_db, dbt_path=tmp_path / "dbt")
    with pytest.raises(FileNotFoundError, match="DuckDB file not found"):
        discover_platform_context(config)

