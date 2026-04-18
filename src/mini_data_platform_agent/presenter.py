"""Response formatting utilities for human and machine output."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .types import AgentAnswer


@dataclass(frozen=True)
class PresentedAnswer:
    """Canonical payload for CLI and downstream consumers."""

    interpretation: dict
    sql: str
    summary: str
    rows: list[dict]
    row_count: int
    caveats: list[str]
    truncated: bool
    duration_ms: int | None = None


def _row_limit_notice(max_rows: int) -> str:
    return f"Output truncated to {max_rows} rows for readability."


def build_presented_answer(answer: AgentAnswer, *, max_rows: int = 5) -> PresentedAnswer:
    """Build the unified response payload from an AgentAnswer."""

    caveats: list[str] = list(answer.assumptions)
    if answer.fallback_reason:
        caveats.append(f"Fallback: {answer.fallback_reason}")

    rows = answer.result.rows if answer.result is not None else []
    row_count = len(rows)

    displayed_rows = rows[:max_rows]
    truncated = bool(answer.result and answer.result.truncated) or len(rows) > max_rows
    if truncated:
        caveats.append(_row_limit_notice(max_rows))

    interpretation = {
        "question": answer.question,
        "intent": answer.intent.intent,
        "confidence": answer.intent.confidence,
        "timeframe": answer.intent.timeframe,
        "top_n": answer.intent.top_n,
        "requested_metric": answer.intent.requested_metric,
        "extracted_filters": answer.intent.extracted_filters,
    }

    duration_ms = answer.result.duration_ms if answer.result is not None else None

    return PresentedAnswer(
        interpretation=interpretation,
        sql=answer.sql,
        summary=answer.summary,
        rows=displayed_rows,
        row_count=row_count,
        caveats=caveats,
        truncated=truncated,
        duration_ms=duration_ms,
    )


def render_json(answer: AgentAnswer, *, max_rows: int = 5) -> str:
    """Render machine-readable answer payload."""

    payload = build_presented_answer(answer, max_rows=max_rows)
    return json.dumps(
        {
            "interpretation": payload.interpretation,
            "sql": payload.sql,
            "summary": payload.summary,
            "rows": payload.rows,
            "row_count": payload.row_count,
            "truncated": payload.truncated,
            "caveats": payload.caveats,
            "duration_ms": payload.duration_ms,
        },
        indent=2,
    )


def render_human(answer: AgentAnswer, *, max_rows: int = 5) -> str:
    """Render human-readable answer payload."""

    payload = build_presented_answer(answer, max_rows=max_rows)
    lines = [
        "Question: " + payload.interpretation["question"],
        f"Intent: {payload.interpretation['intent']} (confidence={payload.interpretation['confidence']:.2f})",
        "Interpretation:",
        f"  - timeframe: {payload.interpretation['timeframe']!s}",
        f"  - requested_metric: {payload.interpretation['requested_metric']!s}",
        "Caveats: " + (", ".join(payload.caveats) if payload.caveats else "none"),
        "SQL:",
        payload.sql,
        f"Summary: {payload.summary}",
        f"Rows: {payload.row_count}",
    ]

    if payload.rows:
        for row in payload.rows:
            lines.append(str(row))
    elif payload.row_count == 0:
        lines.append("No rows returned.")

    return "\n".join(lines)
