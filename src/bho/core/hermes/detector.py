"""Detect the local Hermes Agent installation without modifying it."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from bho.core.hermes.models import HermesStatus
from bho.core.hermes.state import is_managed_installation
from bho.core.hermes.version import parse_hermes_version

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

    executable = _find_executable(executable_name, home, env, which_fn)
    configuration_present = any(
        candidate.exists() for candidate in configuration_candidates(home, env)
    )
    managed_by_bho = is_managed_installation(bho_data_dir, executable)

    if executable is None:
        return HermesStatus(
            installed=False,
            executable=None,
            version=None,
            configuration_present=configuration_present,
            managed_by_bho=False,
            installation_method=None,
        )

    return HermesStatus(
        installed=True,
        executable=executable,
        version=_detect_version(executable, run_fn),
        configuration_present=configuration_present,
        managed_by_bho=managed_by_bho,
        installation_method=detect_installation_method(executable, home, env),
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


def detect_installation_method(
    executable: Path,
    home: Path,
    environment: Mapping[str, str],
) -> str:
    """Identify supported Hermes installation layouts conservatively."""
    resolved = executable.expanduser().resolve(strict=False)
    hermes_home = Path(environment.get("HERMES_HOME", home / ".hermes")).expanduser()
    user_repo = (hermes_home / "hermes-agent").resolve(strict=False)

    if _is_within(resolved, user_repo) or (
        executable.expanduser() == home / ".local" / "bin" / "hermes"
        and user_repo.exists()
    ):
        return "official-user-installer"

    root_repo = Path("/usr/local/lib/hermes-agent")
    if _is_within(resolved, root_repo) or (
        executable == Path("/usr/local/bin/hermes") and root_repo.exists()
    ):
        return "official-root-installer"

    executable_text = str(resolved)
    if "/Cellar/" in executable_text or executable_text.startswith("/opt/homebrew/"):
        return "homebrew"
    if executable_text.startswith("/nix/store/"):
        return "nix"
    if "site-packages" in executable_text or "dist-packages" in executable_text:
        return "pip"

    return "unknown"


def _find_executable(
    executable_name: str,
    home: Path,
    environment: Mapping[str, str],
    which_fn: WhichFunction,
) -> Path | None:
    executable_value = which_fn(executable_name)
    if executable_value:
        return Path(executable_value).expanduser().resolve(strict=False)

    hermes_home = Path(environment.get("HERMES_HOME", home / ".hermes")).expanduser()
    fallback_candidates = (
        home / ".local" / "bin" / executable_name,
        hermes_home / "hermes-agent" / "venv" / "bin" / executable_name,
        Path("/usr/local/bin") / executable_name,
    )
    for candidate in fallback_candidates:
        if candidate.is_file():
            return candidate.resolve(strict=False)
    return None


def _detect_version(executable: Path, run_fn: RunFunction) -> str | None:
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
        version = parse_hermes_version(output)
        if version:
            return version

    return None


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True
