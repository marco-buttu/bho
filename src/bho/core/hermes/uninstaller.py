"""Uninstall Hermes Agent while preserving user data by default."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from bho.core.hermes.detector import default_bho_data_dir, detect_hermes_status
from bho.core.hermes.errors import HermesOperationError
from bho.core.hermes.models import HermesStatus, HermesUninstallResult
from bho.core.hermes.state import remove_managed_installation

RunFunction = Callable[..., subprocess.CompletedProcess[str]]
DetectFunction = Callable[..., HermesStatus]

_SUPPORTED_UNINSTALL_METHODS = {
    "official-user-installer",
    "official-root-installer",
    "pip",
    "homebrew",
    "nix",
}


def uninstall_hermes(
    *,
    home_dir: Path | None = None,
    data_dir: Path | None = None,
    environment: Mapping[str, str] | None = None,
    detect_fn: DetectFunction = detect_hermes_status,
    run_fn: RunFunction = subprocess.run,
) -> HermesUninstallResult:
    """Run Hermes own uninstaller without deleting configuration or user data."""
    env = dict(os.environ if environment is None else environment)
    home = (home_dir or Path.home()).expanduser()
    bho_data_dir = data_dir or default_bho_data_dir(home, env)

    before = detect_fn(home_dir=home, data_dir=bho_data_dir, environment=env)
    if not before.installed or before.executable is None:
        remove_managed_installation(bho_data_dir)
        return HermesUninstallResult(
            uninstalled_now=False,
            already_absent=True,
            data_preserved=True,
        )

    if (
        not before.managed_by_bho
        and before.installation_method not in _SUPPORTED_UNINSTALL_METHODS
    ):
        raise HermesOperationError(
            "The Hermes installation method could not be identified safely. "
            "Automatic uninstall was refused."
        )

    try:
        result = run_fn(
            [str(before.executable), "uninstall", "--yes"],
            check=False,
            env=env,
        )
    except OSError as error:
        raise HermesOperationError(f"Could not start the Hermes uninstaller: {error}") from error

    if result.returncode != 0:
        raise HermesOperationError(
            f"The Hermes uninstaller failed with exit code {result.returncode}."
        )

    after = detect_fn(home_dir=home, data_dir=bho_data_dir, environment=env)
    if after.installed:
        raise HermesOperationError(
            "Hermes reported a successful uninstall, but an executable is still detected."
        )

    remove_managed_installation(bho_data_dir)
    return HermesUninstallResult(
        uninstalled_now=True,
        already_absent=False,
        data_preserved=True,
    )
