"""Tests for the graph-style ask orchestration in the agent layer."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from mini_data_platform_agent import agent
from mini_data_platform_agent.config import AppConfig
from mini_data_platform_agent.intent import Intent
from mini_data_platform_agent.sql_validator import SQLValidationError
from mini_data_platform_agent.types import QueryPlan


def _seed_sales_db(path: Path) -> None:
    con = duckdb.connect(path)
    con.execute(
        """
        CREATE TABLE fct_orders (
            order_id INTEGER,
            order_date DATE,
            total_revenue DOUBLE,
            product_id INTEGER,
            customer_id INTEGER
        )
        """
    )
    con.execute(
        """
        INSERT INTO fct_orders VALUES
            (1, CURRENT_DATE, 120.0, 100, 10),
            (2, CURRENT_DATE, 85.0, 101, 11)
        """
    )
    con.close()


def test_graph_happy_path_resolves_to_query_result(tmp_path: Path) -> None:
    db_path = tmp_path / "platform.duckdb"
    _seed_sales_db(db_path)

    response = agent.answer_question(
        "How much in sales did we do this quarter?",
        config=AppConfig(db_path=db_path, dbt_path=tmp_path / "missing_dbt"),
    )

    assert response.result is not None
    assert response.result.row_count >= 1
    assert response.intent.intent == "sales_trend"
    assert response.fallback_reason is None
    assert "sales_trend_template" in response.assumptions


def test_graph_blocks_invalid_query_without_executor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "platform.duckdb"
    _seed_sales_db(db_path)

    called = {"execute": False}

    def _disallow_execute(*_args, **_kwargs) -> None:
        called["execute"] = True
        raise RuntimeError("Executor was called unexpectedly")

    def _invalid_query(*_args, **_kwargs) -> str:
        raise SQLValidationError("forbidden keyword")

    monkeypatch.setattr(agent, "validate_select_query", _invalid_query)
    monkeypatch.setattr(agent, "execute_query", _disallow_execute)

    with pytest.raises(RuntimeError, match="Query execution failed"):
        agent.answer_question(
            "How much in sales did we do this quarter?",
            config=AppConfig(db_path=db_path, dbt_path=tmp_path / "missing_dbt"),
        )

    assert called["execute"] is False


def test_graph_carries_assumptions_and_caveats(tmp_path: Path) -> None:
    db_path = tmp_path / "platform.duckdb"
    _seed_sales_db(db_path)

    # Patch only plan creation so we can assert the response carries deterministic caveats.
    original_render = agent.render_query_plan

    def _fake_plan(*_args, **_kwargs) -> QueryPlan:
        return QueryPlan(
            sql='SELECT 1 AS marker LIMIT 1',
            intent=Intent(intent="generic", confidence=0.99),
            assumptions=["assumption_a", "assumption_b"],
            required_filters={},
            limit=1,
            fallback_reason="manual_fallback_caveat",
        )

    try:
        agent.render_query_plan = _fake_plan
        response = agent.answer_question(
            "Any question that returns one row",
            config=AppConfig(db_path=db_path, dbt_path=tmp_path / "missing_dbt"),
        )
    finally:
        agent.render_query_plan = original_render

    assert response.assumptions == ["assumption_a", "assumption_b"]
    assert response.fallback_reason == "manual_fallback_caveat"
    assert response.result is not None
    assert response.result.rows == [{"marker": 1}]


def test_graph_fallback_on_low_confidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "platform.duckdb"
    _seed_sales_db(db_path)

    def _low_confidence_intent(_question: str) -> Intent:
        return Intent(intent="sales_trend", confidence=0.10)

    monkeypatch.setattr(agent, "classify_intent", _low_confidence_intent)

    response = agent.answer_question(
        "Unclear query",
        config=AppConfig(db_path=db_path, dbt_path=tmp_path / "missing_dbt"),
    )

    assert response.intent.intent == "generic"
    assert response.fallback_reason == "low_confidence_fallback"
    assert "generic_fallback_template" in response.assumptions
