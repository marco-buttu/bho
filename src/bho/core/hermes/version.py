"""Parse Hermes Agent version and installation metadata."""

from __future__ import annotations

import re
from pathlib import Path

from bho.core.hermes.models import HermesCommandMetadata

_VERSION_VALUE = r"\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?"
_VERSION_PATTERNS = (
    re.compile(
        rf"(?i)\bhermes(?:\s+agent)?(?:\s+version)?\s*[:=]?\s*v?(?P<version>{_VERSION_VALUE})"
    ),
    re.compile(rf"(?i)\bversion\s*[:=]?\s*v?(?P<version>{_VERSION_VALUE})"),
    re.compile(rf"(?<![0-9A-Za-z.])v(?P<version>{_VERSION_VALUE})"),
    re.compile(rf"(?<![0-9A-Za-z.])(?P<version>{_VERSION_VALUE})"),
)
_INSTALL_DIRECTORY_PATTERN = re.compile(
    r"(?im)^\s*Install directory\s*:\s*(?P<path>.+?)\s*$"
)
_INSTALL_METHOD_PATTERN = re.compile(
    r"(?im)^\s*Install method\s*:\s*(?P<method>[^\s]+)\s*$"
)


def parse_hermes_metadata(output: str) -> HermesCommandMetadata:
    """Extract version and installation metadata from Hermes output."""
    install_directory_match = _INSTALL_DIRECTORY_PATTERN.search(output)
    install_method_match = _INSTALL_METHOD_PATTERN.search(output)

    return HermesCommandMetadata(
        version=parse_hermes_version(output),
        install_directory=(
            Path(install_directory_match.group("path")).expanduser()
            if install_directory_match
            else None
        ),
        install_method=(
            install_method_match.group("method") if install_method_match else None
        ),
    )


def parse_hermes_version(output: str) -> str | None:
    """Extract a semantic-looking Hermes version from command output."""
    for pattern in _VERSION_PATTERNS:
        match = pattern.search(output)
        if match:
            return match.group("version")
    return None
