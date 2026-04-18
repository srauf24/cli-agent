"""CLI entrypoint for the Mini Data Platform agent."""

from __future__ import annotations

import typer

from .agent import answer_question
from .config import AppConfig
from .presenter import render_human, render_json

app = typer.Typer(help="Mini Data Platform Agent")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Natural language analytics question."),
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-n",
        min=1,
        help="Optional row cap for generated query result.",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Return response as machine-readable JSON.",
    ),
) -> None:
    """Handle one ad-hoc analytics question."""
    try:
        config = AppConfig.from_env()
        answer = answer_question(question, config=config, limit=limit)
    except Exception as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if output_json:
        print(render_json(answer, max_rows=5))
        return

    typer.echo(render_human(answer, max_rows=5))


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
