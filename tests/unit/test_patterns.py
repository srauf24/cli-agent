"""Tests for Evidence pattern extraction."""

from __future__ import annotations

from pathlib import Path

from mini_data_platform_agent.patterns import (
    discover_patterns,
    extract_patterns_from_text,
    extract_selected_fields,
)


def test_extract_sql_blocks_from_markdown_pages(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence" / "pages"
    evidence.mkdir(parents=True)
    (evidence / "sales.md").write_text(
        """
        # Sales

        ```sql daily_sales
        SELECT
            transaction_id,
            total
        FROM orders
        ```

        ```sql
        SELECT customer_id FROM customers
        ```
        """
    )
    (evidence / "customers.md").write_text(
        """
        # Customers

        ```sql top_customers
        SELECT user_id, lifetime_value FROM customers
        ```
        """
    )

    patterns = discover_patterns(evidence)
    assert len(patterns) == 3
    names = [p.query_name for p in patterns]
    assert set(names) == {"daily_sales", "top_customers", "query_2"}
    assert any(name.startswith("query_") for name in names)
    fields_by_name = {p.query_name: p.fields for p in patterns}
    assert fields_by_name["daily_sales"] == ["transaction_id", "total"]
    assert fields_by_name["top_customers"] == ["user_id", "lifetime_value"]
    assert fields_by_name["query_2"] == ["customer_id"]


def test_field_dedup_and_normalization() -> None:
    sql = """
    SELECT
        customer_id AS Customer_ID,
        customer_id as customer_id,
        product_name AS \"Product Name\",
        SUM(total) AS total_revenue,
        SUM(total) AS total_revenue
    FROM warehouse.fct_orders
    """

    fields = extract_selected_fields(sql)
    assert fields == ["customer_id", "product_name", "total_revenue"]


def test_parser_resilience_with_malformed_fences(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence" / "pages"
    evidence.mkdir(parents=True)
    (evidence / "broken.md").write_text(
        """
        ```sql good_query
        SELECT 1 AS ok
        ```

        ```sql broken_query
        SELECT 2 AS bad
        """
    )

    patterns = discover_patterns(evidence)
    assert len(patterns) == 1
    assert patterns[0].query_name == "good_query"
    assert patterns[0].fields == ["ok"]


def test_extract_from_raw_markdown_blocks_only() -> None:
    text = """
    # Example

    ```sql alpha
    SELECT col_one, col_two FROM t
    ```

    ```markdown not_sql
    Not SQL
    ```
    """
    blocks = extract_patterns_from_text(text)
    assert blocks == [("alpha", "SELECT col_one, col_two FROM t")]


def test_empty_or_partial_evidence_directories_do_not_fail(tmp_path: Path) -> None:
    empty_dir = tmp_path / "missing"
    assert discover_patterns(empty_dir) == []

    partial_dir = tmp_path / "partial"
    partial_dir.mkdir()
    (partial_dir / "notes.txt").write_text("no markdown pages here")
    assert discover_patterns(partial_dir) == []
