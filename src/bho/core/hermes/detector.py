"""Detect the local Hermes Agent installation without modifying it."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from bho.core.hermes.models import HermesStatus

MANAGED_INSTALLATION_MARKER = Path("hermes") / "managed.json"
_VERSION_PATTERN = re.compile(
    r"\b\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?\b"
)

WhichFunction = Callable[[str], str | None]
RunFunction = Callable[..., subprocess.CompletedProcess[str]]


def detect_hermes_status(
    *,
    executable_name: str = "hermes",
    home_dir: Path | None = None,
    data_dir: Path | None = None,
    environment: Mapping[str, str] | None = None,
    which_fn: WhichFunction = shutil.which,
    run_fn: RunFunction = subprocess.run,
) -> HermesStatus:
    """Return the current local Hermes Agent status."""
    env = dict(os.environ if environment is None else environment)
    home = (home_dir or Path.home()).expanduser()
    bho_data_dir = data_dir or _default_bho_data_dir(home, env)

    executable_value = which_fn(executable_name)
    executable = (
        Path(executable_value).expanduser().resolve(strict=False)
        if executable_value
        else None
    )

    configuration_present = any(
        candidate.exists() for candidate in _configuration_candidates(home, env)
    )
    managed_by_bho = (bho_data_dir / MANAGED_INSTALLATION_MARKER).is_file()

    if executable is None:
        return HermesStatus(
            installed=False,
            executable=None,
            version=None,
            configuration_present=configuration_present,
            managed_by_bho=managed_by_bho,
        )

    return HermesStatus(
        installed=True,
        executable=executable,
        version=_detect_version(executable, run_fn),
        configuration_present=configuration_present,
        managed_by_bho=managed_by_bho,
    )


def _default_bho_data_dir(home: Path, environment: Mapping[str, str]) -> Path:
    xdg_data_home = environment.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "bho"
    return home / ".local" / "share" / "bho"


def _configuration_candidates(
    home: Path,
    environment: Mapping[str, str],
) -> tuple[Path, ...]:
    candidates: list[Path] = []

    hermes_home = environment.get("HERMES_HOME")
    if hermes_home:
        candidates.append(Path(hermes_home).expanduser())

    candidates.extend(
        (
            home / ".hermes",
            home / ".config" / "hermes",
        )
    )
    return tuple(candidates)


def _detect_version(executable: Path, run_fn: RunFunction) -> str | None:
    try:
        result = run_fn(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")
    if not first_line:
        return None

    version_match = _VERSION_PATTERN.search(first_line)
    return version_match.group(0) if version_match else first_line
