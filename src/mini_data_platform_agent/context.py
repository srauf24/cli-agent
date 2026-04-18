"""Platform metadata discovery for the DuckDB-backed mini data platform."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from .config import AppConfig
from .types import ColumnMeta, PlatformContext, TableMeta


_IGNORED_SCHEMAS = {"information_schema", "pg_catalog"}


def _quote_identifier(value: str) -> str:
    """Safely quote SQL identifiers for metadata-driven SQL generation."""

    return value.replace('"', '""')


def _is_fact_table(name: str) -> bool:
    return name.startswith("fct_")


def _is_dim_table(name: str) -> bool:
    return name.startswith("dim_")


def _read_dbt_models(dbt_path: Path) -> list[str]:
    """Read dbt model names from SQL files as optional hints."""

    models_path = dbt_path / "models"
    if not models_path.exists():
        return []

    models: list[str] = []
    for model_file in sorted(models_path.rglob("*.sql")):
        if model_file.name.startswith("_"):
            continue
        models.append(model_file.stem)
    return models


def discover_platform_context(config: AppConfig) -> PlatformContext:
    """Discover schemas, tables, and supporting metadata from DuckDB.

    This method infers:
    - available schemas and tables
    - column-level metadata
    - row counts (best-effort)
    - candidate fact/dimension tables by naming convention
    - model hints from DBT model SQL files (best effort)
    """

    if not Path(config.db_path).exists():
        raise FileNotFoundError(f"DuckDB file not found: {config.db_path}")

    tables_query = """
    SELECT table_schema, table_name, table_type
    FROM information_schema.tables
    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
    ORDER BY table_schema, table_name
    """

    columns_query = """
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = ? AND table_name = ?
    ORDER BY ordinal_position
    """

    with duckdb.connect(str(config.db_path), read_only=True) as con:
        discovered_tables = con.execute(tables_query).fetchall()
        table_records: dict[str, TableMeta] = {}
        schemas: list[str] = []
        fact_tables: list[str] = []
        dim_tables: list[str] = []

        for schema_name, table_name, table_type in discovered_tables:
            if schema_name in _IGNORED_SCHEMAS:
                continue

            if schema_name not in schemas:
                schemas.append(schema_name)

            is_view = table_type.upper() == "VIEW"
            table_columns: list[ColumnMeta] = []
            for column_name, data_type, is_nullable in con.execute(
                columns_query, [schema_name, table_name]
            ).fetchall():
                table_columns.append(
                    ColumnMeta(
                        name=column_name,
                        dtype=str(data_type),
                        is_nullable=bool(is_nullable == "YES"),
                    )
                )

            row_count: int | None
            try:
                quoted = f'"{_quote_identifier(schema_name)}"."{_quote_identifier(table_name)}"'
                row_count = con.execute(f"SELECT COUNT(*) AS cnt FROM {quoted}").fetchone()[0]
            except Exception:
                row_count = None

            table = TableMeta(
                schema=schema_name,
                name=table_name,
                columns=table_columns,
                row_count=row_count,
                is_view=is_view,
            )
            table_records[table.fqn] = table

            if _is_fact_table(table_name):
                fact_tables.append(table_name)
            if _is_dim_table(table_name):
                dim_tables.append(table_name)

    dbt_models = _read_dbt_models(config.dbt_path)
    recommended_models = list(dict.fromkeys([*fact_tables, *dim_tables, *dbt_models]))

    return PlatformContext(
        schemas=schemas,
        tables=table_records,
        candidate_fact_tables=fact_tables,
        candidate_dim_tables=dim_tables,
        recommended_models=recommended_models,
        discovered_at=datetime.now(UTC),
    )
