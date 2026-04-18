"""Tests for SQL safety validation and context allowlisting."""

from __future__ import annotations

import pytest

from mini_data_platform_agent.sql_validator import SQLValidationError, validate_select_query
from mini_data_platform_agent.types import ColumnMeta, PlatformContext, TableMeta


def _context() -> PlatformContext:
    return PlatformContext(
        tables={
            "main.fct_orders": TableMeta(
                name="fct_orders",
                schema="main",
                columns=[
                    ColumnMeta(name="order_id", dtype="INTEGER"),
                    ColumnMeta(name="product_id", dtype="INTEGER"),
                    ColumnMeta(name="total_revenue", dtype="DOUBLE"),
                ],
            ),
            "main.dim_products": TableMeta(
                name="dim_products",
                schema="main",
                columns=[
                    ColumnMeta(name="product_id", dtype="INTEGER"),
                    ColumnMeta(name="product_name", dtype="VARCHAR"),
                ],
            ),
        }
    )


def test_block_mutation_statements() -> None:
    ctx = _context()
    blocked = [
        "INSERT INTO main.fct_orders VALUES (1, 2, 3)",
        "UPDATE main.fct_orders SET total_revenue = 0",
        "DELETE FROM main.fct_orders",
        "DROP TABLE main.fct_orders",
        "ALTER TABLE main.fct_orders ADD COLUMN test INTEGER",
        "CREATE TABLE t (id INTEGER)",
        "TRUNCATE TABLE main.fct_orders",
        "ATTACH ':memory:' AS mem",
        "DETACH DATABASE mem",
    ]

    for sql in blocked:
        with pytest.raises(SQLValidationError):
            validate_select_query(sql, ctx, default_limit=100, max_limit=1000)


def test_only_select_or_with_allowed() -> None:
    ctx = _context()

    with pytest.raises(SQLValidationError):
        validate_select_query("DELETE FROM main.fct_orders", ctx, default_limit=100, max_limit=1000)

    with pytest.raises(SQLValidationError):
        validate_select_query("BEGIN; SELECT * FROM main.fct_orders", ctx, default_limit=100, max_limit=1000)

    assert "SELECT" in validate_select_query(
        "WITH x AS (SELECT order_id FROM main.fct_orders) SELECT order_id FROM x",
        ctx,
        default_limit=100,
        max_limit=1000,
    )


def test_unknown_table_is_rejected() -> None:
    ctx = _context()

    with pytest.raises(SQLValidationError) as exc:
        validate_select_query("SELECT * FROM unknown_table", ctx, default_limit=100, max_limit=1000)

    assert "Disallowed table" in str(exc.value)


def test_unknown_column_is_rejected() -> None:
    ctx = _context()

    with pytest.raises(SQLValidationError) as exc:
        validate_select_query(
            "SELECT missing_col FROM main.fct_orders", ctx, default_limit=100, max_limit=1000
        )

    assert "Unknown" in str(exc.value)


def test_limit_normalization_appends_and_caps() -> None:
    ctx = _context()

    sql_default = validate_select_query(
        'SELECT order_id FROM main.fct_orders', ctx, default_limit=50, max_limit=200
    )
    assert "LIMIT 50" in sql_default

    sql_capped = validate_select_query(
        'SELECT order_id FROM main.fct_orders LIMIT 999', ctx, default_limit=50, max_limit=200
    )
    assert "LIMIT 200" in sql_capped


def test_validation_error_is_actionable() -> None:
    ctx = _context()

    with pytest.raises(SQLValidationError) as exc:
        validate_select_query("UPDATE main.fct_orders SET total_revenue = 0", ctx, default_limit=100, max_limit=1000)

    message = str(exc.value)
    assert "Forbidden keyword" in message
