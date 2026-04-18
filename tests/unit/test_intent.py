"""Tests for deterministic intent classification."""

from __future__ import annotations

import pytest

from mini_data_platform_agent.intent import classify_intent


def test_sales_trend_last_quarter() -> None:
    q = "How much in sales did we do last quarter?"
    intent = classify_intent(q)

    assert intent.intent == "sales_trend"
    assert intent.confidence >= 0.8
    assert intent.timeframe == "last_quarter"
    assert intent.requested_metric in {"sales", "revenue"}


def test_copurchase_question() -> None:
    q = "Which two products are most frequently bought together?"
    intent = classify_intent(q)

    assert intent.intent == "copurchase"
    assert intent.confidence >= 0.9
    assert intent.extracted_filters.get("domain") == "products"


def test_anomalies_question() -> None:
    q = "Are there any anomalies with how we sell products?"
    intent = classify_intent(q)

    assert intent.intent == "anomalies"
    assert intent.confidence >= 0.9
    assert intent.extracted_filters.get("anomaly_detection") is True


def test_clv_question() -> None:
    q = "What's our average customer lifetime value?"
    intent = classify_intent(q)

    assert intent.intent == "clv"
    assert intent.confidence >= 0.9
    assert intent.requested_metric == "clv"


def test_top_n_question() -> None:
    q = "Show me the top 2 products by revenue"
    intent = classify_intent(q)

    assert intent.intent == "top_n"
    assert intent.top_n == 2
    assert intent.requested_metric == "revenue"
    assert intent.confidence >= 0.9


def test_ambiguous_returns_generic_low_confidence() -> None:
    q = "show me the trend and top products and anomalies"
    intent = classify_intent(q)

    assert intent.intent == "generic"
    assert intent.confidence < 0.7


def test_empty_question_defaults() -> None:
    intent = classify_intent("")

    assert intent.intent == "generic"
    assert intent.timeframe is None
    assert intent.requested_metric is None
    assert intent.confidence <= 0.3


def test_top_n_extracted_and_fallback_timeframe_default() -> None:
    q = "show top customers"
    intent = classify_intent(q)

    assert intent.intent == "generic"
    assert intent.top_n is None
    assert intent.timeframe is None
    assert intent.confidence < 0.7
