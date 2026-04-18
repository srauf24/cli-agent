"""Evidence markdown query pattern extraction utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_FENCE_PATTERN = re.compile(
    r"(?is)^\s*```sql(?:\s+([^\n`]+))?\n(.*?)\n\s*```",
    re.MULTILINE,
)


_AS_ALIAS_PATTERN = re.compile(
    r'\bas\s+"?\'?([A-Za-z_][A-Za-z0-9_ ]*)"?\'?\s*$',
    re.IGNORECASE,
)
_TRAILING_IDENTIFIER = re.compile(r"([A-Za-z_][A-Za-z0-9_\.]*)\s*$")
_FIELD_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_]+")


@dataclass(frozen=True)
class EvidencePattern:
    """A SQL snippet discovered from Evidence markdown."""

    source_file: str
    query_name: str
    sql: str
    fields: list[str]


def _normalize_field_name(value: str) -> str:
    value = value.strip().strip('"\'`[]')
    value = value.lower().replace(" ", "_")
    value = _FIELD_NAME_PATTERN.sub("_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in values:
        normalized = _normalize_field_name(item)
        if not normalized:
            continue
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    return re.sub(r"--.*?$", "", sql, flags=re.M)


def _extract_comma_parts(select_clause: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_single = False
    in_double = False

    for char in select_clause:
        if char == "'" and not in_double:
            in_single = not in_single if (len(current) == 0 or current[-1] != "\\") else in_single
        elif char == '"' and not in_single:
            in_double = not in_double if (len(current) == 0 or current[-1] != "\\") else in_double
        elif char == "(" and not in_single and not in_double:
            depth += 1
        elif char == ")" and not in_single and not in_double and depth > 0:
            depth -= 1
        elif char == "," and not in_single and not in_double and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(char)

    trailing = "".join(current).strip()
    if trailing:
        parts.append(trailing)
    return parts


def _field_from_expression(expression: str) -> str | None:
    expr = expression.strip().rstrip(",")
    if not expr or expr == "*":
        return None

    as_match = _AS_ALIAS_PATTERN.search(expr)
    if as_match:
        return _normalize_field_name(as_match.group(1))

    if "." in expr:
        # bare schema.table / table.column reference without alias
        if expr.count(" ") == 0 and "(" not in expr and ")" not in expr:
            return _normalize_field_name(expr.split(".")[-1])

    trailing_match = _TRAILING_IDENTIFIER.search(expr)
    if not trailing_match:
        return None
    trailing = trailing_match.group(1)
    if "." in trailing:
        trailing = trailing.split(".")[-1]
    if trailing.lower() in {"from", "select", "where", "group", "order", "limit", "join"}:
        return None
    return _normalize_field_name(trailing)


def extract_selected_fields(sql: str) -> list[str]:
    """Best-effort select-field extraction for SQL snippets."""

    cleaned = _strip_sql_comments(sql)
    select_matches = list(re.finditer(r"(?i)\bselect\b", cleaned))
    if not select_matches:
        return []

    start = select_matches[-1].end()
    tail = cleaned[start:]
    from_match = re.search(r"(?i)\bfrom\b", tail)
    if from_match:
        select_body = tail[: from_match.start()]
    else:
        select_body = tail

    fields = []
    for raw in _extract_comma_parts(select_body):
        field = _field_from_expression(raw)
        if field:
            fields.append(field)

    return _dedupe(fields)


def extract_patterns_from_text(markdown_text: str) -> list[tuple[str, str]]:
    """Return (query_name, sql) for SQL code blocks."""

    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(_FENCE_PATTERN.finditer(markdown_text), start=1):
        name = (match.group(1) or "").strip() or f"query_{index}"
        sql = (match.group(2) or "").strip()
        if sql:
            blocks.append((name, sql))
    return blocks


def discover_patterns(evidence_root: Path | str) -> list[EvidencePattern]:
    """Harvest SQL patterns from markdown files under evidence_root.

    Returns empty list for missing/partial directories without raising.
    """

    root = Path(evidence_root)
    if not root.exists():
        return []

    page_files = sorted(root.glob("*.md"))
    patterns: list[EvidencePattern] = []
    for page in page_files:
        try:
            text = page.read_text()
        except OSError:
            continue
        for name, sql in extract_patterns_from_text(text):
            if not sql:
                continue
            patterns.append(
                EvidencePattern(
                    source_file=page.name,
                    query_name=name,
                    sql=sql,
                    fields=extract_selected_fields(sql),
                )
            )
    return patterns
