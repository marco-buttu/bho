"""Install Hermes Agent using the official installer."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from bho.core.hermes.detector import default_bho_data_dir, detect_hermes_status
from bho.core.hermes.errors import (
    HermesOperationError,
    HermesPartialInstallationError,
)
from bho.core.hermes.models import HermesInstallResult, HermesStatus
from bho.core.hermes.state import (
    remove_managed_installation,
    write_managed_installation,
)

OFFICIAL_INSTALL_SCRIPT_URL = "https://hermes-agent.nousresearch.com/install.sh"
OFFICIAL_INSTALLER_SOURCE = "official-user-installer"
DEFAULT_INSTALL_TIMEOUT_SECONDS = 30 * 60
_MAX_INSTALLER_SIZE = 5 * 1024 * 1024
_PROCESS_TERMINATION_TIMEOUT_SECONDS = 5

DetectFunction = Callable[..., HermesStatus]
DownloadFunction = Callable[[str, Path], None]


class InstallerProcess(Protocol):
    """Describe the subprocess operations used by the installer runner."""

    pid: int
    returncode: int | None

    def communicate(self, timeout: float | None = None) -> tuple[str, str]: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


ProcessFactory = Callable[..., InstallerProcess]


def install_hermes(
    *,
    home_dir: Path | None = None,
    data_dir: Path | None = None,
    environment: Mapping[str, str] | None = None,
    detect_fn: DetectFunction = detect_hermes_status,
    process_factory: ProcessFactory = subprocess.Popen,
    download_fn: DownloadFunction | None = None,
    timeout_seconds: float = DEFAULT_INSTALL_TIMEOUT_SECONDS,
) -> HermesInstallResult:
    """Install Hermes non-interactively and reconcile the final state."""
    env = dict(os.environ if environment is None else environment)
    home = (home_dir or Path.home()).expanduser()
    env.setdefault("HOME", str(home))
    bho_data_dir = data_dir or default_bho_data_dir(home, env)

    before = detect_fn(home_dir=home, data_dir=bho_data_dir, environment=env)
    if before.installed:
        return HermesInstallResult(status=before, installed_now=False)

    remove_managed_installation(bho_data_dir)

    bash = shutil.which("bash")
    if os.name != "posix" or bash is None:
        raise HermesOperationError(
            "This bho release supports automatic Hermes installation only on "
            "POSIX systems with bash."
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

        arguments = [
            bash,
            str(script_path),
            "--skip-setup",
            "--non-interactive",
        ]
        try:
            result = _run_installer_process(
                arguments,
                environment=env,
                timeout_seconds=timeout_seconds,
                process_factory=process_factory,
            )
        except subprocess.TimeoutExpired as error:
            after = _detect_after_operation(detect_fn, home, bho_data_dir, env)
            _raise_incomplete_installation(
                after,
                "Hermes installation did not complete within the allowed time.",
                error,
            )
        except KeyboardInterrupt as error:
            after = _detect_after_operation(detect_fn, home, bho_data_dir, env)
            _raise_incomplete_installation(
                after,
                "Hermes installation was interrupted.",
                error,
            )
        except OSError as error:
            after = _detect_after_operation(detect_fn, home, bho_data_dir, env)
            _raise_incomplete_installation(
                after,
                f"Could not start the official Hermes installer: {error}",
                error,
            )

    after = _detect_after_operation(detect_fn, home, bho_data_dir, env)

    if result.returncode != 0:
        detail = _safe_output_detail(result.stdout, result.stderr)
        message = (
            "The official Hermes installer failed with exit code "
            f"{result.returncode}."
        )
        if detail:
            message = f"{message} Last installer output: {detail}"
        _raise_incomplete_installation(after, message)

    if not after.installed or after.executable is None:
        raise HermesOperationError(
            "Hermes installation completed, but the executable could not be verified."
        )

    write_managed_installation(
        bho_data_dir,
        after,
        installer_source=OFFICIAL_INSTALLER_SOURCE,
    )
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


def _run_installer_process(
    arguments: list[str],
    *,
    environment: Mapping[str, str],
    timeout_seconds: float,
    process_factory: ProcessFactory,
) -> subprocess.CompletedProcess[str]:
    process = process_factory(
        arguments,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(environment),
        start_new_session=True,
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process(process)
        process.communicate()
        raise
    except KeyboardInterrupt:
        _terminate_process(process)
        process.communicate()
        raise

    return subprocess.CompletedProcess(
        args=arguments,
        returncode=process.returncode if process.returncode is not None else -1,
        stdout=stdout,
        stderr=stderr,
    )


def _terminate_process(process: InstallerProcess) -> None:
    _send_process_signal(process, signal.SIGTERM)

    try:
        process.wait(timeout=_PROCESS_TERMINATION_TIMEOUT_SECONDS)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    _send_process_signal(process, signal.SIGKILL)
    try:
        process.wait()
    except OSError:
        pass


def _send_process_signal(process: InstallerProcess, signal_number: signal.Signals) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal_number)
            return
        except (OSError, ProcessLookupError, PermissionError):
            pass

    try:
        if signal_number == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
    except OSError:
        pass


def _detect_after_operation(
    detect_fn: DetectFunction,
    home: Path,
    data_dir: Path,
    environment: Mapping[str, str],
) -> HermesStatus:
    return detect_fn(
        home_dir=home,
        data_dir=data_dir,
        environment=environment,
    )


def _raise_incomplete_installation(
    status: HermesStatus,
    message: str,
    cause: BaseException | None = None,
) -> None:
    if status.installed:
        error: HermesOperationError = HermesPartialInstallationError(
            f"{message} Hermes is now detected, but the installation was not "
            "recorded as managed by bho.",
            status,
        )
    else:
        error = HermesOperationError(message)

    if cause is None:
        raise error
    raise error from cause


def _safe_output_detail(stdout: str, stderr: str) -> str | None:
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
    if not safe_lines:
        return None
    return " | ".join(safe_lines[-3:])[:500]
