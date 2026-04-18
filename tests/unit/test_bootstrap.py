from __future__ import annotations

from pathlib import Path
import sys
import tomllib
from typer.testing import CliRunner


def _load_project_config() -> dict:
    project_file = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with open(project_file, "rb") as f:
        return tomllib.load(f)


def test_cli_entrypoint_is_declared() -> None:
    config = _load_project_config()
    scripts = config["project"]["scripts"]
    assert scripts["mini-agent"] == "mini_data_platform_agent.cli:app"


def test_runtime_dependencies_declared() -> None:
    config = _load_project_config()
    deps = set(config["project"]["dependencies"])

    required = {"duckdb", "typer", "rich", "pydantic", "sqlparse", "jinja2"}
    assert required.issubset({dep.split(">=")[0].split("==")[0] for dep in deps})


def test_test_dependency_group_declared() -> None:
    config = _load_project_config()
    extras = config["project"].get("optional-dependencies", {})
    test_deps = extras.get("test")
    assert test_deps is not None
    assert any(dep.startswith("pytest") for dep in test_deps)


def test_import_smoke_package() -> None:
    src_path = Path(__file__).resolve().parents[2] / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    import mini_data_platform_agent  # noqa: F401
    import mini_data_platform_agent.cli  # noqa: F401


def test_cli_help_invokes_successfully() -> None:
    src_path = Path(__file__).resolve().parents[2] / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    from mini_data_platform_agent.cli import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "Mini Data Platform Agent" in result.output or "ask [OPTIONS] QUESTION" in result.output
