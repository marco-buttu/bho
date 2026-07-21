"""Hermes Agent commands."""

import typer

from bho.core.hermes.detector import detect_hermes_status

app = typer.Typer(
    help="Inspect and manage Hermes Agent.",
    no_args_is_help=True,
)


@app.command()
def status() -> None:
    """Show the current Hermes Agent installation status."""
    hermes_status = detect_hermes_status()

    if not hermes_status.installed:
        typer.echo("Hermes Agent: not installed")
        return

    typer.echo("Hermes Agent: installed")
    typer.echo(f"Executable: {hermes_status.executable}")
    typer.echo(f"Version: {hermes_status.version or 'unknown'}")
    typer.echo(
        f"Managed by bho: {'yes' if hermes_status.managed_by_bho else 'no'}"
    )
    typer.echo(
        "Configuration: "
        f"{'found' if hermes_status.configuration_present else 'not found'}"
    )
