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


@dataclass(frozen=True, slots=True)
class HermesProfileResult:
    """Describe creation or reuse of a Hermes profile."""

    name: str
    path: Path | None
    created: bool


@dataclass(frozen=True, slots=True)
class SubscriptionProviderOption:
    """Describe a subscription-backed provider supported by Hermes."""

    provider: str
    label: str
    description: str
    supported: bool
    authentication_configured: bool


@dataclass(frozen=True, slots=True)
class DockerAvailability:
    """Describe whether Docker can be used by the current user."""

    executable: Path | None
    daemon_available: bool
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class HermesProfileConfiguration:
    """Describe the non-secret configuration of one Hermes profile."""

    profile_name: str
    profile_path: Path | None
    provider: str | None
    model: str | None
    authentication_configured: bool
    configured_api_providers: tuple[str, ...]
    terminal_backend: str | None
    docker_mount_cwd_to_workspace: bool | None
    docker_run_as_host_user: bool | None
    docker_forward_env_empty: bool | None
    fallback_configured: bool

    @property
    def model_configured(self) -> bool:
        """Return whether both provider and model are selected."""
        return bool(self.provider and self.model)

    @property
    def docker_configured(self) -> bool:
        """Return whether the required Docker isolation settings are active."""
        return (
            self.terminal_backend == "docker"
            and self.docker_mount_cwd_to_workspace is True
            and self.docker_run_as_host_user is True
            and self.docker_forward_env_empty is True
        )


@dataclass(frozen=True, slots=True)
class HermesDoctorResult:
    """Describe Hermes diagnostic execution."""

    completed: bool
    returncode: int
    summary: str | None


@dataclass(frozen=True, slots=True)
class HermesConfigurationVerification:
    """Describe the final verification of the bho Hermes profile."""

    configuration: HermesProfileConfiguration
    doctor: HermesDoctorResult
    live_check_passed: bool | None
    live_check_output: str | None

    @property
    def required_checks_passed(self) -> bool:
        """Return whether all non-live checks required by bho passed."""
        return (
            self.configuration.model_configured
            and self.configuration.authentication_configured
            and self.configuration.docker_configured
            and self.doctor.completed
        )

    @property
    def ready(self) -> bool:
        """Return whether required checks and the live check passed."""
        return self.required_checks_passed and self.live_check_passed is True


@dataclass(frozen=True, slots=True)
class ConfiguredProfileRecord:
    """Describe non-secret bho metadata for a configured Hermes profile."""

    profile_name: str
    profile_path: Path | None
    provider: str
    model: str
    terminal_backend: str
    verified_at: str
    live_check_passed: bool | None
    hermes_version: str | None
    ready: bool
