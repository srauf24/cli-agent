"""Shared Pydantic models used by the agent backend."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ColumnMeta(BaseModel):
    """Metadata for a table column."""

    model_config = ConfigDict(frozen=True)

    name: str
    dtype: str
    is_nullable: bool | None = None


class TableMeta(BaseModel):
    """Metadata for a single table or view."""

    model_config = ConfigDict(frozen=True)

    name: str
    schema_name: str = Field(..., alias="schema")
    columns: list[ColumnMeta]
    row_count: int | None = None
    is_view: bool = False

    @property
    def fqn(self) -> str:
        return f"{self.schema_name}.{self.name}"


class PlatformContext(BaseModel):
    """Discovered context snapshot for the current data platform."""

    model_config = ConfigDict(frozen=True)

    schemas: list[str] = Field(default_factory=list)
    tables: dict[str, TableMeta] = Field(default_factory=dict)
    candidate_fact_tables: list[str] = Field(default_factory=list)
    candidate_dim_tables: list[str] = Field(default_factory=list)
    recommended_models: list[str] = Field(default_factory=list)
    discovered_at: datetime | None = None


class Intent(BaseModel):
    """Normalized question intent for query planning."""

    model_config = ConfigDict(frozen=True)

    intent: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    extracted_filters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    requested_metric: str | None = None
    timeframe: str | None = None
    top_n: int | None = Field(default=None, ge=1)


class QueryPlan(BaseModel):
    """Plan returned by the query generator."""

    model_config = ConfigDict(frozen=True)

    sql: str
    intent: Intent
    assumptions: list[str] = Field(default_factory=list)
    required_filters: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )
    limit: int = Field(ge=1, default=200)
    fallback_reason: str | None = None


class QueryResult(BaseModel):
    """Executed SQL result envelope."""

    model_config = ConfigDict(frozen=True)

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: int
    truncated: bool = False


class AgentAnswer(BaseModel):
    """Structured response returned from a question resolution."""

    model_config = ConfigDict(frozen=True)

    question: str
    intent: Intent
    sql: str
    assumptions: list[str] = Field(default_factory=list)
    result: QueryResult | None = None
    summary: str = ""
    fallback_reason: str | None = None
