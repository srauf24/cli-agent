"""Tests for shared fixture provisioning helpers."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import (
    provision_miniplatform_warehouse,
    snapshot_repository_warehouse,
    warehouse_signature,
)


def test_fixture_provisioning_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "mini_platform.duckdb"

    provision_miniplatform_warehouse(db_path)
    first_signature = warehouse_signature(db_path)

    provision_miniplatform_warehouse(db_path)
    second_signature = warehouse_signature(db_path)

    assert first_signature == second_signature


def test_columns_and_types_stay_stable(tmp_path: Path) -> None:
    db_path = tmp_path / "mini_platform.duckdb"
    provision_miniplatform_warehouse(db_path)

    signature = warehouse_signature(db_path)
    expected = {
        "main.orders": [
            "order_id:INTEGER",
            "customer_id:INTEGER",
            "order_date:DATE",
            "total_revenue:DOUBLE",
            "status:VARCHAR",
        ],
        "main.users": [
            "user_id:INTEGER",
            "customer_id:INTEGER",
            "is_active:BOOLEAN",
            "created_at:TIMESTAMP",
        ],
        "marts.dim_customers": [
            "customer_id:INTEGER",
            "customer_name:VARCHAR",
            "country:VARCHAR",
            "segment:VARCHAR",
        ],
        "marts.dim_products": [
            "product_id:INTEGER",
            "product_name:VARCHAR",
            "category:VARCHAR",
            "is_active:BOOLEAN",
        ],
        "marts.fct_orders": [
            "order_id:INTEGER",
            "customer_id:INTEGER",
            "order_date:DATE",
            "total_revenue:DOUBLE",
            "product_id:INTEGER",
            "order_item_count:INTEGER",
        ],
        "raw.customers": [
            "customer_id:INTEGER",
            "customer_name:VARCHAR",
            "email:VARCHAR",
            "country:VARCHAR",
            "signup_date:DATE",
        ],
        "raw.orders": [
            "order_id:INTEGER",
            "customer_id:INTEGER",
            "order_ts:TIMESTAMP",
            "order_total:DOUBLE",
            "currency:VARCHAR",
        ],
        "raw.products": [
            "product_id:INTEGER",
            "product_name:VARCHAR",
            "category:VARCHAR",
            "list_price:DOUBLE",
        ],
        "raw.transactions": [
            "transaction_id:INTEGER",
            "order_id:INTEGER",
            "product_id:INTEGER",
            "customer_id:INTEGER",
            "quantity:INTEGER",
            "unit_price:DOUBLE",
            "transaction_ts:TIMESTAMP",
        ],
        "staging.stg_order_lines": [
            "transaction_id:INTEGER",
            "order_id:INTEGER",
            "product_id:INTEGER",
            "customer_id:INTEGER",
            "quantity:INTEGER",
            "unit_price:DOUBLE",
            "transaction_ts:TIMESTAMP",
        ],
        "staging.stg_transactions": [
            "transaction_id:INTEGER",
            "order_id:INTEGER",
            "product_id:INTEGER",
            "customer_id:INTEGER",
            "quantity:INTEGER",
            "unit_price:DOUBLE",
            "transaction_ts:TIMESTAMP",
        ],
    }

    assert set(expected).issubset(set(signature))
    for key, expected_columns in expected.items():
        assert signature[key] == expected_columns


def test_fixture_usage_does_not_mutate_repo_warehouse(tmp_path: Path) -> None:
    before = snapshot_repository_warehouse()
    # Use fixture helpers on temporary files only.
    provision_miniplatform_warehouse(tmp_path / "fixture_a.duckdb")
    provision_miniplatform_warehouse(tmp_path / "fixture_b.duckdb")
    snapshot_repository_warehouse()
    after = snapshot_repository_warehouse()

    assert before == after
