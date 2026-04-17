"""CLI entrypoint for the Mini Data Platform agent."""

from __future__ import annotations

import typer

app = typer.Typer(help="Mini Data Platform Agent")


@app.command()
def ask(question: str) -> None:
    """Placeholder command for the final ask flow."""
    raise typer.Exit(code=0)


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()

