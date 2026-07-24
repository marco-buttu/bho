"""Manage the dedicated Hermes profile used by bho."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from bho.core.hermes.errors import HermesConfigurationError
from bho.core.hermes.models import HermesProfileResult

BHO_PROFILE_NAME = "bho"
_COMMAND_TIMEOUT_SECONDS = 30

RunFunction = Callable[..., subprocess.CompletedProcess[str]]


def ensure_bho_profile(
    executable: Path,
    *,
    environment: Mapping[str, str] | None = None,
    run_fn: RunFunction = subprocess.run,
) -> HermesProfileResult:
    """Create the blank bho profile when it does not already exist."""
    existing = inspect_profile(
        executable,
        BHO_PROFILE_NAME,
        environment=environment,
        run_fn=run_fn,
    )
    if existing is not None:
        return HermesProfileResult(
            name=BHO_PROFILE_NAME,
            path=existing,
            created=False,
        )

    arguments = [
        str(executable),
        "profile",
        "create",
        BHO_PROFILE_NAME,
        "--no-alias",
    ]
    try:
        result = run_fn(
            arguments,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
            check=False,
            env=dict(environment) if environment is not None else None,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise HermesConfigurationError(
            f"Could not create the Hermes profile '{BHO_PROFILE_NAME}': {error}",
            stage="profile creation",
        ) from error

    if result.returncode != 0:
        detail = _safe_detail(result.stdout, result.stderr)
        message = f"Hermes could not create the profile '{BHO_PROFILE_NAME}'."
        if detail:
            message = f"{message} {detail}"
        raise HermesConfigurationError(message, stage="profile creation")

    created_path = inspect_profile(
        executable,
        BHO_PROFILE_NAME,
        environment=environment,
        run_fn=run_fn,
    )
    if created_path is None:
        raise HermesConfigurationError(
            "Hermes reported profile creation success, but the bho profile "
            "could not be verified.",
            stage="profile verification",
            completed_stages=("profile created",),
        )

    return HermesProfileResult(
        name=BHO_PROFILE_NAME,
        path=created_path,
        created=True,
    )


def inspect_profile(
    executable: Path,
    profile_name: str,
    *,
    environment: Mapping[str, str] | None = None,
    run_fn: RunFunction = subprocess.run,
) -> Path | None:
    """Return a Hermes profile path when the profile exists."""
    arguments = [str(executable), "profile", "show", profile_name]
    try:
        result = run_fn(
            arguments,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
            check=False,
            env=dict(environment) if environment is not None else None,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == "path" and value.strip():
            return Path(value.strip()).expanduser()
    return None


def _safe_detail(stdout: str, stderr: str) -> str | None:
    lines = [
        line.strip()
        for line in "\n".join((stdout or "", stderr or "")).splitlines()
        if line.strip()
    ]
    return lines[-1][:300] if lines else None
