"""Install Hermes Agent using the official installer."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

from bho.core.hermes.detector import default_bho_data_dir, detect_hermes_status
from bho.core.hermes.errors import HermesOperationError
from bho.core.hermes.models import HermesInstallResult, HermesStatus
from bho.core.hermes.state import write_managed_installation

OFFICIAL_INSTALL_SCRIPT_URL = "https://hermes-agent.nousresearch.com/install.sh"
_MAX_INSTALLER_SIZE = 5 * 1024 * 1024

RunFunction = Callable[..., subprocess.CompletedProcess[str]]
DetectFunction = Callable[..., HermesStatus]
DownloadFunction = Callable[[str, Path], None]


def install_hermes(
    *,
    home_dir: Path | None = None,
    data_dir: Path | None = None,
    environment: Mapping[str, str] | None = None,
    detect_fn: DetectFunction = detect_hermes_status,
    run_fn: RunFunction = subprocess.run,
    download_fn: DownloadFunction | None = None,
) -> HermesInstallResult:
    """Install Hermes with its official POSIX installer and verify the result."""
    env = dict(os.environ if environment is None else environment)
    home = (home_dir or Path.home()).expanduser()
    bho_data_dir = data_dir or default_bho_data_dir(home, env)

    before = detect_fn(home_dir=home, data_dir=bho_data_dir, environment=env)
    if before.installed:
        return HermesInstallResult(status=before, installed_now=False)

    bash = shutil.which("bash")
    if os.name != "posix" or bash is None:
        raise HermesOperationError(
            "This bho release supports automatic Hermes installation only on POSIX systems with bash."
        )

    downloader = download_fn or download_official_installer
    with tempfile.TemporaryDirectory(prefix="bho-hermes-") as temporary_dir:
        script_path = Path(temporary_dir) / "install.sh"
        try:
            downloader(OFFICIAL_INSTALL_SCRIPT_URL, script_path)
        except (OSError, ValueError) as error:
            raise HermesOperationError(
                f"Could not download the official Hermes installer: {error}"
            ) from error

        try:
            result = run_fn(
                [bash, str(script_path), "--skip-setup"],
                check=False,
                env=env,
            )
        except OSError as error:
            raise HermesOperationError(
                f"Could not start the official Hermes installer: {error}"
            ) from error

    if result.returncode != 0:
        raise HermesOperationError(
            f"The official Hermes installer failed with exit code {result.returncode}."
        )

    after = detect_fn(home_dir=home, data_dir=bho_data_dir, environment=env)
    if not after.installed or after.executable is None:
        raise HermesOperationError(
            "Hermes installation completed, but the executable could not be verified."
        )

    write_managed_installation(bho_data_dir, after)
    verified = detect_fn(home_dir=home, data_dir=bho_data_dir, environment=env)
    if not verified.managed_by_bho:
        raise HermesOperationError(
            "Hermes was installed, but bho could not record the managed installation."
        )

    return HermesInstallResult(status=verified, installed_now=True)


def download_official_installer(url: str, destination: Path) -> None:
    """Download and minimally validate the official Hermes installer script."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "bho-hermes-installer"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read(_MAX_INSTALLER_SIZE + 1)

    if len(content) > _MAX_INSTALLER_SIZE:
        raise ValueError("Installer response exceeds the maximum allowed size.")
    if not content.startswith(b"#!/bin/bash"):
        raise ValueError("Downloaded content is not the expected Bash installer.")

    destination.write_bytes(content)
