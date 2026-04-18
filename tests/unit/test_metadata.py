"""Tests for the metadata discovery layer."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from mini_data_platform_agent.config import AppConfig
from mini_data_platform_agent.metadata import discover_platform_context


def _seed_tables(db_path: Path) -> None:
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA raw")
    con.execute(
        "CREATE TABLE raw.transactions (transaction_id INTEGER, customer_id INTEGER, amount DOUBLE)"
    )
    con.execute("INSERT INTO raw.transactions VALUES (1, 10, 3.2), (2, 20, 4.1)")

    con.execute("CREATE SCHEMA marts")
    con.execute(
        "CREATE TABLE marts.fct_orders (order_id INTEGER, customer_id INTEGER, total_amount DOUBLE)"
    )
    con.execute(
        "INSERT INTO marts.fct_orders VALUES (1, 10, 99.99), (2, 20, 49.95)"
    )
    con.execute(
        "CREATE TABLE marts.dim_products (product_id INTEGER, name VARCHAR, category VARCHAR)"
    )
    con.execute("INSERT INTO marts.dim_products VALUES (1, 'Shoe', 'Apparel')")
    con.close()


def test_metadata_discovers_schemas_tables_and_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "platform.duckdb"
    _seed_tables(db_path)
    dbt_path = tmp_path / "dbt_project"
    dbt_path.mkdir()

    ctx = discover_platform_context(AppConfig(db_path=db_path, dbt_path=dbt_path))

    assert "raw" in ctx.schemas
    assert "marts" in ctx.schemas
    assert ctx.tables["raw.transactions"].fqn == "raw.transactions"
    assert ctx.tables["raw.transactions"].columns[0].name == "transaction_id"
    assert ctx.tables["marts.fct_orders"].row_count == 2


def _seed_signature_tables(db_path: Path) -> None:
    con = duckdb.connect(db_path)
    con.execute("CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, order_total DOUBLE)")
    con.execute("INSERT INTO orders VALUES (1, 10, 99.0)")
    con.execute(
        "CREATE TABLE customer_dimension (customer_id INTEGER, email VARCHAR, country VARCHAR)"
    )
    con.execute("INSERT INTO customer_dimension VALUES (10, 'a@example.com', 'US')")
    con.close()


def test_dbt_model_scan_prioritizes_marts_before_staging(tmp_path: Path) -> None:
    db_path = tmp_path / "metadata.duckdb"
    con = duckdb.connect(db_path)
    con.execute("CREATE TABLE t (id INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.close()

    dbt_path = tmp_path / "dbt_project"
    (dbt_path / "models" / "marts").mkdir(parents=True)
    (dbt_path / "models" / "staging").mkdir(parents=True)
    (dbt_path / "models" / "marts" / "fct_sales.sql").write_text("SELECT 1")
    (dbt_path / "models" / "marts" / "dim_customers.sql").write_text("SELECT 2")
    (dbt_path / "models" / "staging" / "stg_sales.sql").write_text("SELECT 3")
    (dbt_path / "models" / "staging" / "stg_customers.sql").write_text("SELECT 4")

    ctx = discover_platform_context(AppConfig(db_path=db_path, dbt_path=dbt_path))

    recommendations = ctx.recommended_models
    assert recommendations.index("fct_sales") < recommendations.index("stg_sales")
    assert recommendations.index("dim_customers") < recommendations.index("stg_sales")


def test_fact_and_dim_classification_uses_name_and_signatures(tmp_path: Path) -> None:
    db_path = tmp_path / "signature.duckdb"
    _seed_signature_tables(db_path)

    ctx = discover_platform_context(AppConfig(db_path=db_path))

    assert "orders" in ctx.candidate_fact_tables
    assert "customer_dimension" in ctx.candidate_dim_tables


def test_missing_dbt_directory_is_handled_gracefully(tmp_path: Path) -> None:
    db_path = tmp_path / "missing_dbt.duckdb"
    con = duckdb.connect(db_path)
    con.execute("CREATE TABLE baseline (id INTEGER)")
    con.execute("INSERT INTO baseline VALUES (1)")
    con.close()

    ctx = discover_platform_context(AppConfig(db_path=db_path, dbt_path=tmp_path / "does_not_exist"))

    assert ctx.tables["main.baseline"].row_count == 1
    assert ctx.recommended_models == []
