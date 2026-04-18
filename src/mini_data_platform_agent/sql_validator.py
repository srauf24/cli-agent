"""Read-only SQL validation and safety guardrails."""

from __future__ import annotations

import re

from .types import PlatformContext, TableMeta

_FORBIDDEN_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "truncate",
    "attach",
    "detach",
)

_LIMIT_RE = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)
_FROM_JOIN_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:"
    r'(?:"(?P<qs>[^\"]+)"\.)?"(?P<qt>[^\"]+)"'
    r"|(?:(?P<schema>\w+)\.)?(?P<table>\w+)"
    r")\s*(?:AS\s+)?(?P<alias>\"?[A-Za-z_][A-Za-z0-9_]*\"?)?",
    re.IGNORECASE,
)
_COLUMN_LIST_RE = re.compile(r"\bSELECT\s+(.*?)\s+FROM\b", re.IGNORECASE | re.DOTALL)
_QUALIFIED_COL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
_UNQUOTED_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_START_TOKEN_RE = re.compile(r"^\s*(\w+)")
_CTE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(", re.IGNORECASE)


class SQLValidationError(ValueError):
    """Raised when SQL is unsafe or outside discovered context."""

    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"SQL validation failed: {reason}")

    def __str__(self) -> str:
        return f"SQL validation failed: {self.reason}"


def _normalise_identifier(value: str) -> str:
    return value.replace('"', "").strip().lower()


def _strip_comments(sql: str) -> str:
    return re.sub(r"--.*?$|/\*.*?\*/", "", sql, flags=re.MULTILINE | re.DOTALL)


def _extract_cte_names(statement: str) -> set[str]:
    lowered = statement.lstrip().lower()
    if not lowered.startswith("with"):
        return set()

    cte_section_end = lowered.find(" select ")
    if cte_section_end == -1:
        return set()
    cte_section = statement[:cte_section_end]
    return {_normalise_identifier(match.group(1)) for match in _CTE_RE.finditer(cte_section)}


def _split_statements(sql: str) -> list[str]:
    parts = [part.strip() for part in sql.split(";")]
    return [part for part in parts if part]


def _validate_forbidden_keywords(statement: str) -> None:
    lowered = statement.lower()
    for token in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{token}\b", lowered):
            raise SQLValidationError(f"Forbidden keyword detected: {token}")

    match = _START_TOKEN_RE.match(lowered)
    if match is None:
        raise SQLValidationError("Empty SQL statement.")
    if match.group(1) not in {"select", "with"}:
        raise SQLValidationError("Only SELECT and WITH statements are allowed.")


def _build_table_lookup(context: PlatformContext) -> tuple[set[str], dict[str, list[str]], dict[str, TableMeta]]:
    by_fqn = {table.fqn.lower(): table for table in context.tables.values()}
    by_name: dict[str, list[str]] = {}
    for table in context.tables.values():
        by_name.setdefault(table.name.lower(), []).append(table.fqn.lower())
    return set(by_fqn.keys()), by_name, by_fqn


def _schema_names(context: PlatformContext) -> set[str]:
    return {table.schema_name.lower() for table in context.tables.values()}


def _extract_table_aliases(
    statement: str,
    context: PlatformContext,
    cte_names: set[str],
) -> tuple[dict[str, str], set[str]]:
    by_fqn, by_name, _ = _build_table_lookup(context)
    aliases: dict[str, str] = {}
    seen_aliases: set[str] = set()

    for match in _FROM_JOIN_RE.finditer(statement):
        quoted_schema = _normalise_identifier(match.group("qs") or "")
        quoted_table = _normalise_identifier(match.group("qt") or "")
        schema = _normalise_identifier(match.group("schema") or "")
        table = _normalise_identifier(match.group("table") or "")
        alias = _normalise_identifier(match.group("alias") or "")

        if quoted_table:
            table_name = quoted_table
            schema_name = quoted_schema or None
        else:
            table_name = table
            schema_name = schema or None

        fqns = {f"{schema_name}.{table_name}" if schema_name else table_name}
        fqn_from_context = None
        for fqn in fqns:
            if fqn in by_fqn:
                fqn_from_context = fqn
                break

        if fqn_from_context is None and schema_name is None:
            candidates = by_name.get(table_name, [])
            if not candidates:
                if table_name in cte_names:
                    continue
                raise SQLValidationError(f"Disallowed table reference: {table_name}")
            if len(candidates) > 1:
                raise SQLValidationError(f"Ambiguous table reference: {table_name}")
            fqn_from_context = candidates[0]
        elif fqn_from_context is None and schema_name is not None:
            raise SQLValidationError(f"Disallowed table reference: {schema_name}.{table_name}")

        default_ref = alias or table_name
        aliases[default_ref] = fqn_from_context
        seen_aliases.add(default_ref)

    return aliases, seen_aliases


def _validate_table_references(statement: str, context: PlatformContext) -> set[str]:
    by_fqn, by_name, _ = _build_table_lookup(context)
    referenced: set[str] = set()
    for match in _FROM_JOIN_RE.finditer(statement):
        quoted_schema = _normalise_identifier(match.group("qs") or "")
        quoted_table = _normalise_identifier(match.group("qt") or "")
        schema = _normalise_identifier(match.group("schema") or "")
        table = _normalise_identifier(match.group("table") or "")

        if quoted_table:
            table_name = quoted_table
            schema_name = quoted_schema
        else:
            table_name = table
            schema_name = schema

        if not table_name:
            continue

        if schema_name:
            candidate = f"{schema_name}.{table_name}"
            if candidate not in by_fqn:
                if table_name in _extract_cte_names(statement):
                    continue
                raise SQLValidationError(f"Disallowed table reference: {candidate}")
            referenced.add(candidate)
            continue

        if table_name not in by_name:
            if table_name in _extract_cte_names(statement):
                continue
            raise SQLValidationError(f"Disallowed table reference: {table_name}")
        candidates = by_name[table_name]
        if len(candidates) > 1:
            raise SQLValidationError(f"Ambiguous table reference: {table_name}")
        referenced.add(candidates[0])
    return referenced


def _validate_column_references(
    statement: str,
    context: PlatformContext,
    cte_names: set[str],
) -> None:
    table_aliases, _ = _extract_table_aliases(statement, context, cte_names)
    fqn_to_table = {table.fqn.lower(): table for table in context.tables.values()}

    # Validate qualified column references across full statement.
    for alias, column in _QUALIFIED_COL_RE.findall(statement):
        table_ref = table_aliases.get(alias.lower())
        if table_ref is None:
            if alias.lower() in cte_names:
                continue
            if alias.lower() in _schema_names(context):
                continue
            # Allow schema-qualified patterns like t.col where t is not an alias yet.
            table_ref = alias.lower()
            if table_ref in fqn_to_table:
                table = fqn_to_table[table_ref]
            else:
                raise SQLValidationError(f"Unknown table/alias: {alias}")
        else:
            table = fqn_to_table.get(table_ref)
            if table is None:
                raise SQLValidationError(f"Unknown table in context: {table_ref}")

        if column.lower() not in {col.name.lower() for col in table.columns}:
            raise SQLValidationError(f"Unknown column '{column}' on table {table_ref}")

    # Validate select list for unqualified columns.
    select_match = _COLUMN_LIST_RE.search(statement)
    if not select_match:
        return

    select_body = select_match.group(1)
    for item in select_body.split(","):
        expression = item.strip()
        if not expression or expression == "*" or expression.startswith("* "):
            continue

        if _QUALIFIED_COL_RE.search(expression):
            continue
        if "(" in expression:
            continue

        token_match = expression.split()[0]
        if token_match.startswith("'") or token_match.isdigit():
            continue

        if token_match.upper() == "DISTINCT":
            token_match = (expression.split(maxsplit=1)[1] if len(expression.split()) > 1 else "")
        if not token_match:
            continue

        if not _UNQUOTED_ID_RE.match(token_match):
            continue
        candidate = token_match.lower()
        if candidate in {"*", "null"}:
            continue

        owners = []
        for table in context.tables.values():
            if candidate in {col.name.lower() for col in table.columns}:
                owners.append(table.fqn.lower())
        if not owners:
            raise SQLValidationError(f"Unknown unqualified column: {candidate}")
        if len(owners) > 1:
            raise SQLValidationError(f"Ambiguous unqualified column: {candidate}")


def validate_select_query(
    sql: str,
    context: PlatformContext,
    *,
    default_limit: int,
    max_limit: int,
) -> str:
    """Validate SQL and normalize limit clauses."""

    if default_limit <= 0 or max_limit <= 0:
        raise SQLValidationError("Limits must be positive.")
    if max_limit < default_limit:
        raise SQLValidationError("max_limit must be >= default_limit.")

    statement_list = _split_statements(_strip_comments(sql or ""))
    if not statement_list:
        raise SQLValidationError("No executable SQL statement found.")
    if len(statement_list) > 1:
        raise SQLValidationError("Only one SQL statement is allowed.")

    statement = statement_list[0].strip()
    _validate_forbidden_keywords(statement)
    cte_names = _extract_cte_names(statement)
    _validate_table_references(statement, context)
    _validate_column_references(statement, context, cte_names)

    match = _LIMIT_RE.search(statement)
    if match is None:
        statement = f"{statement} LIMIT {default_limit}"
    else:
        limit = int(match.group(1))
        if limit <= 0:
            raise SQLValidationError("LIMIT must be positive.")
        if limit > max_limit:
            statement = _LIMIT_RE.sub(f"LIMIT {max_limit}", statement, count=1)
    return statement
