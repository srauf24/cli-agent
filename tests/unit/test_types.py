from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from mini_data_platform_agent.types import (
    ColumnMeta,
    Intent,
    PlatformContext,
    QueryPlan,
    QueryResult,
    TableMeta,
)


def test_column_and_table_metadata_models() -> None:
    column = ColumnMeta(name="user_id", dtype="INTEGER", is_nullable=False)
    table = TableMeta(
        name="fct_orders",
        schema="marts",
        columns=[column],
        row_count=100,
        is_view=False,
    )

    assert column.name == "user_id"
    assert table.fqn == "marts.fct_orders"


def test_platform_context_collections() -> None:
    context = PlatformContext(
        schemas=["raw", "marts"],
        tables={
            "marts.fct_orders": TableMeta(
                name="fct_orders",
                schema="marts",
                columns=[ColumnMeta(name="total", dtype="DOUBLE")],
            )
        },
        candidate_fact_tables=["fct_orders"],
        candidate_dim_tables=["dim_customers"],
        recommended_models=["dim_products"],
        discovered_at=datetime(2026, 1, 1),
    )

    assert context.schemas == ["raw", "marts"]
    assert "marts.fct_orders" in context.tables
    assert context.recommended_models == ["dim_products"]
    assert context.discovered_at.year == 2026


def test_intent_validation() -> None:
    intent = Intent(intent="clv", confidence=0.87, top_n=3, timeframe="last_quarter")
    assert intent.intent == "clv"
    assert intent.top_n == 3

    with pytest.raises(ValidationError):
        Intent(intent="clv", confidence=1.5)


def test_query_plan_and_result_models() -> None:
    intent = Intent(intent="sales_trend", confidence=0.9)
    plan = QueryPlan(
        sql="SELECT 1 AS metric",
        intent=intent,
        assumptions=["defaulting status filter"],
        limit=50,
    )

    assert plan.limit == 50
    assert plan.assumptions == ["defaulting status filter"]

    result = QueryResult(
        columns=["metric"],
        rows=[{"metric": 10}],
        row_count=1,
        duration_ms=50,
    )

    assert result.rows[0]["metric"] == 10
    assert result.duration_ms == 50
