"""Tests for Hermes Agent CLI commands."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bho.cli import app
from bho.core.hermes.models import HermesStatus

runner = CliRunner()


def test_hermes_status_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should report a valid absent state."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: HermesStatus(
            installed=False,
            executable=None,
            version=None,
            configuration_present=False,
            managed_by_bho=False,
        ),
    )

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "Hermes Agent: not installed"


def test_hermes_status_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should render all detected Hermes details."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: HermesStatus(
            installed=True,
            executable=Path("/opt/hermes/bin/hermes"),
            version="1.2.3",
            configuration_present=True,
            managed_by_bho=False,
        ),
    )

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert result.stdout == (
        "Hermes Agent: installed\n"
        "Executable: /opt/hermes/bin/hermes\n"
        "Version: 1.2.3\n"
        "Managed by bho: no\n"
        "Configuration: found\n"
    )


def test_hermes_status_with_unknown_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should render unknown when version detection fails."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: HermesStatus(
            installed=True,
            executable=Path("/opt/hermes/bin/hermes"),
            version=None,
            configuration_present=False,
            managed_by_bho=True,
        ),
    )

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert "Version: unknown" in result.stdout
    assert "Managed by bho: yes" in result.stdout
    assert "Configuration: not found" in result.stdout
