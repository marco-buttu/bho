"""Data models for Docker host integration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DockerState(str, Enum):
    """Describe the actionable state of the local Docker installation."""

    READY = "ready"
    NOT_INSTALLED = "not_installed"
    DAEMON_STOPPED = "daemon_stopped"
    PERMISSION_DENIED = "permission_denied"
    SESSION_REFRESH_REQUIRED = "session_refresh_required"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DockerHostStatus:
    """Describe Docker availability for the current user and session."""

    state: DockerState
    executable: Path | None
    detail: str | None = None
    current_user: str | None = None
    docker_group_exists: bool = False
    user_configured_for_group: bool = False
    group_active_in_session: bool = False

    @property
    def ready(self) -> bool:
        """Return whether Docker can be used without elevated privileges."""
        return self.state is DockerState.READY


@dataclass(frozen=True, slots=True)
class LinuxDistribution:
    """Describe the detected Linux distribution and package support."""

    distribution_id: str
    name: str
    id_like: tuple[str, ...]
    package_manager: str | None

    @property
    def apt_supported(self) -> bool:
        """Return whether bho supports guided apt installation on this host."""
        families = {self.distribution_id, *self.id_like}
        return self.package_manager == "apt-get" and bool(
            families.intersection({"debian", "ubuntu", "linuxmint"})
        )
