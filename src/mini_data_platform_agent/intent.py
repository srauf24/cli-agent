"""Deterministic intent classification for ad-hoc analytics questions."""

from __future__ import annotations

import re

from .types import Intent


_INTENT_COEFFICIENT = {
    "copurchase": [
        (r"\b(buy|bought|purchas)\s*(together|with|in\s+combination)\b", 0.99),
        (r"\b(co-?purchase|co.?purchase|co[- ]?purchase|also[- ]?bought|frequently\s+bought\b)", 0.98),
        (r"\bpair\b", 0.84),
    ],
    "clv": [
        (r"\blifetime\s+value\b", 0.99),
        (r"\bclv\b", 0.98),
        (r"\blifetime\b|\bcustomer\s+lifetime\b", 0.82),
    ],
    "anomalies": [
        (r"\banomal\w*\b", 0.99),
        (r"\bunusual|\boutlier|\bspike\b|\bunhealthy", 0.92),
        (r"\brare|\bweird", 0.85),
    ],
    "top_n": [
        (r"\btop\s+(\d+)\b", 0.98),
        (r"\bmost\s+(\d+)\b", 0.92),
        (r"\bhighest\b|\bbest\b|\blowest\b", 0.88),
    ],
    "sales_trend": [
        (r"\bsales\b.*\b(trend|trend\s+by|by\s+month|by\s+quarter|over\s+time)", 0.98),
        (r"\brevenue\b.*\b(trend|month|quarter|over\s+time)", 0.95),
        (r"\b(last|previous|this|current)\s+quarter\b", 0.9),
        (r"\bquarter\b", 0.8),
        (r"\bby\s+quarter\b|\bmonthly\b|\bover\s+time\b", 0.8),
    ],
}

_TIMEFRAME_PATTERNS = [
    (r"\blast\s+quarter\b", "last_quarter"),
    (r"\bthis\s+quarter\b", "this_quarter"),
    (r"\blast\s+month\b", "last_month"),
    (r"\bthis\s+month\b", "this_month"),
    (r"\blast\s+year\b", "last_year"),
    (r"\bytd\b|\byear\s+to\s+date\b", "ytd"),
    (r"\bq1\b|\bq2\b|\bq3\b|\bq4\b", "quarter"),
]


_TOP_N_RE = re.compile(r"\b(?:top|most|least)\s+(\d+)\b", re.IGNORECASE)


def _match_top_n(text: str) -> int | None:
    match = _TOP_N_RE.search(text)
    if not match:
        return None

    try:
        value = int(match.group(1))
    except ValueError:
        return None

    return value if value > 0 else None


def _match_timeframe(text: str) -> str | None:
    for pattern, label in _TIMEFRAME_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return label
    return None


def _extract_metric(text: str) -> str | None:
    metric_patterns = [
        (r"\brevenue\b", "revenue"),
        (r"\bsales\b", "sales"),
        (r"\border\s+count\b|\borders\b", "orders"),
        (r"\borders\b", "orders"),
        (r"\bcustomer\b|\bclv\b|\blifetime\b", "clv"),
        (r"\bproducts\b", "products"),
    ]
    for pattern, metric in metric_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return metric
    return None


def _extract_filters(text: str) -> dict[str, str | int | float | bool | None]:
    filters: dict[str, str | int | float | bool | None] = {}

    if re.search(r"\bproducts?\b", text, flags=re.IGNORECASE):
        filters["domain"] = "products"
    if re.search(r"\bcustomer\b", text, flags=re.IGNORECASE):
        filters["domain"] = filters.get("domain", "customers")
    if re.search(r"\banom|outlier|spike|unusual", text, flags=re.IGNORECASE):
        filters["anomaly_detection"] = True

    return filters


def _intent_score(text: str, intent: str) -> tuple[float, dict[str, str | int | float | bool | None]]:
    score = 0.0
    hits: dict[str, str | int | float | bool | None] = {}

    for pattern, weight in _INTENT_COEFFICIENT.get(intent, []):
        if re.search(pattern, text, flags=re.IGNORECASE):
            score = max(score, weight)
            if intent == "top_n":
                top_n = _match_top_n(text)
                if top_n:
                    hits["top_n_detected"] = top_n
            elif intent == "anomalies" and "anomaly_detection" not in hits:
                hits["anomaly_detection"] = True

    if score == 0.0:
        return 0.0, hits

    timeframe = _match_timeframe(text)
    if timeframe:
        hits["timeframe"] = timeframe

    metric = _extract_metric(text)
    if metric:
        hits["requested_metric"] = metric

    return score, hits


def classify_intent(question: str) -> Intent:
    """Classify intent using deterministic pattern matching.

    Returns Intent with a confidence score and extracted hint fields.
    """

    text = (question or "").strip().lower()
    if not text:
        return Intent(intent="generic", confidence=0.10, extracted_filters={"empty": True})

    candidates: list[tuple[str, float, dict[str, str | int | float | bool | None]]] = []
    for intent_name in ["copurchase", "clv", "anomalies", "top_n", "sales_trend"]:
        score, hits = _intent_score(text, intent_name)
        if score > 0:
            candidates.append((intent_name, score, hits))

    if candidates:
        # Tie-breakers: choose strongest confidence first, then deterministic intent priority.
        ordered = sorted(
            candidates,
            key=lambda item: (item[1],
                              {"copurchase": 5, "clv": 4, "anomalies": 3, "top_n": 2, "sales_trend": 1}[item[0]],
                              0),
            reverse=True,
        )

        # Avoid overfitting mixed prompts to a single intent when multiple intents are hinted.
        candidate_names = {name for name, _score, _hits in candidates}
        has_anomalies = any(name == "anomalies" for name in candidate_names)
        has_sales_trend = any(name == "sales_trend" for name in candidate_names)
        has_top_n = any(name == "top_n" for name in candidate_names)
        has_copurchase = any(name == "copurchase" for name in candidate_names)
        has_trend_hint = bool(re.search(r"\btrend\b", text, flags=re.IGNORECASE))
        has_top_hint = bool(re.search(r"\btop\b|\bmost\b|\bleast\b", text, flags=re.IGNORECASE))
        has_top_product_hint = has_top_hint and bool(re.search(r"\bproduct", text, flags=re.IGNORECASE))
        if has_anomalies and (has_sales_trend or has_top_n or has_copurchase or has_trend_hint or has_top_product_hint):
            return Intent(
                intent="generic",
                confidence=0.38,
                extracted_filters=_extract_filters(text),
                requested_metric=_extract_metric(text),
                timeframe=_match_timeframe(text),
            )

        intent_name, score, hits = ordered[0]

        top_n = hits.pop("top_n_detected", None)
        timeframe = hits.pop("timeframe", None)
        requested_metric = hits.pop("requested_metric", None)

        extracted_filters = _extract_filters(text)
        extracted_filters.update(hits)

        confidence = float(min(0.99, score))

        ambiguous = score < 0.75
        if ambiguous:
            # conservative lowering for mixed phrasing
            confidence = 0.62

        return Intent(
            intent=intent_name,
            confidence=confidence,
            extracted_filters=extracted_filters,
            requested_metric=requested_metric,
            timeframe=timeframe,
            top_n=top_n,
        )

    # Generic fallback with sane defaults
    extracted_filters = _extract_filters(text)
    return Intent(
        intent="generic",
        confidence=0.42,
        extracted_filters=extracted_filters,
        requested_metric=_extract_metric(text),
        timeframe=_match_timeframe(text),
    )
