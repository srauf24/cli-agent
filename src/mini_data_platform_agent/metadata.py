"""Metadata discovery for the DuckDB-backed mini data platform."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb

from .config import AppConfig
from .types import ColumnMeta, PlatformContext, TableMeta

_IGNORED_SCHEMAS = {"information_schema", "pg_catalog"}


_FACT_PREFIXES = ("fct_", "fact_")
_DIM_PREFIXES = ("dim_", "dimens")

_DBT_MODEL_LAYER_PRIORITY = ("marts", "staging", "other")
_DBT_MODEL_EXT = "*.sql"

_FACT_METRIC_MARKERS = (
    "amount",
    "total",
    "revenue",
    "price",
    "subtotal",
    "gross",
    "net",
    "qty",
    "quantity",
    "cost",
)

_DIM_TEXT_MARKERS = (
    "name",
    "description",
    "category",
    "country",
    "region",
    "segment",
    "email",
    "status",
)


def _quote_identifier(value: str) -> str:
    """Return a SQL-safe identifier quote."""

    return value.replace('"', '""')


def _classify_table_name(name: str) -> str | None:
    lowered = name.lower()
    if lowered.startswith(_FACT_PREFIXES):
        return "fact"
    if lowered.startswith(_DIM_PREFIXES):
        return "dim"
    return None


def _has_prefix(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(lowered.startswith(marker) for marker in markers)


def _classify_by_signature(table_name: str, columns: list[str]) -> str | None:
    lowered = table_name.lower()
    lowered_columns = [col.lower() for col in columns]

    is_fact_signal = any(
        _has_prefix(col, _FACT_METRIC_MARKERS) or marker in col
        for col in lowered_columns
        for marker in _FACT_METRIC_MARKERS
    ) and any("id" in col for col in lowered_columns)

    has_descriptive_signal = any(
        any(marker in col for marker in _DIM_TEXT_MARKERS) for col in lowered_columns
    )
    has_id_key = any(col.endswith("_id") for col in lowered_columns)

    if has_descriptive_signal and has_id_key:
        return "dim"
    if is_fact_signal:
        return "fact"
    if lowered in {"fct", "fact"} and has_id_key:
        return "fact"
    return None


def _ordered_uniq(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _read_dbt_models(dbt_path: Path) -> list[str]:
    """Scan dbt SQL files and return ordered model names by layer priority.

    The scan is resilient to missing paths and ignores files prefixed with "_".
    """

    models_root = dbt_path / "models"
    if not models_root.exists():
        return []

    by_layer: dict[str, list[str]] = {layer: [] for layer in _DBT_MODEL_LAYER_PRIORITY}

    for model_file in models_root.rglob(_DBT_MODEL_EXT):
        if model_file.name.startswith("_"):
            continue

        relative_parts = model_file.relative_to(models_root).parts
        layer = relative_parts[0] if len(relative_parts) > 1 else "other"
        if layer not in by_layer:
            layer = "other"
        by_layer[layer].append(model_file.stem)

    ordered: list[str] = []
    for layer in _DBT_MODEL_LAYER_PRIORITY:
        ordered.extend(sorted(by_layer[layer]))

    return _ordered_uniq(ordered)


def discover_platform_context(config: AppConfig) -> PlatformContext:
    """Discover platform metadata from DuckDB and local dbt model files."""

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
        tables: dict[str, TableMeta] = {}
        schemas: list[str] = []
        fact_tables: list[str] = []
        dim_tables: list[str] = []

        for schema_name, table_name, table_type in discovered_tables:
            if schema_name in _IGNORED_SCHEMAS:
                continue
            if schema_name not in schemas:
                schemas.append(schema_name)

            is_view = table_type.upper() == "VIEW"
            metadata_columns: list[ColumnMeta] = []
            normalized_columns = []
            for column_name, data_type, is_nullable in con.execute(
                columns_query, [schema_name, table_name]
            ).fetchall():
                normalized_columns.append(column_name)
                metadata_columns.append(
                    ColumnMeta(
                        name=column_name,
                        dtype=str(data_type),
                        is_nullable=bool(is_nullable == "YES"),
                    )
                )

            row_count = None
            try:
                quoted = f'"{_quote_identifier(schema_name)}"."{_quote_identifier(table_name)}"'
                row_count = con.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            except Exception:
                row_count = None

            metadata = TableMeta(
                schema=schema_name,
                name=table_name,
                columns=metadata_columns,
                row_count=row_count,
                is_view=is_view,
            )
            tables[metadata.fqn] = metadata

            classification = _classify_table_name(table_name)
            if classification is None:
                classification = _classify_by_signature(table_name, normalized_columns)

            if classification == "fact":
                fact_tables.append(table_name)
            elif classification == "dim":
                dim_tables.append(table_name)

    recommended_models = _ordered_uniq(
        [
            *fact_tables,
            *dim_tables,
            *_read_dbt_models(config.dbt_path),
        ]
    )

    return PlatformContext(
        schemas=schemas,
        tables=tables,
        candidate_fact_tables=fact_tables,
        candidate_dim_tables=dim_tables,
        recommended_models=recommended_models,
        discovered_at=datetime.now(UTC),
    )

