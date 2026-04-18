"""Tests for standardized response rendering."""

from __future__ import annotations

import json

from mini_data_platform_agent.intent import Intent
from mini_data_platform_agent.presenter import build_presented_answer, render_human, render_json
from mini_data_platform_agent.types import AgentAnswer, QueryResult


def _sample_answer() -> AgentAnswer:
    return AgentAnswer(
        question="How much in sales did we do last quarter?",
        intent=Intent(
            intent="sales_trend",
            confidence=0.93,
            requested_metric="sales",
            timeframe="last_quarter",
        ),
        sql='SELECT 1 AS metric, "x" FROM sales',
        assumptions=["assumption_a", "assumption_b"],
        result=QueryResult(
            columns=["metric", "x"],
            rows=[{"metric": 1, "x": "a"}, {"metric": 2, "x": "b"}, {"metric": 3, "x": "c"}],
            row_count=3,
            duration_ms=11,
            truncated=True,
        ),
        summary="3 rows returned",
        fallback_reason="low_confidence_fallback",
    )


def test_presenter_sections_and_caveats() -> None:
    answer = _sample_answer()
    payload = build_presented_answer(answer, max_rows=2)

    assert payload.interpretation["question"] == answer.question
    assert payload.interpretation["intent"] == "sales_trend"
    assert payload.sql == answer.sql
    assert payload.summary == answer.summary
    assert payload.row_count == 3
    assert payload.rows == [{"metric": 1, "x": "a"}, {"metric": 2, "x": "b"}]
    assert payload.truncated is True
    assert "assumption_a" in payload.caveats
    assert "Fallback: low_confidence_fallback" in payload.caveats


def test_presenter_json_schema_is_complete() -> None:
    answer = _sample_answer()
    data = json.loads(render_json(answer, max_rows=2))

    expected = {"interpretation", "sql", "summary", "rows", "row_count", "truncated", "caveats"}
    assert expected.issubset(data.keys())
    assert data["interpretation"]["question"] == answer.question
    assert data["interpretation"]["intent"] == "sales_trend"
    assert data["truncated"] is True
    assert isinstance(data["rows"], list)
    assert len(data["rows"]) == 2


def test_presenter_truncates_large_output_with_notice() -> None:
    answer = _sample_answer()
    payload = build_presented_answer(answer, max_rows=1)
    human = render_human(answer, max_rows=1)

    assert payload.rows == [{"metric": 1, "x": "a"}]
    assert payload.truncated is True
    assert "Output truncated to 1 rows for readability." in payload.caveats
    assert "Output truncated to 1 rows for readability." in human
