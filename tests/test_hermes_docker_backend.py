"""Tests for the Hermes Docker terminal backend."""

import subprocess
from pathlib import Path

import pytest

from bho.core.hermes.docker_backend import (
    check_docker_availability,
    configure_docker_backend,
    required_docker_settings,
)
from bho.core.hermes.errors import HermesConfigurationError


def test_missing_docker_is_reported() -> None:
    """Docker absence must not silently select the local terminal backend."""
    result = check_docker_availability(which_fn=lambda name: None)

    assert result.executable is None
    assert result.daemon_available is False


def test_unreachable_docker_daemon_is_reported(tmp_path: Path) -> None:
    """The Docker executable alone is insufficient when the daemon is unavailable."""
    result = check_docker_availability(
        which_fn=lambda name: str(tmp_path / "docker"),
        run_fn=lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr="permission denied",
        ),
    )

    assert result.executable == tmp_path / "docker"
    assert result.daemon_available is False
    assert result.detail == "permission denied"


def test_available_docker_daemon(tmp_path: Path) -> None:
    """A successful docker info command should satisfy the precondition."""
    result = check_docker_availability(
        which_fn=lambda name: str(tmp_path / "docker"),
        run_fn=lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="Server Version: 27",
            stderr="",
        ),
    )

    assert result.daemon_available is True


def test_required_docker_settings_are_applied(tmp_path: Path) -> None:
    """bho must configure isolation and avoid forwarding host credentials."""
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout="ok", stderr="")

    configure_docker_backend(
        tmp_path / "hermes",
        "bho",
        run_fn=fake_run,
    )

    expected = [
        [
            str(tmp_path / "hermes"),
            "-p",
            "bho",
            "config",
            "set",
            key,
            value,
        ]
        for key, value in required_docker_settings()
    ]
    assert calls == expected
    assert calls[-1][-2:] == ["terminal.docker_forward_env", "[]"]


def test_unsupported_docker_setting_fails_clearly(tmp_path: Path) -> None:
    """bho must not weaken isolation when Hermes rejects a required setting."""
    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            arguments,
            2,
            stdout="",
            stderr="unknown configuration key",
        )

    with pytest.raises(HermesConfigurationError, match="required setting") as captured:
        configure_docker_backend(
            tmp_path / "hermes",
            "bho",
            run_fn=fake_run,
        )

    assert captured.value.stage == "Docker backend configuration"
