from __future__ import annotations

from pathlib import Path

import pytest

from mini_data_platform_agent.config import AppConfig


def test_default_config_has_expected_values() -> None:
    cfg = AppConfig()

    assert cfg.db_path == Path("warehouse/data.duckdb")
    assert cfg.dbt_path == Path("dbt_project")
    assert cfg.evidence_path == Path("evidence")
    assert cfg.default_limit == 200
    assert cfg.max_limit == 5000
    assert cfg.query_timeout_ms == 10000


def test_config_reads_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_AGENT_DB_PATH", "/tmp/test.duckdb")
    monkeypatch.setenv("MINI_AGENT_DBT_PATH", "/tmp/dbt")
    monkeypatch.setenv("MINI_AGENT_EVIDENCE_PATH", "/tmp/evidence")
    monkeypatch.setenv("MINI_AGENT_DEFAULT_LIMIT", "250")
    monkeypatch.setenv("MINI_AGENT_MAX_LIMIT", "300")
    monkeypatch.setenv("MINI_AGENT_QUERY_TIMEOUT_MS", "30000")

    cfg = AppConfig.from_env()

    assert cfg.db_path == Path("/tmp/test.duckdb")
    assert cfg.dbt_path == Path("/tmp/dbt")
    assert cfg.evidence_path == Path("/tmp/evidence")
    assert cfg.default_limit == 250
    assert cfg.max_limit == 300
    assert cfg.query_timeout_ms == 30000


def test_effective_limit_is_capped() -> None:
    cfg = AppConfig(default_limit=50, max_limit=100)
    assert cfg.effective_limit() == 50
    assert cfg.effective_limit(10) == 10
    assert cfg.effective_limit(1000) == 100


def test_invalid_limits_raise_validation_error() -> None:
    with pytest.raises(ValueError, match="must be a positive integer"):
        AppConfig(default_limit=0)

    with pytest.raises(ValueError, match="max_limit must be greater than"):
        AppConfig(default_limit=200, max_limit=10)

