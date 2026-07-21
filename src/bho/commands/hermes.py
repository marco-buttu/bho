"""Hermes Agent commands."""

from __future__ import annotations

import typer

from bho.core.hermes.detector import detect_hermes_status
from bho.core.hermes.errors import HermesOperationError
from bho.core.hermes.installer import OFFICIAL_INSTALL_SCRIPT_URL, install_hermes
from bho.core.hermes.models import HermesStatus
from bho.core.hermes.uninstaller import uninstall_hermes

app = typer.Typer(
    help="Inspect and manage Hermes Agent.",
    no_args_is_help=True,
)


@app.command()
def status() -> None:
    """Show the current Hermes Agent installation status."""
    _render_status(detect_hermes_status())


@app.command()
def install() -> None:
    """Install Hermes Agent using its official installer."""
    current = detect_hermes_status()
    if current.installed:
        typer.echo("Hermes Agent is already installed.")
        _render_installed_details(current)
        return

    typer.echo("Installing Hermes Agent...")
    typer.echo(f"Installer: {OFFICIAL_INSTALL_SCRIPT_URL}")
    try:
        result = install_hermes()
    except HermesOperationError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo("Hermes Agent installed successfully.")
    _render_installed_details(result.status)


@app.command()
def uninstall(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Confirm uninstall without prompting.",
    ),
) -> None:
    """Uninstall Hermes Agent while preserving configuration and user data."""
    current = detect_hermes_status()
    if not current.installed:
        typer.echo("Hermes Agent is not installed.")
        return

    if not current.managed_by_bho:
        typer.echo("Hermes Agent is installed but is not managed by bho.")
    typer.echo(f"Executable: {current.executable}")
    typer.echo("Configuration and user data will be preserved.")

    if not yes and not typer.confirm("Uninstall Hermes Agent?", default=False):
        typer.echo("Uninstall cancelled.")
        return

    try:
        result = uninstall_hermes()
    except HermesOperationError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    if result.already_absent:
        typer.echo("Hermes Agent is not installed.")
        return

    typer.echo("Hermes Agent uninstalled successfully.")
    typer.echo("Configuration and user data were preserved.")


def _render_status(hermes_status: HermesStatus) -> None:
    if not hermes_status.installed:
        typer.echo("Hermes Agent: not installed")
        return

    typer.echo("Hermes Agent: installed")
    _render_installed_details(hermes_status, status_format=True)
    typer.echo(
        "Configuration: "
        f"{'found' if hermes_status.configuration_present else 'not found'}"
    )


def _render_installed_details(
    hermes_status: HermesStatus,
    *,
    status_format: bool = False,
) -> None:
    typer.echo(f"Executable: {hermes_status.executable}")
    typer.echo(f"Version: {hermes_status.version or 'unknown'}")
    typer.echo(
        f"Managed by bho: {'yes' if hermes_status.managed_by_bho else 'no'}"
    )
    if status_format and hermes_status.installation_method:
        typer.echo(f"Installation method: {hermes_status.installation_method}")
