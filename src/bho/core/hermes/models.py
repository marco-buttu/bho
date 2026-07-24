"""Data models for Hermes Agent integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HermesCommandMetadata:
    """Describe metadata reported by a Hermes version command."""

    version: str | None = None
    install_directory: Path | None = None
    install_method: str | None = None


@dataclass(frozen=True, slots=True)
class ManagedInstallationRecord:
    """Describe a bho-managed Hermes installation marker."""

    executable: Path
    version: str | None
    install_directory: Path | None
    installer_source: str
    hermes_install_method: str | None
    installed_at: str


@dataclass(frozen=True, slots=True)
class HermesStatus:
    """Describe the detected local Hermes Agent state."""

    installed: bool
    executable: Path | None
    version: str | None
    configuration_present: bool
    managed_by_bho: bool
    installer_source: str | None = None
    hermes_install_method: str | None = None
    install_directory: Path | None = None


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
