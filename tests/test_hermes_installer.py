"""Tests for Hermes Agent installation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from bho.core.hermes.errors import (
    HermesOperationError,
    HermesPartialInstallationError,
)
from bho.core.hermes.installer import install_hermes
from bho.core.hermes.models import HermesStatus


class FakeProcess:
    """Controllable installer process for unit tests."""

    pid = 999_999_999

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        first_exception: BaseException | None = None,
    ) -> None:
        self.returncode: int | None = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.first_exception = first_exception
        self.communicate_calls = 0
        self.terminated = False
        self.killed = False

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self.communicate_calls += 1
        if self.communicate_calls == 1 and self.first_exception is not None:
            raise self.first_exception
        return self.stdout, self.stderr

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0


def _missing_status(*, configuration: bool = False) -> HermesStatus:
    return HermesStatus(
        installed=False,
        executable=None,
        version=None,
        configuration_present=configuration,
        managed_by_bho=False,
    )


def _installed_status(
    executable: Path,
    install_directory: Path,
    *,
    managed: bool = False,
) -> HermesStatus:
    return HermesStatus(
        installed=True,
        executable=executable,
        version="0.19.0",
        configuration_present=True,
        managed_by_bho=managed,
        installer_source="official-user-installer" if managed else None,
        hermes_install_method="git",
        install_directory=install_directory,
    )


def _fake_download(url: str, destination: Path) -> None:
    destination.write_text("#!/bin/bash\n", encoding="utf-8")


def test_successful_install_is_non_interactive_and_creates_marker(
    tmp_path: Path,
) -> None:
    """A successful install should skip interactive stages and be recorded."""
    data_dir = tmp_path / "bho-data"
    executable = tmp_path / ".local" / "bin" / "hermes"
    install_directory = tmp_path / ".hermes" / "hermes-agent"
    process = FakeProcess()
    process_call: dict[str, Any] = {}
    installed = False

    def fake_detect(**kwargs: object) -> HermesStatus:
        marker = data_dir / "hermes" / "managed.json"
        if not installed:
            return _missing_status(configuration=True)
        return _installed_status(
            executable,
            install_directory,
            managed=marker.is_file(),
        )

    def fake_factory(arguments: list[str], **kwargs: object) -> FakeProcess:
        nonlocal installed
        process_call["arguments"] = arguments
        process_call["kwargs"] = kwargs
        installed = True
        executable.parent.mkdir(parents=True)
        executable.touch()
        install_directory.mkdir(parents=True)
        return process

    result = install_hermes(
        home_dir=tmp_path,
        data_dir=data_dir,
        environment={},
        detect_fn=fake_detect,
        process_factory=fake_factory,
        download_fn=_fake_download,
    )

    arguments = process_call["arguments"]
    kwargs = process_call["kwargs"]
    assert arguments[-2:] == ["--skip-setup", "--non-interactive"]
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.PIPE
    assert kwargs["start_new_session"] is True
    assert "shell" not in kwargs

    marker = data_dir / "hermes" / "managed.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert result.installed_now is True
    assert result.status.managed_by_bho is True
    assert payload["executable"] == str(executable)
    assert payload["version"] == "0.19.0"
    assert payload["install_directory"] == str(install_directory)
    assert payload["installer_source"] == "official-user-installer"
    assert payload["hermes_install_method"] == "git"


def test_already_installed_is_not_reinstalled(tmp_path: Path) -> None:
    """An existing installation should be returned without executing an installer."""
    status = _installed_status(
        tmp_path / "hermes",
        tmp_path / ".hermes" / "hermes-agent",
    )

    def fail_factory(*args: object, **kwargs: object) -> FakeProcess:
        raise AssertionError("Installer should not run.")

    result = install_hermes(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        detect_fn=lambda **kwargs: status,
        process_factory=fail_factory,
    )

    assert result.installed_now is False
    assert result.status == status


def test_installer_command_failure_is_reported(tmp_path: Path) -> None:
    """A non-zero result with no installation should fail normally."""
    process = FakeProcess(returncode=7, stderr="installer error")

    with pytest.raises(HermesOperationError, match="exit code 7"):
        install_hermes(
            home_dir=tmp_path,
            data_dir=tmp_path / "bho-data",
            environment={},
            detect_fn=lambda **kwargs: _missing_status(),
            process_factory=lambda *args, **kwargs: process,
            download_fn=_fake_download,
        )


def test_failed_installer_that_created_hermes_is_partial(tmp_path: Path) -> None:
    """A failed process followed by a detected install should not create a marker."""
    data_dir = tmp_path / "bho-data"
    executable = tmp_path / ".local" / "bin" / "hermes"
    install_directory = tmp_path / ".hermes" / "hermes-agent"
    process = FakeProcess(returncode=9)
    calls = 0

    def fake_detect(**kwargs: object) -> HermesStatus:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _missing_status()
        return _installed_status(executable, install_directory)

    with pytest.raises(HermesPartialInstallationError) as captured:
        install_hermes(
            home_dir=tmp_path,
            data_dir=data_dir,
            environment={},
            detect_fn=fake_detect,
            process_factory=lambda *args, **kwargs: process,
            download_fn=_fake_download,
        )

    assert captured.value.status.installed is True
    assert captured.value.status.managed_by_bho is False
    assert not (data_dir / "hermes" / "managed.json").exists()


def test_installation_verification_failure_is_reported(tmp_path: Path) -> None:
    """A successful script exit without a detectable executable should fail."""
    with pytest.raises(HermesOperationError, match="could not be verified"):
        install_hermes(
            home_dir=tmp_path,
            data_dir=tmp_path / "bho-data",
            environment={},
            detect_fn=lambda **kwargs: _missing_status(),
            process_factory=lambda *args, **kwargs: FakeProcess(returncode=0),
            download_fn=_fake_download,
        )


def test_timeout_terminates_process_and_reconciles_absent_state(tmp_path: Path) -> None:
    """A timed-out installer should be terminated and leave no false marker."""
    process = FakeProcess(
        first_exception=subprocess.TimeoutExpired(cmd="install.sh", timeout=1)
    )
    data_dir = tmp_path / "bho-data"

    with pytest.raises(HermesOperationError, match="allowed time"):
        install_hermes(
            home_dir=tmp_path,
            data_dir=data_dir,
            environment={},
            detect_fn=lambda **kwargs: _missing_status(),
            process_factory=lambda *args, **kwargs: process,
            download_fn=_fake_download,
            timeout_seconds=1,
        )

    assert process.terminated is True
    assert process.communicate_calls == 2
    assert not (data_dir / "hermes" / "managed.json").exists()


def test_timeout_with_detected_install_is_reported_as_partial(tmp_path: Path) -> None:
    """A timed-out process that installed Hermes should be reconciled explicitly."""
    process = FakeProcess(
        first_exception=subprocess.TimeoutExpired(cmd="install.sh", timeout=1)
    )
    data_dir = tmp_path / "bho-data"
    executable = tmp_path / ".local" / "bin" / "hermes"
    install_directory = tmp_path / ".hermes" / "hermes-agent"
    calls = 0

    def fake_detect(**kwargs: object) -> HermesStatus:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _missing_status()
        return _installed_status(executable, install_directory)

    with pytest.raises(HermesPartialInstallationError, match="allowed time"):
        install_hermes(
            home_dir=tmp_path,
            data_dir=data_dir,
            environment={},
            detect_fn=fake_detect,
            process_factory=lambda *args, **kwargs: process,
            download_fn=_fake_download,
            timeout_seconds=1,
        )

    assert not (data_dir / "hermes" / "managed.json").exists()


def test_keyboard_interrupt_terminates_process_and_reconciles(tmp_path: Path) -> None:
    """Ctrl+C should terminate the installer and re-run detection."""
    process = FakeProcess(first_exception=KeyboardInterrupt())
    calls = 0

    def fake_detect(**kwargs: object) -> HermesStatus:
        nonlocal calls
        calls += 1
        return _missing_status()

    with pytest.raises(HermesOperationError, match="interrupted"):
        install_hermes(
            home_dir=tmp_path,
            data_dir=tmp_path / "bho-data",
            environment={},
            detect_fn=fake_detect,
            process_factory=lambda *args, **kwargs: process,
            download_fn=_fake_download,
        )

    assert process.terminated is True
    assert calls == 2


def test_sensitive_installer_output_is_not_in_error(tmp_path: Path) -> None:
    """Installer failures should not echo lines that may contain credentials."""
    process = FakeProcess(
        returncode=4,
        stdout="progress line\nAPI key: secret-value\n",
        stderr="failed safely\n",
    )

    with pytest.raises(HermesOperationError) as captured:
        install_hermes(
            home_dir=tmp_path,
            data_dir=tmp_path / "bho-data",
            environment={},
            detect_fn=lambda **kwargs: _missing_status(),
            process_factory=lambda *args, **kwargs: process,
            download_fn=_fake_download,
        )

    assert "secret-value" not in str(captured.value)
    assert "failed safely" in str(captured.value)


def test_stale_marker_is_removed_before_install_attempt(tmp_path: Path) -> None:
    """An absent installation should not retain a stale managed marker."""
    data_dir = tmp_path / "bho-data"
    marker = data_dir / "hermes" / "managed.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")

    with pytest.raises(HermesOperationError):
        install_hermes(
            home_dir=tmp_path,
            data_dir=data_dir,
            environment={},
            detect_fn=lambda **kwargs: _missing_status(),
            process_factory=lambda *args, **kwargs: FakeProcess(returncode=3),
            download_fn=_fake_download,
        )

    assert not marker.exists()
