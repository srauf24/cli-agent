"""Tests for CLI command integration and output modes."""

from __future__ import annotations

from pathlib import Path

import json

from typer.testing import CliRunner

from mini_data_platform_agent.cli import app
from mini_data_platform_agent.intent import Intent
from mini_data_platform_agent.types import AgentAnswer, QueryResult


def _sample_answer() -> AgentAnswer:
    return AgentAnswer(
        question="sample question",
        intent=Intent(
            intent="sales_trend",
            confidence=0.81,
            requested_metric="revenue",
            timeframe="last_quarter",
        ),
        sql="SELECT 1 AS col LIMIT 1",
        assumptions=["unit_test_assumption"],
        result=QueryResult(
            columns=["col"],
            rows=[{"col": 1}],
            row_count=1,
            duration_ms=11,
            truncated=False,
        ),
        summary="1 row returned",
    )


def test_cli_ask_includes_sql_output(monkeypatch) -> None:
    def _fake_answer_question(*_args, **_kwargs) -> AgentAnswer:
        return _sample_answer()

    monkeypatch.setattr("mini_data_platform_agent.cli.answer_question", _fake_answer_question)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["How much in sales did we do last quarter?"],
        env={"MINI_AGENT_DB_PATH": "/tmp/fake-noop.duckdb"},
    )

    assert result.exit_code == 0
    assert "SQL:" in result.output
    assert "SELECT 1 AS col LIMIT 1" in result.output


def test_cli_json_returns_complete_schema(monkeypatch) -> None:
    def _fake_answer_question(*_args, **_kwargs) -> AgentAnswer:
        return _sample_answer()

    monkeypatch.setattr("mini_data_platform_agent.cli.answer_question", _fake_answer_question)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["How much in sales did we do last quarter?", "--json"],
        env={"MINI_AGENT_DB_PATH": "/tmp/fake-noop.duckdb"},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {
        "interpretation",
        "sql",
        "summary",
        "rows",
        "row_count",
        "truncated",
        "caveats",
        "duration_ms",
    }
    assert payload["interpretation"]["intent"] == "sales_trend"
    assert payload["sql"] == "SELECT 1 AS col LIMIT 1"


def test_cli_bad_db_path_fails_with_error_message(tmp_path: Path) -> None:
    bad_path = tmp_path / "does_not_exist.duckdb"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["How much in sales did we do last quarter?"],
        env={"MINI_AGENT_DB_PATH": str(bad_path), "MINI_AGENT_DBT_PATH": str(tmp_path / "missing_dbt")},
    )

    assert result.exit_code == 1
    assert "error: Platform data source is not healthy." in result.output


def test_cli_default_limit_enforced_from_flag(monkeypatch) -> None:
    captured = {"limit": None}

    def _fake_answer_question(*_args, **kwargs) -> AgentAnswer:
        captured["limit"] = kwargs.get("limit")
        return _sample_answer()

    monkeypatch.setattr("mini_data_platform_agent.cli.answer_question", _fake_answer_question)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["How much in sales did we do last quarter?", "--limit", "7"],
        env={"MINI_AGENT_DB_PATH": "/tmp/fake-noop.duckdb"},
    )
    assert result.exit_code == 0
    assert captured["limit"] == 7


def test_cli_parses_special_characters(monkeypatch) -> None:
    captured = {"question": None}
    special_question = "What% of sales in Q4? Revenue (US $) ↑ 20% @ max!"

    def _fake_answer_question(*_args, **kwargs) -> AgentAnswer:
        captured["question"] = kwargs.get("question", _args[0] if _args else None)
        return _sample_answer()

    monkeypatch.setattr("mini_data_platform_agent.cli.answer_question", _fake_answer_question)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [special_question],
        env={"MINI_AGENT_DB_PATH": "/tmp/fake-noop.duckdb"},
    )

    assert result.exit_code == 0
    assert captured["question"] == special_question
