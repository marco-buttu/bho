"""Tests for Hermes Agent CLI commands."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bho.cli import app
from bho.core.hermes.errors import (
    HermesOperationError,
    HermesPartialInstallationError,
)
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
    configuration_present: bool = True,
) -> HermesStatus:
    return HermesStatus(
        installed=installed,
        executable=Path("/home/user/.local/bin/hermes") if installed else None,
        version="0.19.0" if installed else None,
        configuration_present=configuration_present,
        managed_by_bho=managed,
        installer_source="official-user-installer" if managed else None,
        hermes_install_method="git" if installed else None,
        install_directory=(
            Path("/home/user/.hermes/hermes-agent") if installed else None
        ),
    )


def test_hermes_status_when_not_installed_with_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI should report preserved configuration when Hermes is absent."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False, configuration_present=True),
    )

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert result.stdout.strip().splitlines() == [
        "Hermes Agent: not installed",
        "Configuration: found",
    ]


def test_hermes_status_when_not_installed_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI should distinguish a completely absent Hermes state."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False, configuration_present=False),
    )

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert "Configuration: not found" in result.stdout


def test_hermes_status_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should render separate installer and Hermes metadata."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(managed=True),
    )

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert "Version: 0.19.0" in result.stdout
    assert "Managed by bho: yes" in result.stdout
    assert "Installer source: official-user-installer" in result.stdout
    assert "Hermes install method: git" in result.stdout
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
        lambda: _status(installed=False),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.install_hermes",
        lambda: HermesInstallResult(_status(managed=True), installed_now=True),
    )

    result = runner.invoke(app, ["hermes", "install"])

    assert result.exit_code == 0
    assert "Installing Hermes Agent non-interactively..." in result.stdout
    assert "Optional setup and gateway stages will be skipped." in result.stdout
    assert "Hermes Agent installed successfully." in result.stdout
    assert "Managed by bho: yes" in result.stdout


def test_partial_install_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """An interrupted installation should report the reconciled state."""
    partial = _status(managed=False)
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.install_hermes",
        lambda: (_ for _ in ()).throw(
            HermesPartialInstallationError("install interrupted", partial)
        ),
    )

    result = runner.invoke(app, ["hermes", "install"])

    assert result.exit_code == 1
    assert "Error: install interrupted" in result.output
    assert "Executable: /home/user/.local/bin/hermes" in result.output
    assert "Managed by bho: no" in result.output
    assert "Run `bho hermes status`" in result.output


def test_install_failure_returns_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Installation errors should be visible and return a failing exit code."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False),
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
    assert "hash -r" in result.stdout
    assert "Uninstall Hermes Agent?" not in result.stdout


def test_uninstall_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """An absent installation should be treated as a successful valid state."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False),
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
