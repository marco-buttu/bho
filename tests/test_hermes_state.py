"""Tests for bho Hermes management markers."""

import json
from pathlib import Path

from bho.core.hermes.models import HermesStatus
from bho.core.hermes.state import (
    is_managed_installation,
    read_matching_managed_installation,
    write_managed_installation,
)


def _status(tmp_path: Path) -> HermesStatus:
    return HermesStatus(
        installed=True,
        executable=tmp_path / ".local" / "bin" / "hermes",
        version="0.19.0",
        configuration_present=True,
        managed_by_bho=False,
        hermes_install_method="git",
        install_directory=tmp_path / ".hermes" / "hermes-agent",
    )


def test_marker_records_management_metadata(tmp_path: Path) -> None:
    """A marker should record enough metadata to validate the installation."""
    data_dir = tmp_path / "bho-data"
    status = _status(tmp_path)

    write_managed_installation(
        data_dir,
        status,
        installer_source="official-user-installer",
    )

    payload = json.loads(
        (data_dir / "hermes" / "managed.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == 1
    assert payload["executable"] == str(status.executable)
    assert payload["version"] == "0.19.0"
    assert payload["install_directory"] == str(status.install_directory)
    assert payload["installer_source"] == "official-user-installer"
    assert payload["hermes_install_method"] == "git"
    assert payload["installed_at"]


def test_matching_marker_is_recognized(tmp_path: Path) -> None:
    """A marker should match the installation it recorded."""
    data_dir = tmp_path / "bho-data"
    status = _status(tmp_path)
    write_managed_installation(
        data_dir,
        status,
        installer_source="official-user-installer",
    )

    record = read_matching_managed_installation(
        data_dir,
        executable=status.executable,
        version=status.version,
        install_directory=status.install_directory,
        hermes_install_method=status.hermes_install_method,
    )

    assert record is not None
    assert record.installer_source == "official-user-installer"
    assert is_managed_installation(
        data_dir,
        status.executable,
        version=status.version,
        install_directory=status.install_directory,
        hermes_install_method=status.hermes_install_method,
    )


def test_changed_version_invalidates_marker(tmp_path: Path) -> None:
    """A marker should not claim a replacement installation as managed."""
    data_dir = tmp_path / "bho-data"
    status = _status(tmp_path)
    write_managed_installation(
        data_dir,
        status,
        installer_source="official-user-installer",
    )

    assert not is_managed_installation(
        data_dir,
        status.executable,
        version="0.20.0",
        install_directory=status.install_directory,
        hermes_install_method=status.hermes_install_method,
    )


def test_corrupt_marker_is_ignored(tmp_path: Path) -> None:
    """A corrupt marker must not produce a false managed state."""
    data_dir = tmp_path / "bho-data"
    marker = data_dir / "hermes" / "managed.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("not-json", encoding="utf-8")

    assert not is_managed_installation(
        data_dir,
        tmp_path / "hermes",
        version="0.19.0",
    )
