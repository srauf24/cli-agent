"""Core ask orchestration for the mini data platform agent."""

from __future__ import annotations

from .adapter import DuckDBAdapter, PlatformAdapter
from .config import AppConfig
from .intent import classify_intent
from .executor import ExecutionError, execute_query
from .templates import render_query_plan
from .sql_validator import SQLValidationError, validate_select_query
from .types import AgentAnswer, QueryResult


def _coerce_result_summary(result: QueryResult) -> str:
    if result.row_count == 0:
        return "No rows returned."
    if not result.columns or not result.rows:
        return "Query returned no structured output."
    if len(result.columns) == 1:
        first_value = result.rows[0].get(result.columns[0], None)
        return f"Top result: {result.columns[0]}={first_value}"
    return f"Returned {result.row_count} row(s) across {len(result.columns)} column(s)."


def answer_question(
    question: str,
    *,
    config: AppConfig | None = None,
    adapter: PlatformAdapter | None = None,
    limit: int | None = None,
) -> AgentAnswer:
    """Resolve one ad-hoc analytics question into an answer."""

    runtime_config = config or AppConfig.from_env()
    question_text = (question or "").strip()
    if not question_text:
        raise ValueError("A non-empty question is required.")

    platform_adapter = adapter or DuckDBAdapter(runtime_config)
    if not platform_adapter.health_check():
        raise RuntimeError("Platform data source is not healthy.")

    context = platform_adapter.load_context()
    intent = classify_intent(question_text)
    plan = render_query_plan(intent, context, limit=runtime_config.effective_limit(limit))
    sql = validate_select_query(
        plan.sql,
        context,
        default_limit=runtime_config.default_limit,
        max_limit=runtime_config.max_limit,
    )

    try:
        result = execute_query(
            sql,
            adapter=platform_adapter,
            limit=plan.limit,
            timeout_ms=runtime_config.query_timeout_ms,
        )
    except (ExecutionError, SQLValidationError) as exc:
        raise RuntimeError(f"Query execution failed: {exc}") from exc

    return AgentAnswer(
        question=question_text,
        intent=intent,
        sql=sql,
        assumptions=list(plan.assumptions),
        result=result,
        summary=_coerce_result_summary(result),
    )
