"""Pytest configuration and shared fixture utilities."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import duckdb
import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from mini_data_platform_agent.config import AppConfig

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
_FIXTURE_SQL_PATH = _FIXTURE_DIR / "miniplatform_fixture.sql"
_REPO_WAREHOUSE_PATH = Path(__file__).resolve().parents[1] / "warehouse" / "data.duckdb"


def _iter_sql_statements(sql: str) -> list[str]:
    """Split SQL into executable statements."""

    return [
        statement.strip()
        for statement in sql.split(";")
        if statement.strip() and not statement.strip().startswith("--")
    ]


def _apply_sql_file(conn: duckdb.DuckDBPyConnection, path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"fixture SQL file not found: {path}")

    for statement in _iter_sql_statements(path.read_text(encoding="utf-8")):
        conn.execute(statement)


def provision_miniplatform_warehouse(db_path: Path) -> None:
    """Provision a deterministic mini warehouse at `db_path`."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    with duckdb.connect(str(db_path)) as con:
        _apply_sql_file(con, _FIXTURE_SQL_PATH)


def provision_miniplatform_dbt_project(dbt_path: Path) -> None:
    """Create a deterministic dbt fixture project layout."""

    models_root = dbt_path / "models"
    marts_dir = models_root / "marts"
    staging_dir = models_root / "staging"

    marts_dir.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    (marts_dir / "fct_orders.sql").write_text(
        "SELECT * FROM marts.fct_orders",
        encoding="utf-8",
    )
    (marts_dir / "dim_products.sql").write_text(
        "SELECT * FROM marts.dim_products",
        encoding="utf-8",
    )
    (marts_dir / "dim_customers.sql").write_text(
        "SELECT * FROM marts.dim_customers",
        encoding="utf-8",
    )
    (staging_dir / "stg_transactions.sql").write_text(
        "SELECT * FROM raw.transactions",
        encoding="utf-8",
    )
    (staging_dir / "stg_orders.sql").write_text(
        "SELECT * FROM main.orders",
        encoding="utf-8",
    )


def snapshot_repository_warehouse() -> tuple[int, str]:
    """Return size and hash fingerprint for the repository warehouse."""

    if not _REPO_WAREHOUSE_PATH.exists():
        raise FileNotFoundError(f"Repository warehouse not found: {_REPO_WAREHOUSE_PATH}")

    data = _REPO_WAREHOUSE_PATH.read_bytes()
    return _REPO_WAREHOUSE_PATH.stat().st_size, _checksum(data)


def warehouse_signature(db_path: Path) -> dict[str, list[str]]:
    """Return a deterministic schema/table/column fingerprint."""

    with duckdb.connect(str(db_path), read_only=True) as con:
        tables = con.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
            """
        ).fetchall()

        signature: dict[str, list[str]] = {}
        for table_schema, table_name in tables:
            columns = con.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = ?
                  AND table_name = ?
                ORDER BY ordinal_position
                """,
                [table_schema, table_name],
            ).fetchall()
            signature[f"{table_schema}.{table_name}"] = [
                f"{name}:{dtype}" for name, dtype in columns
            ]
        return signature


def _checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mini_platform_config(tmp_path: Path) -> AppConfig:
    """Compatibility helper retained for explicit fixtures in unit tests."""

    db_path = tmp_path / "mini_platform.duckdb"
    provision_miniplatform_warehouse(db_path)
    dbt_path = tmp_path / "dbt_project"
    provision_miniplatform_dbt_project(dbt_path)
    return AppConfig(db_path=db_path, dbt_path=dbt_path)


@pytest.fixture
def mini_platform_warehouse(tmp_path: Path) -> Path:
    """Provisioned deterministic DuckDB fixture."""

    db_path = tmp_path / "mini_platform.duckdb"
    provision_miniplatform_warehouse(db_path)
    return db_path


@pytest.fixture
def mini_platform_dbt_project(tmp_path: Path) -> Path:
    """Provisioned deterministic dbt fixture project."""

    dbt_path = tmp_path / "dbt_project"
    provision_miniplatform_dbt_project(dbt_path)
    return dbt_path


@pytest.fixture
def mini_platform_config_fixture(tmp_path: Path) -> AppConfig:
    """Provisioned deterministic app config."""

    db_path = tmp_path / "mini_platform.duckdb"
    dbt_path = tmp_path / "dbt_project"
    provision_miniplatform_warehouse(db_path)
    provision_miniplatform_dbt_project(dbt_path)
    return AppConfig(db_path=db_path, dbt_path=dbt_path)
