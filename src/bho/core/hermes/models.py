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
    installation_method: str | None = None


@dataclass(frozen=True, slots=True)
class HermesInstallResult:
    """Describe the result of a Hermes installation request."""

    status: HermesStatus
    installed_now: bool


@dataclass(frozen=True, slots=True)
class HermesUninstallResult:
    """Describe the result of a Hermes uninstallation request."""

    uninstalled_now: bool
    already_absent: bool
    data_preserved: bool
