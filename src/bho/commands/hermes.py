"""Hermes Agent commands."""

from __future__ import annotations

import typer

from bho.core.docker.detector import (
    detect_docker_status,
    detect_linux_distribution,
)
from bho.core.docker.errors import DockerSetupError
from bho.core.docker.models import DockerHostStatus, DockerState
from bho.core.docker.setup import (
    add_user_to_docker_group,
    docker_install_commands,
    install_docker,
    start_docker_service,
)

from bho.core.hermes.configuration import (
    apply_and_verify_hermes_configuration,
    prepare_hermes_configuration,
)
from bho.core.hermes.detector import detect_hermes_status
from bho.core.hermes.errors import (
    HermesConfigurationError,
    HermesOperationError,
    HermesPartialInstallationError,
)
from bho.core.hermes.installer import OFFICIAL_INSTALL_SCRIPT_URL, install_hermes
from bho.core.hermes.models import HermesStatus, SubscriptionProviderOption
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

    typer.echo("Installing Hermes Agent non-interactively...")
    typer.echo(f"Installer: {OFFICIAL_INSTALL_SCRIPT_URL}")
    typer.echo("Optional setup and gateway stages will be skipped.")
    try:
        result = install_hermes()
    except HermesPartialInstallationError as error:
        typer.echo(f"Error: {error}", err=True)
        _render_installed_details(error.status)
        typer.echo("Run `bho hermes status` to inspect the current state.", err=True)
        raise typer.Exit(code=1) from error
    except HermesOperationError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo("Hermes Agent installed successfully.")
    _render_installed_details(result.status)


@app.command()
def configure(
    skip_live_check: bool = typer.Option(
        False,
        "--skip-live-check",
        help="Validate configuration without making a model inference request.",
    ),
) -> None:
    """Configure the dedicated Hermes profile used by bho."""
    current = detect_hermes_status()
    if not current.installed or current.executable is None:
        typer.echo("Hermes Agent is not installed.", err=True)
        typer.echo("Run `bho hermes install` first.", err=True)
        raise typer.Exit(code=1)

    typer.echo("Configuring Hermes Agent for bho...")
    if not _ensure_docker_ready():
        raise typer.Exit(code=1)

    try:
        preparation = prepare_hermes_configuration(current.executable)
    except HermesConfigurationError as error:
        _render_configuration_error(error)
        raise typer.Exit(code=1) from error

    typer.echo("")
    typer.echo("Hermes profile: bho")
    typer.echo(
        "Profile status: "
        + ("created" if preparation.profile.created else "existing")
    )
    if preparation.profile.path is not None:
        typer.echo(f"Profile path: {preparation.profile.path}")
    typer.echo(f"Docker executable: {preparation.docker.executable}")
    typer.echo("Docker daemon: available")

    _render_subscription_recommendations(preparation.subscription_providers)
    _render_configured_api_providers(
        preparation.current.configured_api_providers
    )

    existing = preparation.current
    reconfigure_model = True
    if (
        existing.model_configured
        and existing.authentication_configured
    ):
        typer.echo("")
        typer.echo(f"Current provider: {existing.provider}")
        typer.echo(f"Current model: {existing.model}")
        typer.echo("Authentication: configured")
        reconfigure_model = typer.confirm(
            "Reconfigure provider and model?",
            default=False,
        )
    else:
        typer.echo("")
        typer.echo(
            "The official Hermes provider and model wizard will now open."
        )
        typer.echo(
            "Choose a subscription-backed OAuth option first when it matches "
            "an active subscription."
        )

    try:
        verification = apply_and_verify_hermes_configuration(
            current.executable,
            reconfigure_model=reconfigure_model,
            skip_live_check=skip_live_check,
            hermes_version=current.version,
        )
    except HermesConfigurationError as error:
        _render_configuration_error(error)
        raise typer.Exit(code=1) from error

    configured = verification.configuration
    typer.echo("")
    typer.echo("Hermes Agent configuration completed.")
    typer.echo("Hermes profile: bho")
    typer.echo(f"Provider: {configured.provider}")
    typer.echo(f"Model: {configured.model}")
    typer.echo("Authentication: configured")
    typer.echo("Terminal backend: docker")
    typer.echo("Docker daemon: available")
    if verification.doctor.returncode == 0:
        typer.echo("Hermes diagnostics: passed")
    else:
        typer.echo(
            "Hermes diagnostics: completed with non-fatal warnings "
            f"(exit code {verification.doctor.returncode})"
        )
    if skip_live_check:
        typer.echo("Live model check: skipped")
        typer.echo(
            "Hermes Agent is configured for bho but has not been live-verified."
        )
    else:
        typer.echo("Live model check: passed")
        typer.echo("Hermes Agent is ready for bho.")


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
    typer.echo("If your shell still reports the old Hermes path, run: hash -r")


def _ensure_docker_ready() -> bool:
    """Offer explicit repairs until Docker is ready or user action is required."""
    for _ in range(4):
        status = detect_docker_status()
        if status.state is DockerState.READY:
            return True
        if status.state is DockerState.NOT_INSTALLED:
            if not _offer_docker_installation():
                return False
            continue
        if status.state is DockerState.DAEMON_STOPPED:
            if not _offer_docker_service_start(status):
                return False
            continue
        if status.state is DockerState.SESSION_REFRESH_REQUIRED:
            _render_session_refresh_required(status)
            return False
        if status.state is DockerState.PERMISSION_DENIED:
            if status.group_active_in_session:
                typer.echo(
                    "Docker access is still denied even though the docker group "
                    "is active in this session.",
                    err=True,
                )
                if status.detail:
                    typer.echo(f"Detail: {status.detail}", err=True)
                typer.echo(
                    "Inspect /var/run/docker.sock and the Docker service, then "
                    "run `bho hermes configure` again.",
                    err=True,
                )
                return False
            if not _offer_docker_group_setup(status):
                return False
            return False

        typer.echo("Docker is installed but could not be used.", err=True)
        if status.detail:
            typer.echo(f"Detail: {status.detail}", err=True)
        typer.echo(
            "Resolve the Docker error, then run `bho hermes configure` again.",
            err=True,
        )
        return False

    typer.echo(
        "Docker setup did not reach a usable state. Run `docker info` and retry.",
        err=True,
    )
    return False


def _offer_docker_installation() -> bool:
    """Offer a supported privileged Docker installation."""
    typer.echo("")
    typer.echo("Docker is not installed.")
    typer.echo("Docker is required for the bho Hermes profile.")
    distribution = detect_linux_distribution()
    typer.echo(f"Detected system: {distribution.name}")

    if not distribution.apt_supported:
        typer.echo(
            "Automatic Docker installation is currently supported only on "
            "Debian-, Ubuntu-, and Linux Mint-based systems using apt.",
            err=True,
        )
        typer.echo(
            "Install Docker manually, then run `bho hermes configure` again.",
            err=True,
        )
        return False

    typer.echo("")
    typer.echo("The following privileged commands will be executed:")
    try:
        commands = docker_install_commands(distribution)
    except DockerSetupError as error:
        typer.echo(f"Error: {error}", err=True)
        return False
    for command in commands:
        typer.echo(f"- {' '.join(command)}")

    if not typer.confirm("Install and configure Docker now?", default=False):
        typer.echo("Docker installation cancelled.")
        return False

    try:
        install_docker(distribution)
    except DockerSetupError as error:
        typer.echo(f"Docker installation failed: {error}", err=True)
        return False

    typer.echo("Docker installation completed.")
    return True


def _offer_docker_service_start(status: DockerHostStatus) -> bool:
    """Offer to enable and start an installed Docker daemon."""
    typer.echo("")
    typer.echo("Docker is installed, but the daemon is not running.")
    if status.detail:
        typer.echo(f"Detail: {status.detail}")
    if not typer.confirm("Start and enable Docker now?", default=False):
        typer.echo("Docker service setup cancelled.")
        return False

    try:
        start_docker_service()
    except DockerSetupError as error:
        typer.echo(f"Docker service setup failed: {error}", err=True)
        return False

    typer.echo("Docker service started and enabled.")
    return True


def _offer_docker_group_setup(status: DockerHostStatus) -> bool:
    """Offer non-root Docker access with a separate security confirmation."""
    username = status.current_user
    typer.echo("")
    typer.echo("Docker is installed, but the current user cannot access the daemon.")
    if status.detail:
        typer.echo(f"Detail: {status.detail}")
    if not username:
        typer.echo("The current user could not be identified safely.", err=True)
        return False

    typer.echo("")
    typer.echo(
        "Security warning: membership in the docker group grants root-level "
        "privileges on this machine."
    )
    if not typer.confirm(
        f'Add user "{username}" to the docker group?',
        default=False,
    ):
        typer.echo("Docker permission setup cancelled.")
        return False

    try:
        add_user_to_docker_group(username)
    except DockerSetupError as error:
        typer.echo(f"Docker permission setup failed: {error}", err=True)
        return False

    typer.echo(f'User "{username}" was added to the docker group.')
    typer.echo(
        "Log out completely and log back in, then run "
        "`bho hermes configure` again."
    )
    typer.echo(
        "The current process cannot safely activate the new group membership."
    )
    return True


def _render_session_refresh_required(status: DockerHostStatus) -> None:
    """Explain that configured group membership is not active in this session."""
    username = status.current_user or "The current user"
    typer.echo("")
    typer.echo(f'{username} is already configured in the docker group.')
    typer.echo(
        "The group membership is not active in this login session. "
        "Log out completely and log back in, then run "
        "`bho hermes configure` again."
    )


def _render_status(hermes_status: HermesStatus) -> None:
    if not hermes_status.installed:
        typer.echo("Hermes Agent: not installed")
        typer.echo(
            "Configuration: "
            f"{'found' if hermes_status.configuration_present else 'not found'}"
        )
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
    if status_format:
        typer.echo(f"Installer source: {hermes_status.installer_source or 'unknown'}")
        typer.echo(
            "Hermes install method: "
            f"{hermes_status.hermes_install_method or 'unknown'}"
        )


def _render_subscription_recommendations(
    options: tuple[SubscriptionProviderOption, ...],
) -> None:
    """Show subscription-backed provider options before the Hermes wizard."""
    typer.echo("")
    typer.echo("Subscription-first provider recommendations:")
    if not options:
        typer.echo("- No subscription-backed provider could be detected.")
        typer.echo("  The Hermes wizard will show all supported providers.")
        return

    for index, option in enumerate(options, start=1):
        status = (
            "authentication already configured"
            if option.authentication_configured
            else "authentication available"
        )
        typer.echo(f"{index}. {option.label} ({status})")
        typer.echo(f"   {option.description}")

    typer.echo(
        "Separately billed API providers remain available in the Hermes wizard."
    )


def _render_configured_api_providers(providers: tuple[str, ...]) -> None:
    """Show API-key providers already configured in the Hermes profile."""
    if not providers:
        return
    typer.echo("")
    typer.echo("Already configured API-key providers:")
    for provider in providers:
        typer.echo(f"- {provider}")


def _render_configuration_error(error: HermesConfigurationError) -> None:
    """Render a structured Hermes configuration failure."""
    typer.echo("", err=True)
    typer.echo("Hermes configuration was not completed.", err=True)
    if error.completed_stages:
        typer.echo("Completed stages:", err=True)
        for stage in error.completed_stages:
            typer.echo(f"- {stage}", err=True)
    typer.echo("Failed stage:", err=True)
    typer.echo(f"- {error.stage}", err=True)
    typer.echo(f"Error: {error}", err=True)
    typer.echo("Run `bho hermes configure` to retry.", err=True)
