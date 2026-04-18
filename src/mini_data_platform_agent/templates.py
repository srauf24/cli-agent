"""Template-first SQL generation for classified intents."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from datetime import datetime
from typing import Any

from .intent import Intent
from .types import PlatformContext, QueryPlan, TableMeta

_CONFIDENCE_FALLBACK_THRESHOLD = 0.35
_DEFAULT_LIMIT = 200
_FACT_PREFERENCES = ("fct_orders", "fct_order_items", "sales_facts", "orders")
_DIM_PREFERENCES = ("dim_products", "dim_customers", "dim_users", "products", "customers")

SUPPORTED_INTENTS = {
    "sales_trend",
    "copurchase",
    "anomalies",
    "clv",
    "top_n",
}


class TemplateRenderError(RuntimeError):
    """Raised when a template cannot be rendered from discovered context."""


@dataclass(frozen=True)
class _RenderableTable:
    table: TableMeta

    @property
    def fqn(self) -> str:
        return self.table.fqn


def _quote(value: str) -> str:
    """Quote an SQL identifier safely for string formatting."""

    return f'"{value.replace("\"", "\"\"")}"'


def _normalise_identifier(value: str) -> str:
    return re.sub(r"\W+", "", value).lower()


def _find_table_by_preference(
    context: PlatformContext, candidate_names: list[str] | tuple[str, ...]
) -> TableMeta:
    by_name = {table.name.lower(): table for table in context.tables.values()}

    for name in candidate_names:
        if name in by_name:
            return by_name[name]

    for table in context.tables.values():
        if not by_name:
            continue
        for preferred in candidate_names:
            if table.name.lower() == preferred:
                return table

    for table in context.tables.values():
        if not table.is_view:
            return table

    if context.tables:
        return next(iter(context.tables.values()))
    raise TemplateRenderError("Unable to select a table from discovered context.")


def _pick_column(table: TableMeta, candidates: list[str], mandatory: bool = False) -> str:
    column_names = {column.name.lower(): column.name for column in table.columns}
    for candidate in candidates:
        candidate_lower = _normalise_identifier(candidate)
        if candidate_lower in column_names:
            return column_names[candidate_lower]

        for col in table.columns:
            if candidate_lower in _normalise_identifier(col.name):
                return col.name

    if mandatory:
        raise TemplateRenderError(
            f"Unable to find required column from candidates={candidates} in table={table.fqn}"
        )

    if table.columns:
        return table.columns[0].name
    raise TemplateRenderError(f"No usable columns found in table={table.fqn}")


def _resolve_fact_table(context: PlatformContext) -> TableMeta:
    candidates: list[str] = [name.lower() for name in context.candidate_fact_tables]
    if not candidates:
        candidates = list(_FACT_PREFERENCES)

    for preferred in candidates:
        for table in context.tables.values():
            if table.name.lower() == preferred and not table.is_view:
                return table

    if context.candidate_fact_tables:
        for preferred in context.candidate_fact_tables:
            for table in context.tables.values():
                if table.name.lower() == preferred:
                    return table

    for table in context.tables.values():
        if table.name.lower().startswith(("fct_", "fact_")) and not table.is_view:
            return table

    for table in context.tables.values():
        if not table.is_view:
            return table

    if context.tables:
        return next(iter(context.tables.values()))

    raise TemplateRenderError("Unable to resolve fact table; context has no tables.")


def _resolve_dimension_like_table(context: PlatformContext) -> TableMeta:
    for preferred in _DIM_PREFERENCES:
        for table in context.tables.values():
            if table.name.lower() == preferred:
                return table
    for table in context.tables.values():
        if table.is_view:
            continue
        for candidate in _DIM_PREFERENCES:
            if candidate in table.name.lower():
                return table
    if context.candidate_dim_tables:
        for preferred in context.candidate_dim_tables:
            for table in context.tables.values():
                if table.name.lower() == preferred:
                    return table

    if context.tables:
        return next(iter(context.tables.values()))
    raise TemplateRenderError("Unable to resolve dimension-like table; context has no tables.")


def _build_date_filter(date_col: str, timeframe: str | None) -> str:
    if timeframe == "last_quarter":
        return (
            f"{_quote(date_col)} >= DATE_TRUNC('quarter', CURRENT_DATE) - INTERVAL '3 months'\n"
            f"AND {_quote(date_col)} < DATE_TRUNC('quarter', CURRENT_DATE)"
        )
    if timeframe == "this_quarter":
        return (
            f"{_quote(date_col)} >= DATE_TRUNC('quarter', CURRENT_DATE)\n"
            f"AND {_quote(date_col)} < DATE_TRUNC('quarter', CURRENT_DATE) + INTERVAL '3 months'"
        )
    if timeframe == "last_month":
        return (
            f"{_quote(date_col)} >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'\n"
            f"AND {_quote(date_col)} < DATE_TRUNC('month', CURRENT_DATE)"
        )
    if timeframe == "last_year":
        return (
            f"{_quote(date_col)} >= DATE_TRUNC('year', CURRENT_DATE) - INTERVAL '1 year'\n"
            f"AND {_quote(date_col)} < DATE_TRUNC('year', CURRENT_DATE)"
        )
    if timeframe == "ytd":
        return f"{_quote(date_col)} >= DATE_TRUNC('year', CURRENT_DATE)\n"

    current_year = datetime.utcnow().year
    return (
        f"{_quote(date_col)} >= DATE '{current_year}-01-01'\n"
        f"AND {_quote(date_col)} <= CURRENT_DATE"
    )


def _select_template(intent: Intent, context: PlatformContext) -> str:
    if intent.confidence < _CONFIDENCE_FALLBACK_THRESHOLD:
        return "generic"
    if intent.intent in SUPPORTED_INTENTS:
        return intent.intent
    return "generic"


def _template_sales_trend(
    intent: Intent,
    context: PlatformContext,
    limit: int,
) -> QueryPlan:
    table = _resolve_fact_table(context)
    time_col = _pick_column(
        table,
        ["transaction_date", "order_date", "created_at", "order_ts", "ts", "date"],
        mandatory=True,
    )
    metric_col = _pick_column(
        table,
        ["total", "revenue", "amount", "sales", "order_total", "lifetime_value"],
        mandatory=True,
    )
    timeframe = intent.timeframe or "last_30_days"

    date_filter = _build_date_filter(time_col, timeframe)
    requested = intent.requested_metric or "revenue"
    sql = f"""
SELECT
    DATE_TRUNC('day', {_quote(time_col)}) AS period_start,
    SUM({_quote(metric_col)}) AS {requested}_metric
FROM {_quote(table.schema_name)}.{_quote(table.name)}
WHERE {date_filter}
GROUP BY 1
ORDER BY 1 DESC
LIMIT {limit}
""".strip()
    return QueryPlan(
        sql=sql,
        intent=intent,
        assumptions=["sales_trend_template", f"time_col={time_col}", f"metric_col={metric_col}"],
        required_filters={"timeframe": timeframe, "table": table.fqn},
        limit=limit,
    )


def _template_copurchase(
    intent: Intent,
    context: PlatformContext,
    limit: int,
) -> QueryPlan:
    table = _resolve_fact_table(context)
    order_col = _pick_column(table, ["order_id", "transaction_id", "invoice_id"], mandatory=True)
    product_col = _pick_column(
        table,
        ["product_id", "product", "sku", "product_name", "item_id"],
        mandatory=True,
    )

    top_n = max(1, intent.top_n or limit)

    sql = f"""
SELECT
    t1.{_quote(product_col)} AS product_a,
    t2.{_quote(product_col)} AS product_b,
    COUNT(*) AS co_purchase_count
FROM {_quote(table.schema_name)}.{_quote(table.name)} AS t1
JOIN {_quote(table.schema_name)}.{_quote(table.name)} AS t2
  ON t1.{_quote(order_col)} = t2.{_quote(order_col)}
 AND t1.{_quote(product_col)} < t2.{_quote(product_col)}
WHERE t1.{_quote(product_col)} IS NOT NULL
  AND t2.{_quote(product_col)} IS NOT NULL
GROUP BY 1, 2
ORDER BY co_purchase_count DESC
LIMIT {top_n}
""".strip()
    return QueryPlan(
        sql=sql,
        intent=intent,
        assumptions=["copurchase_template", "duplicate_pair_elimination_with_ordering"],
        required_filters={"table": table.fqn, "product_col": product_col, "order_col": order_col},
        limit=top_n,
    )


def _template_clv(intent: Intent, context: PlatformContext, limit: int) -> QueryPlan:
    table = _resolve_fact_table(context)
    customer_col = _pick_column(
        table,
        ["user_id", "customer_id", "account_id", "consumer_id"],
        mandatory=True,
    )
    metric_col = _pick_column(
        table,
        ["total", "revenue", "amount", "lifetime_value", "sales"],
        mandatory=True,
    )
    top_n = max(1, intent.top_n or limit)

    sql = f"""
WITH per_customer AS (
    SELECT
        {_quote(customer_col)} AS customer_key,
        SUM({_quote(metric_col)}) AS lifetime_value
    FROM {_quote(table.schema_name)}.{_quote(table.name)}
    GROUP BY {_quote(customer_col)}
)
SELECT
    AVG(lifetime_value) AS avg_customer_lifetime_value
FROM per_customer
LIMIT 1
""".strip()
    return QueryPlan(
        sql=sql,
        intent=intent,
        assumptions=["clv_template", "aggregates customer totals by customer"],
        required_filters={"table": table.fqn, "customer_col": customer_col},
        limit=top_n,
    )


def _template_anomalies(intent: Intent, context: PlatformContext, limit: int) -> QueryPlan:
    table = _resolve_fact_table(context)
    time_col = _pick_column(
        table,
        ["transaction_date", "order_date", "created_at", "event_ts", "date"],
        mandatory=True,
    )
    metric_col = _pick_column(
        table,
        ["total", "revenue", "amount", "sales", "quantity", "lifetime_value"],
        mandatory=True,
    )

    top_n = max(1, intent.top_n or limit)
    sql = f"""
WITH daily AS (
    SELECT DATE_TRUNC('day', {_quote(time_col)}) AS day_bucket,
           SUM({_quote(metric_col)}) AS metric_value
    FROM {_quote(table.schema_name)}.{_quote(table.name)}
    GROUP BY 1
),
stats AS (
    SELECT
        day_bucket,
        metric_value,
        AVG(metric_value) OVER () AS avg_metric,
        STDDEV_POP(metric_value) OVER () AS std_metric
    FROM daily
)
SELECT
    day_bucket,
    metric_value,
    avg_metric,
    std_metric,
    ABS(metric_value - avg_metric) AS deviation
FROM stats
WHERE std_metric IS NOT NULL
  AND ABS(metric_value - avg_metric) > 2 * std_metric
ORDER BY deviation DESC
LIMIT {top_n}
""".strip()
    return QueryPlan(
        sql=sql,
        intent=intent,
        assumptions=["anomaly_template", "zscore_window=global"],
        required_filters={"table": table.fqn},
        limit=top_n,
    )


def _template_top_n(intent: Intent, context: PlatformContext, limit: int) -> QueryPlan:
    table = _resolve_fact_table(context)
    requested = intent.requested_metric or "revenue"

    domain = intent.extracted_filters.get("domain")
    if domain == "products":
        entity_col = _pick_column(table, ["product_id", "product_name", "sku", "item_id"])
    elif domain == "customers":
        entity_col = _pick_column(table, ["user_id", "customer_id", "account_id"])
    else:
        entity_col = _pick_column(
            table,
            ["product_id", "user_id", "customer_id", "order_id"],
            mandatory=True,
        )

    metric_col = _pick_column(
        table,
        ["total", "revenue", "amount", "sales", "quantity", "lifetime_value", requested],
        mandatory=False,
    )
    top_n = max(1, intent.top_n or limit)

    sql = f"""
SELECT
    {_quote(entity_col)} AS entity,
    SUM({_quote(metric_col)}) AS metric_total
FROM {_quote(table.schema_name)}.{_quote(table.name)}
WHERE {_quote(entity_col)} IS NOT NULL
GROUP BY 1
ORDER BY metric_total DESC
LIMIT {top_n}
""".strip()
    return QueryPlan(
        sql=sql,
        intent=intent,
        assumptions=[f"top_n_template for metric={requested}"],
        required_filters={"table": table.fqn, "entity_col": entity_col, "metric_col": metric_col},
        limit=top_n,
    )


def _template_generic(intent: Intent, context: PlatformContext, limit: int) -> QueryPlan:
    if not context.tables:
        raise TemplateRenderError("Generic fallback cannot run: no discovered tables available.")
    table = next(iter(context.tables.values()))
    sql = f'SELECT * FROM {_quote(table.schema_name)}.{_quote(table.name)} LIMIT {limit}'
    return QueryPlan(
        sql=sql,
        intent=intent,
        assumptions=["generic_fallback_template"],
        required_filters={"table": table.fqn},
        limit=limit,
    )


TemplateRenderer = Callable[[Intent, PlatformContext, int], QueryPlan]

TEMPLATES: dict[str, tuple[str, TemplateRenderer]] = {
    "sales_trend": ("sales trend metrics over time", _template_sales_trend),
    "copurchase": ("co-purchase pair analysis", _template_copurchase),
    "anomalies": ("anomaly detection template", _template_anomalies),
    "clv": ("customer lifetime value", _template_clv),
    "top_n": ("top N ranking template", _template_top_n),
    "generic": ("deterministic fallback", _template_generic),
}


def template_for_intent(intent: Intent, context: PlatformContext) -> str:
    """Return selected template key for intent."""

    return _select_template(intent, context)


def render_query_plan(
    intent: Intent,
    context: PlatformContext,
    limit: int | None = None,
) -> QueryPlan:
    """Return a QueryPlan for the input intent using metadata-backed templates."""

    normalized_limit = _DEFAULT_LIMIT if limit is None else limit
    if normalized_limit <= 0:
        raise ValueError("limit must be positive")

    template_key = template_for_intent(intent, context)
    template_name, renderer = TEMPLATES.get(template_key, TEMPLATES["generic"])
    _ = template_name

    plan = renderer(intent, context, normalized_limit)
    if template_key == "generic":
        if intent.intent == "generic":
            reason = "generic_intent_requested"
        elif intent.confidence < _CONFIDENCE_FALLBACK_THRESHOLD:
            reason = "low_confidence_fallback"
        else:
            reason = "unsupported_intent_fallback"
        plan = plan.model_copy(update={"fallback_reason": reason})

    return plan
