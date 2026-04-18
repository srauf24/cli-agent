"""Integration tests for full prompt-to-SQL execution prompts."""

from __future__ import annotations

import re
from pathlib import Path

from mini_data_platform_agent.agent import answer_question
from mini_data_platform_agent.config import AppConfig
from mini_data_platform_agent.presenter import build_presented_answer

from tests.conftest import provision_miniplatform_dbt_project, provision_miniplatform_warehouse


FORBIDDEN_WRITE_PATTERNS = (
    r"\binsert\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\bdrop\b",
    r"\balter\b",
    r"\bcreate\b",
    r"\btruncate\b",
    r"\battach\b",
    r"\bdetach\b",
)


def _build_prompt_config(tmp_path: Path) -> AppConfig:
    db_path = tmp_path / "platform.duckdb"
    dbt_path = tmp_path / "dbt_project"
    provision_miniplatform_warehouse(db_path)
    provision_miniplatform_dbt_project(dbt_path)
    return AppConfig(db_path=db_path, dbt_path=dbt_path)


def _assert_read_only_sql(sql: str) -> None:
    lowered = sql.lower()
    for pattern in FORBIDDEN_WRITE_PATTERNS:
        assert not re.search(pattern, lowered), f"found write-like keyword in SQL: {pattern}"
    assert lowered.strip().startswith("select") or lowered.strip().startswith("with"), (
        "generated SQL should start with SELECT/WITH after validation"
    )


def test_sales_trend_prompt_returns_numeric_result(tmp_path: Path) -> None:
    config = _build_prompt_config(tmp_path)
    question = "How much in sales did we do last quarter?"

    response = answer_question(question, config=config)
    presented = build_presented_answer(response, max_rows=5)

    assert response.intent.intent == "sales_trend"
    assert response.result is not None
    assert response.result.row_count >= 1
    assert any(isinstance(value, (int, float)) for row in response.result.rows for value in row.values())
    assert "sales_trend_template" in response.assumptions
    assert "question" in presented.interpretation and "intent" in presented.interpretation
    assert presented.interpretation["intent"] == "sales_trend"
    assert isinstance(presented.caveats, list) and presented.caveats
    _assert_read_only_sql(response.sql)


def test_copurchase_prompt_returns_product_pair_list(tmp_path: Path) -> None:
    config = _build_prompt_config(tmp_path)
    question = "Which two products are most frequently bought together?"

    response = answer_question(question, config=config)

    assert response.intent.intent == "copurchase"
    assert response.result is not None
    assert response.result.row_count >= 1
    assert len(response.result.rows[0]) >= 3
    first_row = response.result.rows[0]
    assert "product_a" in first_row and "product_b" in first_row and "co_purchase_count" in first_row
    assert first_row["product_a"] != first_row["product_b"]
    assert "copurchase_template" in response.assumptions
    assert "duplicate_pair_elimination_with_ordering" in response.assumptions
    _assert_read_only_sql(response.sql)


def test_anomaly_prompt_returns_anomalies_or_empty_with_caveat(tmp_path: Path) -> None:
    config = _build_prompt_config(tmp_path)
    question = "Are there any anomalies with how we sell products?"

    response = answer_question(question, config=config)
    presented = build_presented_answer(response, max_rows=5)

    assert response.intent.intent == "anomalies"
    assert response.result is not None
    assert response.result.row_count >= 0
    assert "anomaly_template" in response.assumptions
    assert any("anomaly" in caveat.lower() for caveat in presented.caveats)
    if response.result.row_count == 0:
        assert "no rows" in response.summary.lower() or "no rows returned" in response.summary.lower()
    _assert_read_only_sql(response.sql)


def test_clv_prompt_returns_clv_metric(tmp_path: Path) -> None:
    config = _build_prompt_config(tmp_path)
    question = "What’s our average customer lifetime value?"

    response = answer_question(question, config=config)

    assert response.intent.intent == "clv"
    assert response.result is not None
    assert response.result.row_count == 1
    assert len(response.result.rows) == 1
    row = response.result.rows[0]
    assert "avg_customer_lifetime_value" in row
    assert isinstance(row["avg_customer_lifetime_value"], (int, float))
    assert "clv_template" in response.assumptions
    _assert_read_only_sql(response.sql)


def test_top_n_prompt_returns_bounded_and_executable(tmp_path: Path) -> None:
    config = _build_prompt_config(tmp_path)
    question = "Show top 2 products by sales"

    response = answer_question(question, config=config)
    presented = build_presented_answer(response, max_rows=5)

    assert response.intent.intent == "top_n"
    assert response.result is not None
    assert response.result.row_count <= 2
    assert response.assumptions
    assert any("top_n_template" in caveat for caveat in response.assumptions)
    assert any("top_n_template" in caveat for caveat in presented.caveats)
    assert response.sql.lower().startswith("select") or response.sql.lower().startswith("with")
    _assert_read_only_sql(response.sql)
