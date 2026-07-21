"""Tests for Hermes Agent installation."""

import json
import subprocess
from pathlib import Path

import pytest

from bho.core.hermes.errors import HermesOperationError
from bho.core.hermes.installer import install_hermes
from bho.core.hermes.models import HermesStatus


def test_successful_install_creates_management_marker(tmp_path: Path) -> None:
    """A verified installation should be recorded as managed by bho."""
    data_dir = tmp_path / "bho-data"
    executable = tmp_path / ".local" / "bin" / "hermes"
    installed = False

    def fake_detect(**kwargs: object) -> HermesStatus:
        marker = data_dir / "hermes" / "managed.json"
        return HermesStatus(
            installed=installed,
            executable=executable if installed else None,
            version="0.18.2" if installed else None,
            configuration_present=installed,
            managed_by_bho=marker.is_file(),
            installation_method="official-user-installer" if installed else None,
        )

    def fake_download(url: str, destination: Path) -> None:
        destination.write_text("#!/bin/bash\n", encoding="utf-8")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal installed
        installed = True
        executable.parent.mkdir(parents=True)
        executable.touch()
        return subprocess.CompletedProcess(args=args, returncode=0)

    result = install_hermes(
        home_dir=tmp_path,
        data_dir=data_dir,
        environment={},
        detect_fn=fake_detect,
        run_fn=fake_run,
        download_fn=fake_download,
    )

    marker = data_dir / "hermes" / "managed.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert result.installed_now is True
    assert result.status.managed_by_bho is True
    assert payload["executable"] == str(executable)
    assert payload["version"] == "0.18.2"


def test_already_installed_is_not_reinstalled(tmp_path: Path) -> None:
    """An existing installation should be returned without executing an installer."""
    status = HermesStatus(
        installed=True,
        executable=tmp_path / "hermes",
        version="0.18.2",
        configuration_present=True,
        managed_by_bho=False,
        installation_method="official-user-installer",
    )

    def fail_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("Installer should not run.")

    result = install_hermes(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        detect_fn=lambda **kwargs: status,
        run_fn=fail_run,
    )

    assert result.installed_now is False
    assert result.status == status


def test_installer_command_failure_is_reported(tmp_path: Path) -> None:
    """A non-zero official installer result should fail the operation."""
    missing = HermesStatus(False, None, None, False, False, None)

    def fake_download(url: str, destination: Path) -> None:
        destination.write_text("#!/bin/bash\n", encoding="utf-8")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=7)

    with pytest.raises(HermesOperationError, match="exit code 7"):
        install_hermes(
            home_dir=tmp_path,
            data_dir=tmp_path / "bho-data",
            environment={},
            detect_fn=lambda **kwargs: missing,
            run_fn=fake_run,
            download_fn=fake_download,
        )


def test_installation_verification_failure_is_reported(tmp_path: Path) -> None:
    """A successful script exit without a detectable executable should fail."""
    missing = HermesStatus(False, None, None, False, False, None)

    def fake_download(url: str, destination: Path) -> None:
        destination.write_text("#!/bin/bash\n", encoding="utf-8")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=0)

    with pytest.raises(HermesOperationError, match="could not be verified"):
        install_hermes(
            home_dir=tmp_path,
            data_dir=tmp_path / "bho-data",
            environment={},
            detect_fn=lambda **kwargs: missing,
            run_fn=fake_run,
            download_fn=fake_download,
        )
