"""Command-line interface for bho."""

import typer

from bho import __version__

app = typer.Typer(
    name="bho",
    help="Manage Hermes Agent and software projects.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Manage Hermes Agent and software projects."""


@app.command()
def version() -> None:
    """Show the installed bho version."""
    typer.echo(f"bho {__version__}")


if __name__ == "__main__":
    app()
