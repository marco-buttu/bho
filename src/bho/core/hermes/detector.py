"""Detect the local Hermes Agent installation without modifying it."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from bho.core.hermes.models import HermesCommandMetadata, HermesStatus
from bho.core.hermes.state import read_matching_managed_installation
from bho.core.hermes.version import parse_hermes_metadata

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
    bho_data_dir = data_dir or default_bho_data_dir(home, env)

    configuration_present = any(
        candidate.exists() for candidate in configuration_candidates(home, env)
    )
    executable = _find_executable(executable_name, home, env, which_fn)

    if executable is None:
        return HermesStatus(
            installed=False,
            executable=None,
            version=None,
            configuration_present=configuration_present,
            managed_by_bho=False,
            installer_source=None,
            hermes_install_method=None,
            install_directory=None,
        )

    metadata = _detect_metadata(executable, run_fn)
    marker = read_matching_managed_installation(
        bho_data_dir,
        executable=executable,
        version=metadata.version,
        install_directory=metadata.install_directory,
        hermes_install_method=metadata.install_method,
    )

    return HermesStatus(
        installed=True,
        executable=executable,
        version=metadata.version,
        configuration_present=configuration_present,
        managed_by_bho=marker is not None,
        installer_source=marker.installer_source if marker else None,
        hermes_install_method=metadata.install_method,
        install_directory=metadata.install_directory,
    )


def default_bho_data_dir(home: Path, environment: Mapping[str, str]) -> Path:
    """Return the platform-neutral bho data directory used by this release."""
    xdg_data_home = environment.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "bho"
    return home / ".local" / "share" / "bho"


def configuration_candidates(
    home: Path,
    environment: Mapping[str, str],
) -> tuple[Path, ...]:
    """Return known Hermes configuration and data locations."""
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


def _find_executable(
    executable_name: str,
    home: Path,
    environment: Mapping[str, str],
    which_fn: WhichFunction,
) -> Path | None:
    executable_value = which_fn(executable_name)
    if executable_value:
        candidate = Path(executable_value).expanduser()
        if candidate.is_file():
            return candidate.absolute()

    hermes_home = Path(environment.get("HERMES_HOME", home / ".hermes")).expanduser()
    fallback_candidates = (
        home / ".local" / "bin" / executable_name,
        hermes_home / "hermes-agent" / "venv" / "bin" / executable_name,
        Path("/usr/local/bin") / executable_name,
    )
    for candidate in fallback_candidates:
        if candidate.is_file():
            return candidate.absolute()
    return None


def _detect_metadata(
    executable: Path,
    run_fn: RunFunction,
) -> HermesCommandMetadata:
    for arguments in (
        [str(executable), "version"],
        [str(executable), "--version"],
    ):
        try:
            result = run_fn(
                arguments,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue

        if result.returncode != 0:
            continue

        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        metadata = parse_hermes_metadata(output)
        if metadata.version or metadata.install_directory or metadata.install_method:
            return metadata

    return HermesCommandMetadata()
