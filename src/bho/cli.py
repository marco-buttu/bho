"""Command-line interface for bho."""

import typer

from bho import __version__
from bho.commands.hermes import app as hermes_app

app = typer.Typer(
    name="bho",
    help="Manage Hermes Agent and software projects.",
    no_args_is_help=True,
)
app.add_typer(hermes_app, name="hermes")


@app.callback()
def main() -> None:
    """Manage Hermes Agent and software projects."""


@app.command()
def version() -> None:
    """Show the installed bho version."""
    typer.echo(f"bho {__version__}")


if __name__ == "__main__":
    app()
