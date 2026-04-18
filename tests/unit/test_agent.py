"""Tests for ask orchestration and CLI exposure."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from mini_data_platform_agent.agent import answer_question
from mini_data_platform_agent.cli import app
from mini_data_platform_agent.config import AppConfig


def _seed_sales_db(path: Path) -> None:
    con = duckdb.connect(path)
    con.execute("CREATE TABLE fct_orders (order_id INTEGER, order_date DATE, total_revenue DOUBLE)")
    con.execute("INSERT INTO fct_orders VALUES (1, DATE '2026-02-05', 100.5), (2, DATE '2026-03-10', 30.0)")
    con.close()


def test_answer_question_end_to_end(tmp_path: Path) -> None:
    db_path = tmp_path / "platform.duckdb"
    _seed_sales_db(db_path)

    response = answer_question(
        "How much in sales did we do last quarter?",
        config=AppConfig(db_path=db_path, dbt_path=tmp_path / "missing_dbt"),
    )

    assert response.intent.intent == "sales_trend"
    assert response.sql.startswith("SELECT")
    assert response.result is not None
    assert response.result.row_count >= 0
    assert "Summary:" not in response.summary


def test_cli_ask_outputs_human_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "platform.duckdb"
    _seed_sales_db(db_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["How much in sales did we do last quarter?"],
        env={"MINI_AGENT_DB_PATH": str(db_path), "MINI_AGENT_DBT_PATH": str(tmp_path / "missing_dbt")},
    )
    assert result.exit_code == 0
    assert "Question:" in result.output
    assert "Intent:" in result.output
    assert "Rows:" in result.output
    assert "SQL:" in result.output


def test_answer_question_rejects_empty_question(tmp_path: Path) -> None:
    db_path = tmp_path / "platform.duckdb"
    _seed_sales_db(db_path)
    with pytest.raises(ValueError):
        answer_question(
            "",
            config=AppConfig(db_path=db_path, dbt_path=tmp_path / "missing_dbt"),
        )
