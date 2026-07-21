"""Parse Hermes Agent version output."""

from __future__ import annotations

import re

_VERSION_VALUE = r"\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?"
_VERSION_PATTERNS = (
    re.compile(
        rf"(?i)\bhermes(?:\s+agent)?(?:\s+version)?\s*[:=]?\s*v?(?P<version>{_VERSION_VALUE})"
    ),
    re.compile(rf"(?i)\bversion\s*[:=]?\s*v?(?P<version>{_VERSION_VALUE})"),
    re.compile(rf"(?<![0-9A-Za-z.])v(?P<version>{_VERSION_VALUE})"),
    re.compile(rf"(?<![0-9A-Za-z.])(?P<version>{_VERSION_VALUE})"),
)


def parse_hermes_version(output: str) -> str | None:
    """Extract a semantic-looking Hermes version from command output."""
    for pattern in _VERSION_PATTERNS:
        match = pattern.search(output)
        if match:
            return match.group("version")
    return None
