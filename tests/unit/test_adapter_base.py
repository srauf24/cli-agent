"""Tests for the adapter interface contract."""

from __future__ import annotations

import pytest

from mini_data_platform_agent.adapter.base import PlatformAdapter
from mini_data_platform_agent.config import AppConfig
from mini_data_platform_agent.types import PlatformContext, QueryResult


def test_platform_adapter_is_abstract():
    class IncompleteAdapter(PlatformAdapter):
        pass

    with pytest.raises(TypeError):
        IncompleteAdapter(config=AppConfig())


def test_platform_adapter_exposes_required_methods():
    class DummyAdapter(PlatformAdapter):
        def health_check(self) -> bool:
            return True

        def load_context(self) -> PlatformContext:
            return PlatformContext()

        def _execute_select(self, sql: str, limit: int) -> QueryResult:
            return QueryResult(columns=["ok"], rows=[{"ok": True}], row_count=1, duration_ms=1)

    adapter = DummyAdapter(config=AppConfig())
    assert callable(adapter.health_check)
    assert callable(adapter.load_context)
    assert callable(adapter.run_select)
    assert callable(adapter._execute_select)
    result = adapter.run_select("SELECT 1", limit=1)
    assert result.row_count == 1
    assert result.rows == [{"ok": True}]

