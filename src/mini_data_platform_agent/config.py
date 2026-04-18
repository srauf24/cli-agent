"""Configuration models for the CLI agent."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AppConfig(BaseModel):
    """Runtime configuration loaded from environment or defaults."""

    model_config = ConfigDict(frozen=True)

    db_path: Path = Field(default=Path("warehouse/data.duckdb"))
    dbt_path: Path = Field(default=Path("dbt_project"))
    evidence_path: Path = Field(default=Path("evidence"))

    default_limit: int = Field(default=200)
    max_limit: int = Field(default=5000)
    query_timeout_ms: int = Field(default=10000)

    @field_validator("default_limit", "max_limit", "query_timeout_ms")
    @classmethod
    def _positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be a positive integer")
        return value

    @model_validator(mode="after")
    def _validate_limits(self) -> "AppConfig":
        if self.max_limit < self.default_limit:
            raise ValueError("max_limit must be greater than or equal to default_limit")
        return self

    @classmethod
    def from_env(cls, prefix: str = "MINI_AGENT") -> "AppConfig":
        """Build config from environment variables."""
        env = os.environ
        data: dict[str, str] = {}

        env_map = {
            "db_path": f"{prefix}_DB_PATH",
            "dbt_path": f"{prefix}_DBT_PATH",
            "evidence_path": f"{prefix}_EVIDENCE_PATH",
            "default_limit": f"{prefix}_DEFAULT_LIMIT",
            "max_limit": f"{prefix}_MAX_LIMIT",
            "query_timeout_ms": f"{prefix}_QUERY_TIMEOUT_MS",
        }

        for field, env_key in env_map.items():
            if env_key in env and env[env_key].strip():
                data[field] = env[env_key].strip()

        if "db_path" in data:
            data["db_path"] = Path(data["db_path"])
        if "dbt_path" in data:
            data["dbt_path"] = Path(data["dbt_path"])
        if "evidence_path" in data:
            data["evidence_path"] = Path(data["evidence_path"])
        if "default_limit" in data:
            data["default_limit"] = int(data["default_limit"])
        if "max_limit" in data:
            data["max_limit"] = int(data["max_limit"])
        if "query_timeout_ms" in data:
            data["query_timeout_ms"] = int(data["query_timeout_ms"])

        return cls.model_validate(data)

    def effective_limit(self, requested_limit: int | None = None) -> int:
        """Clamp a requested limit to safe, configured limits."""
        requested = self.default_limit if requested_limit is None else requested_limit
        if requested <= 0:
            raise ValueError("limit must be positive")
        return min(self.max_limit, requested)
