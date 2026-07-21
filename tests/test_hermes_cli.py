"""Tests for Hermes Agent CLI commands."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bho.cli import app
from bho.core.hermes.errors import HermesOperationError
from bho.core.hermes.models import (
    HermesInstallResult,
    HermesStatus,
    HermesUninstallResult,
)

runner = CliRunner()


def _status(
    *,
    installed: bool = True,
    managed: bool = False,
    method: str | None = "official-user-installer",
) -> HermesStatus:
    return HermesStatus(
        installed=installed,
        executable=Path("/home/user/.local/bin/hermes") if installed else None,
        version="0.18.2" if installed else None,
        configuration_present=True,
        managed_by_bho=managed,
        installation_method=method if installed else None,
    )


def test_hermes_status_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should report a valid absent state."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False, method=None),
    )

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "Hermes Agent: not installed"


def test_hermes_status_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should render detected Hermes details."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert "Version: 0.18.2" in result.stdout
    assert "Managed by bho: no" in result.stdout
    assert "Installation method: official-user-installer" in result.stdout
    assert "Configuration: found" in result.stdout


def test_install_when_already_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should not reinstall an existing Hermes installation."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.install_hermes",
        lambda: (_ for _ in ()).throw(AssertionError("Install should not run.")),
    )

    result = runner.invoke(app, ["hermes", "install"])

    assert result.exit_code == 0
    assert "Hermes Agent is already installed." in result.stdout


def test_successful_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should report a verified managed installation."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False, method=None),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.install_hermes",
        lambda: HermesInstallResult(_status(managed=True), installed_now=True),
    )

    result = runner.invoke(app, ["hermes", "install"])

    assert result.exit_code == 0
    assert "Hermes Agent installed successfully." in result.stdout
    assert "Managed by bho: yes" in result.stdout


def test_install_failure_returns_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Installation errors should be visible and return a failing exit code."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False, method=None),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.install_hermes",
        lambda: (_ for _ in ()).throw(HermesOperationError("install failed")),
    )

    result = runner.invoke(app, ["hermes", "install"])

    assert result.exit_code == 1
    assert "Error: install failed" in result.output


def test_uninstall_can_be_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Declining confirmation should leave Hermes untouched."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.uninstall_hermes",
        lambda: (_ for _ in ()).throw(AssertionError("Uninstall should not run.")),
    )

    result = runner.invoke(app, ["hermes", "uninstall"], input="n\n")

    assert result.exit_code == 0
    assert "Uninstall cancelled." in result.stdout


def test_uninstall_yes_skips_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The --yes option should support non-interactive uninstall."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.uninstall_hermes",
        lambda: HermesUninstallResult(True, False, True),
    )

    result = runner.invoke(app, ["hermes", "uninstall", "--yes"])

    assert result.exit_code == 0
    assert "not managed by bho" in result.stdout
    assert "Hermes Agent uninstalled successfully." in result.stdout
    assert "Configuration and user data were preserved." in result.stdout
    assert "Uninstall Hermes Agent?" not in result.stdout


def test_uninstall_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """An absent installation should be treated as a successful valid state."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False, method=None),
    )

    result = runner.invoke(app, ["hermes", "uninstall"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "Hermes Agent is not installed."


def test_uninstall_failure_returns_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uninstall errors should be visible and return a failing exit code."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.uninstall_hermes",
        lambda: (_ for _ in ()).throw(HermesOperationError("uninstall failed")),
    )

    result = runner.invoke(app, ["hermes", "uninstall", "--yes"])

    assert result.exit_code == 1
    assert "Error: uninstall failed" in result.output
