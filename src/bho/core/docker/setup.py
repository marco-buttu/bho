"""Perform explicit, privileged Docker host setup operations."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence

from bho.core.docker.errors import DockerSetupError
from bho.core.docker.models import LinuxDistribution

RunFunction = Callable[..., subprocess.CompletedProcess[str]]

APT_DOCKER_PACKAGE = "docker.io"


def docker_install_commands(
    distribution: LinuxDistribution,
) -> tuple[tuple[str, ...], ...]:
    """Return the privileged commands used by the supported installer."""
    if not distribution.apt_supported:
        raise DockerSetupError(
            "Guided Docker installation is currently supported only on "
            "Debian-, Ubuntu-, and Linux Mint-based systems with apt."
        )
    return (
        ("sudo", "apt-get", "update"),
        ("sudo", "apt-get", "install", "-y", APT_DOCKER_PACKAGE),
        ("sudo", "systemctl", "enable", "--now", "docker"),
    )


def install_docker(
    distribution: LinuxDistribution,
    *,
    run_fn: RunFunction = subprocess.run,
) -> None:
    """Install and start Docker after the caller has obtained user consent."""
    commands = docker_install_commands(distribution)
    _run_commands(
        commands,
        run_fn=run_fn,
        timeout_by_command=(900, 900, 120),
        action="Docker installation",
    )


def start_docker_service(
    *,
    run_fn: RunFunction = subprocess.run,
) -> None:
    """Enable and start the Docker system service."""
    _run_commands(
        (("sudo", "systemctl", "enable", "--now", "docker"),),
        run_fn=run_fn,
        timeout_by_command=(120,),
        action="Docker service setup",
    )


def add_user_to_docker_group(
    username: str,
    *,
    run_fn: RunFunction = subprocess.run,
) -> None:
    """Create the Docker group if needed and add one explicit user."""
    if not username or username == "root" or any(char.isspace() for char in username):
        raise DockerSetupError("Refusing to modify an invalid user account.")
    _run_commands(
        (
            ("sudo", "groupadd", "-f", "docker"),
            ("sudo", "usermod", "-aG", "docker", username),
        ),
        run_fn=run_fn,
        timeout_by_command=(60, 60),
        action="Docker group setup",
    )


def _run_commands(
    commands: Sequence[Sequence[str]],
    *,
    run_fn: RunFunction,
    timeout_by_command: Sequence[int],
    action: str,
) -> None:
    for command, timeout in zip(commands, timeout_by_command, strict=True):
        try:
            result = run_fn(
                list(command),
                check=False,
                timeout=timeout,
            )
        except KeyboardInterrupt as error:
            raise DockerSetupError(f"{action} was cancelled.") from error
        except subprocess.TimeoutExpired as error:
            raise DockerSetupError(
                f"{action} timed out while running: {' '.join(command)}"
            ) from error
        except OSError as error:
            raise DockerSetupError(
                f"{action} could not run {' '.join(command)}: {error}"
            ) from error

        if result.returncode != 0:
            raise DockerSetupError(
                f"{action} failed with exit code {result.returncode} while "
                f"running: {' '.join(command)}"
            )
