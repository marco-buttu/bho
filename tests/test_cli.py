"""Tests for the bho command-line interface."""

from typer.testing import CliRunner

from bho.cli import app

runner = CliRunner()


def test_version_command() -> None:
    """The version command should print the installed version."""
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "bho 0.5.0"


def test_help_option() -> None:
    """The help option should describe the command-line application."""
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Manage Hermes Agent and software projects." in result.stdout
