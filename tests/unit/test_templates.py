"""Tests for template selection and SQL rendering."""

from __future__ import annotations

import pytest

from mini_data_platform_agent.intent import Intent
from mini_data_platform_agent.templates import TemplateRenderError, render_query_plan, template_for_intent
from mini_data_platform_agent.types import ColumnMeta, PlatformContext, TableMeta


def _context_with_sales_facts() -> PlatformContext:
    context = PlatformContext(
        schemas=["marts"],
        tables={
            "marts.fct_orders": TableMeta(
                name="fct_orders",
                schema="marts",
                columns=[
                    ColumnMeta(name="order_id", dtype="INTEGER"),
                    ColumnMeta(name="customer_id", dtype="INTEGER"),
                    ColumnMeta(name="order_date", dtype="TIMESTAMP"),
                    ColumnMeta(name="ordered_at", dtype="TIMESTAMP"),
                    ColumnMeta(name="total_revenue", dtype="DOUBLE"),
                    ColumnMeta(name="product_id", dtype="INTEGER"),
                ],
            )
        },
        candidate_fact_tables=["fct_orders"],
        candidate_dim_tables=["dim_products"],
    )
    return context


def test_template_selection_by_intent() -> None:
    ctx = _context_with_sales_facts()

    assert template_for_intent(
        Intent(intent="sales_trend", confidence=0.95),
        ctx,
    ) == "sales_trend"
    assert template_for_intent(
        Intent(intent="copurchase", confidence=0.95),
        ctx,
    ) == "copurchase"
    assert template_for_intent(
        Intent(intent="clv", confidence=0.95),
        ctx,
    ) == "clv"
    assert template_for_intent(
        Intent(intent="anomalies", confidence=0.95),
        ctx,
    ) == "anomalies"
    assert template_for_intent(
        Intent(intent="top_n", confidence=0.95),
        ctx,
    ) == "top_n"
    assert template_for_intent(Intent(intent="unknown", confidence=0.95), ctx) == "generic"
    assert template_for_intent(Intent(intent="sales_trend", confidence=0.1), ctx) == "generic"


def test_rendering_fills_discovered_tables_and_columns_only() -> None:
    ctx = _context_with_sales_facts()
    intent = Intent(intent="sales_trend", confidence=0.95, timeframe="last_quarter")
    plan = render_query_plan(intent, ctx, limit=50)

    # Ensure renderer used discovered table and discovered columns only.
    assert 'FROM "marts"."fct_orders"' in plan.sql
    assert '"order_date"' in plan.sql
    assert '"total_revenue"' in plan.sql
    assert "transaction_date" not in plan.sql


def test_last_quarter_filter_contains_date_window_logic() -> None:
    ctx = _context_with_sales_facts()
    intent = Intent(intent="sales_trend", confidence=0.95, timeframe="last_quarter")
    plan = render_query_plan(intent, ctx)

    assert "DATE_TRUNC('quarter', CURRENT_DATE) - INTERVAL '3 months'" in plan.sql
    assert "DATE_TRUNC('quarter', CURRENT_DATE)" in plan.sql
    assert ">= " in plan.sql
    assert "< " in plan.sql


def test_copurchase_query_avoids_duplicate_pairs_and_limits_output() -> None:
    ctx = _context_with_sales_facts()
    intent = Intent(intent="copurchase", confidence=0.95, top_n=3)
    plan = render_query_plan(intent, ctx)

    assert "product_a" in plan.sql
    assert "product_b" in plan.sql
    assert "co_purchase_count" in plan.sql
    assert "t1.\"product_id\" < t2.\"product_id\"" in plan.sql
    assert "LIMIT 3" in plan.sql


def test_generic_fallback_requires_context_or_fails_clearly() -> None:
    empty_ctx = PlatformContext()
    intent = Intent(intent="sales_trend", confidence=0.0)
    with pytest.raises(TemplateRenderError):
        render_query_plan(intent, empty_ctx)
