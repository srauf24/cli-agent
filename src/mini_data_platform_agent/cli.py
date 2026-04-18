"""CLI entrypoint for the Mini Data Platform agent."""

from __future__ import annotations

import typer

from .agent import answer_question
from .config import AppConfig

app = typer.Typer(help="Mini Data Platform Agent")


def _format_row_preview(rows: list[dict]) -> list[str]:
    return [str(row) for row in rows]


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
        print(answer.model_dump_json(indent=2))
        return

    typer.echo(f"Question: {answer.question}")
    typer.echo(
        f"Intent: {answer.intent.intent} (confidence={answer.intent.confidence:.2f})"
    )
    typer.echo("Assumptions: " + ", ".join(answer.assumptions))
    typer.echo("SQL:")
    typer.echo(answer.sql)
    if answer.result is not None:
        typer.echo(f"Rows: {answer.result.row_count}")
        typer.echo(f"Summary: {answer.summary}")
        for row in answer.result.rows[:5]:
            typer.echo(_format_row_preview([row])[0])


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
