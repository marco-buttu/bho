"""Configure and verify the Hermes Docker terminal backend."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from bho.core.docker.detector import detect_docker_status
from bho.core.docker.models import DockerState
from bho.core.hermes.errors import HermesConfigurationError
from bho.core.hermes.models import DockerAvailability

RunFunction = Callable[..., subprocess.CompletedProcess[str]]
WhichFunction = Callable[[str], str | None]

_DOCKER_SETTINGS = (
    ("terminal.backend", "docker"),
    ("terminal.docker_mount_cwd_to_workspace", "true"),
    ("terminal.docker_run_as_host_user", "true"),
    ("terminal.docker_forward_env", "[]"),
)


def check_docker_availability(
    *,
    environment: Mapping[str, str] | None = None,
    which_fn: WhichFunction = shutil.which,
    run_fn: RunFunction = subprocess.run,
) -> DockerAvailability:
    """Return whether Docker exists and the daemon is reachable."""
    status = detect_docker_status(
        environment=environment,
        which_fn=which_fn,
        run_fn=run_fn,
    )
    return DockerAvailability(
        executable=status.executable,
        daemon_available=status.state is DockerState.READY,
        detail=status.detail,
    )


def configure_docker_backend(
    executable: Path,
    profile_name: str,
    *,
    environment: Mapping[str, str] | None = None,
    run_fn: RunFunction = subprocess.run,
) -> None:
    """Apply the required Docker isolation settings to a Hermes profile."""
    for key, value in _DOCKER_SETTINGS:
        arguments = [
            str(executable),
            "-p",
            profile_name,
            "config",
            "set",
            key,
            value,
        ]
        try:
            result = run_fn(
                arguments,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=dict(environment) if environment is not None else None,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise HermesConfigurationError(
                f"Could not set Hermes configuration key '{key}': {error}",
                stage="Docker backend configuration",
                completed_stages=("profile available", "model configured"),
            ) from error

        if result.returncode != 0:
            detail = _safe_detail(result.stdout, result.stderr)
            message = f"Hermes does not support the required setting '{key}'."
            if detail:
                message = f"{message} {detail}"
            raise HermesConfigurationError(
                message,
                stage="Docker backend configuration",
                completed_stages=("profile available", "model configured"),
            )


def required_docker_settings() -> tuple[tuple[str, str], ...]:
    """Return the Docker settings enforced by bho."""
    return _DOCKER_SETTINGS


def _safe_detail(stdout: str, stderr: str) -> str | None:
    sensitive_terms = ("key", "token", "secret", "password", "credential")
    lines = [
        line.strip()
        for line in "\n".join((stdout or "", stderr or "")).splitlines()
        if line.strip()
    ]
    safe_lines = [
        line
        for line in lines
        if not any(term in line.lower() for term in sensitive_terms)
    ]
    return safe_lines[-1][:300] if safe_lines else None
