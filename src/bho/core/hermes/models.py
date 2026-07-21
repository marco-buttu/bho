"""Data models for Hermes Agent integration."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HermesStatus:
    """Describe the detected local Hermes Agent state."""

    installed: bool
    executable: Path | None
    version: str | None
    configuration_present: bool
    managed_by_bho: bool
