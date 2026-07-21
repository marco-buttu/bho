"""Tests for Hermes version parsing."""

import pytest

from bho.core.hermes.version import parse_hermes_version


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
    ],
)
def test_parse_supported_version_outputs(output: str, expected: str) -> None:
    """Supported Hermes output formats should preserve the complete version."""
    assert parse_hermes_version(output) == expected


def test_invalid_output_returns_none() -> None:
    """Output without a version should not be treated as a version string."""
    assert parse_hermes_version("Hermes Agent development build") is None


def test_parser_does_not_drop_the_leading_zero() -> None:
    """A version prefixed by v must retain its leading zero component."""
    assert parse_hermes_version("Hermes Agent v0.18.2") != "18.2"
