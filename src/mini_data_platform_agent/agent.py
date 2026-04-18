"""Core ask orchestration for the mini data platform agent."""

from __future__ import annotations

from dataclasses import dataclass

from .adapter import DuckDBAdapter, PlatformAdapter
from .config import AppConfig
from .intent import classify_intent
from .executor import ExecutionError, execute_query
from .templates import render_query_plan
from .sql_validator import SQLValidationError, validate_select_query
from .types import AgentAnswer, Intent, PlatformContext, QueryPlan, QueryResult


@dataclass
class _AskGraphState:
    """Mutable orchestration state for one ask request."""

    question: str
    runtime_config: AppConfig
    adapter: PlatformAdapter
    requested_limit: int | None = None
    context: PlatformContext | None = None
    intent: Intent | None = None
    plan: QueryPlan | None = None
    sql: str = ""
    result: QueryResult | None = None
    fallback_reason: str | None = None


def _bootstrap_state(
    question_text: str,
    runtime_config: AppConfig,
    platform_adapter: PlatformAdapter,
    limit: int | None,
) -> _AskGraphState:
    return _AskGraphState(
        question=question_text,
        runtime_config=runtime_config,
        adapter=platform_adapter,
        requested_limit=limit,
    )


def _node_context(state: _AskGraphState) -> _AskGraphState:
    if not state.adapter.health_check():
        raise RuntimeError("Platform data source is not healthy.")
    state.context = state.adapter.load_context()
    return state


def _node_intent(state: _AskGraphState) -> _AskGraphState:
    state.intent = classify_intent(state.question)
    return state


def _node_plan(state: _AskGraphState) -> _AskGraphState:
    if state.intent is None or state.context is None:
        raise RuntimeError("Intent or context is unavailable during planning.")
    state.plan = render_query_plan(
        state.intent,
        state.context,
        limit=state.runtime_config.effective_limit(state.requested_limit),
    )
    state.fallback_reason = state.plan.fallback_reason
    return state


def _node_validate(state: _AskGraphState) -> _AskGraphState:
    if state.plan is None or state.context is None:
        raise RuntimeError("Plan or context missing before SQL validation.")
    state.sql = validate_select_query(
        state.plan.sql,
        state.context,
        default_limit=state.runtime_config.default_limit,
        max_limit=state.runtime_config.max_limit,
    )
    return state


def _node_execute(state: _AskGraphState) -> _AskGraphState:
    if state.plan is None:
        raise RuntimeError("Plan missing before execution.")
    state.result = execute_query(
        state.sql,
        adapter=state.adapter,
        limit=state.plan.limit,
        timeout_ms=state.runtime_config.query_timeout_ms,
    )
    return state


def _run_ask_graph(state: _AskGraphState) -> _AskGraphState:
    state = _node_context(state)
    state = _node_intent(state)
    state = _node_plan(state)
    state = _node_validate(state)
    state = _node_execute(state)
    return state


def _coerce_output_intent(state: _AskGraphState) -> Intent:
    if state.intent is None:
        raise RuntimeError("Intent stage did not produce a valid classification.")

    if state.fallback_reason and state.intent.intent != "generic":
        return state.intent.model_copy(update={"intent": "generic"})
    return state.intent


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
    state = _bootstrap_state(
        question_text=question_text,
        runtime_config=runtime_config,
        platform_adapter=platform_adapter,
        limit=limit,
    )

    try:
        state = _run_ask_graph(state)
    except (ExecutionError, SQLValidationError) as exc:
        raise RuntimeError(f"Query execution failed: {exc}") from exc
    if state.result is None or state.intent is None or state.plan is None:
        raise RuntimeError("Query pipeline did not produce results.")

    return AgentAnswer(
        question=question_text,
        intent=_coerce_output_intent(state),
        sql=state.sql,
        assumptions=list(state.plan.assumptions),
        result=state.result,
        summary=_coerce_result_summary(state.result),
        fallback_reason=state.fallback_reason,
    )
