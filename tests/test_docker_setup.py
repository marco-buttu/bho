"""Tests for explicit Docker host setup operations."""

from __future__ import annotations

import subprocess

import pytest

from bho.core.docker.errors import DockerSetupError
from bho.core.docker.models import LinuxDistribution
from bho.core.docker.setup import (
    add_user_to_docker_group,
    docker_install_commands,
    install_docker,
    start_docker_service,
)


def _mint() -> LinuxDistribution:
    return LinuxDistribution(
        distribution_id="linuxmint",
        name="Linux Mint",
        id_like=("ubuntu", "debian"),
        package_manager="apt-get",
    )


def test_install_plan_uses_argument_lists() -> None:
    commands = docker_install_commands(_mint())

    assert commands == (
        ("sudo", "apt-get", "update"),
        ("sudo", "apt-get", "install", "-y", "docker.io"),
        ("sudo", "systemctl", "enable", "--now", "docker"),
    )


def test_install_runs_only_explicit_commands() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(
        arguments: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 0)

    install_docker(_mint(), run_fn=fake_run)

    assert [call[0] for call in calls] == [
        list(item) for item in docker_install_commands(_mint())
    ]
    assert all("shell" not in kwargs for _, kwargs in calls)


def test_unsupported_distribution_is_rejected() -> None:
    with pytest.raises(DockerSetupError, match="currently supported only"):
        docker_install_commands(
            LinuxDistribution("arch", "Arch Linux", (), None)
        )


def test_service_start_uses_systemctl() -> None:
    calls: list[list[str]] = []

    def fake_run(
        arguments: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0)

    start_docker_service(run_fn=fake_run)

    assert calls == [["sudo", "systemctl", "enable", "--now", "docker"]]


def test_group_setup_is_separate_from_installation() -> None:
    calls: list[list[str]] = []

    def fake_run(
        arguments: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0)

    add_user_to_docker_group("marco", run_fn=fake_run)

    assert calls == [
        ["sudo", "groupadd", "-f", "docker"],
        ["sudo", "usermod", "-aG", "docker", "marco"],
    ]


def test_privileged_command_failure_is_reported() -> None:
    def fake_run(
        arguments: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 1)

    with pytest.raises(DockerSetupError, match="exit code 1"):
        start_docker_service(run_fn=fake_run)
