"""Detect Docker installation, daemon, and permission state."""

from __future__ import annotations

import getpass
import grp
import os
import pwd
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from bho.core.docker.models import DockerHostStatus, DockerState, LinuxDistribution

RunFunction = Callable[..., subprocess.CompletedProcess[str]]
WhichFunction = Callable[[str], str | None]

_PERMISSION_TERMS = (
    "permission denied",
    "got permission denied",
    "access denied",
)
_DAEMON_TERMS = (
    "cannot connect to the docker daemon",
    "is the docker daemon running",
    "connection refused",
    "failed to connect to the docker api",
    "error during connect",
)


def detect_docker_status(
    *,
    environment: Mapping[str, str] | None = None,
    which_fn: WhichFunction = shutil.which,
    run_fn: RunFunction = subprocess.run,
    current_user: str | None = None,
    active_group_ids: Sequence[int] | None = None,
) -> DockerHostStatus:
    """Return an actionable Docker state for the current user session."""
    executable_value = which_fn("docker")
    user = current_user or _current_user()
    group_state = _docker_group_state(user, active_group_ids)

    if not executable_value:
        return DockerHostStatus(
            state=DockerState.NOT_INSTALLED,
            executable=None,
            detail="Docker executable not found.",
            current_user=user,
            **group_state,
        )

    executable = Path(executable_value).expanduser().absolute()
    try:
        result = run_fn(
            [str(executable), "info"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=dict(environment) if environment is not None else None,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return DockerHostStatus(
            state=DockerState.ERROR,
            executable=executable,
            detail=str(error),
            current_user=user,
            **group_state,
        )

    if result.returncode == 0:
        return DockerHostStatus(
            state=DockerState.READY,
            executable=executable,
            current_user=user,
            **group_state,
        )

    detail = _safe_detail(result.stdout, result.stderr)
    lowered = detail.lower() if detail else ""
    if any(term in lowered for term in _PERMISSION_TERMS):
        state = (
            DockerState.SESSION_REFRESH_REQUIRED
            if group_state["user_configured_for_group"]
            and not group_state["group_active_in_session"]
            else DockerState.PERMISSION_DENIED
        )
    elif any(term in lowered for term in _DAEMON_TERMS):
        state = DockerState.DAEMON_STOPPED
    else:
        state = DockerState.ERROR

    return DockerHostStatus(
        state=state,
        executable=executable,
        detail=detail or "Docker daemon is unavailable.",
        current_user=user,
        **group_state,
    )


def detect_linux_distribution(
    *,
    os_release_path: Path = Path("/etc/os-release"),
    which_fn: WhichFunction = shutil.which,
) -> LinuxDistribution:
    """Detect Linux distribution metadata needed for guided installation."""
    values: dict[str, str] = {}
    try:
        for raw_line in os_release_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"').strip("'")
    except OSError:
        pass

    distribution_id = values.get("ID", "unknown").lower()
    name = values.get("PRETTY_NAME") or values.get("NAME") or distribution_id
    id_like = tuple(
        item.lower() for item in values.get("ID_LIKE", "").split() if item
    )
    package_manager = "apt-get" if which_fn("apt-get") else None
    return LinuxDistribution(
        distribution_id=distribution_id,
        name=name,
        id_like=id_like,
        package_manager=package_manager,
    )


def _current_user() -> str:
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except (KeyError, OSError):
        return getpass.getuser()


def _docker_group_state(
    user: str,
    active_group_ids: Sequence[int] | None,
) -> dict[str, bool]:
    try:
        docker_group = grp.getgrnam("docker")
    except KeyError:
        return {
            "docker_group_exists": False,
            "user_configured_for_group": False,
            "group_active_in_session": False,
        }

    try:
        user_entry = pwd.getpwnam(user)
        primary_group_id = user_entry.pw_gid
    except KeyError:
        primary_group_id = -1

    group_ids = set(os.getgroups() if active_group_ids is None else active_group_ids)
    group_ids.add(os.getegid())
    configured = user in docker_group.gr_mem or primary_group_id == docker_group.gr_gid
    active = docker_group.gr_gid in group_ids
    return {
        "docker_group_exists": True,
        "user_configured_for_group": configured,
        "group_active_in_session": active,
    }


def _safe_detail(stdout: str, stderr: str) -> str | None:
    lines = [
        line.strip()
        for line in "\n".join((stdout or "", stderr or "")).splitlines()
        if line.strip()
    ]
    return lines[-1][:500] if lines else None
