"""Tests for Hermes version and metadata parsing."""

from pathlib import Path

import pytest

from bho.core.hermes.version import parse_hermes_metadata, parse_hermes_version


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("Hermes Agent v0.18.2", "0.18.2"),
        ("Hermes Agent 0.18.2", "0.18.2"),
        ("Hermes Agent\nVersion: 0.18.2", "0.18.2"),
        ("hermes version 0.18.2", "0.18.2"),
        ("v0.18.2", "0.18.2"),
        ("0.18.2", "0.18.2"),
        ("Hermes Agent v0.19.0-beta.1", "0.19.0-beta.1"),
        ("Hermes Agent 0.19.0+build.4", "0.19.0+build.4"),
        ("Hermes Agent v0.19.0 (2026.7.20)", "0.19.0"),
    ],
)
def test_parse_supported_version_outputs(output: str, expected: str) -> None:
    """Supported Hermes output formats should preserve the complete version."""
    assert parse_hermes_version(output) == expected


def test_parse_complete_hermes_metadata() -> None:
    """The current Hermes version output should expose install metadata."""
    output = (
        "Hermes Agent v0.19.0 (2026.7.20) \u00b7 upstream 03841c96\n"
        "Install directory: /home/user/.hermes/hermes-agent\n"
        "Install method: git\n"
        "Python: 3.11.15\n"
    )

    metadata = parse_hermes_metadata(output)

    assert metadata.version == "0.19.0"
    assert metadata.install_directory == Path("/home/user/.hermes/hermes-agent")
    assert metadata.install_method == "git"


def test_missing_metadata_fields_are_none() -> None:
    """Older version output should remain valid without extra metadata."""
    metadata = parse_hermes_metadata("Hermes Agent v0.18.2")

    assert metadata.version == "0.18.2"
    assert metadata.install_directory is None
    assert metadata.install_method is None


def test_invalid_output_returns_none() -> None:
    """Output without a version should not be treated as a version string."""
    assert parse_hermes_version("Hermes Agent development build") is None


def test_parser_does_not_drop_the_leading_zero() -> None:
    """A version prefixed by v must retain its leading zero component."""
    assert parse_hermes_version("Hermes Agent v0.18.2") != "18.2"
