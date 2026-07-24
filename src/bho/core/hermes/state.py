"""Persist local state for the Hermes installation managed by bho."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bho.core.hermes.models import (
    HermesStatus,
    ManagedInstallationRecord,
)

MANAGED_INSTALLATION_MARKER = Path("hermes") / "managed.json"
_MARKER_SCHEMA_VERSION = 1


def managed_marker_path(data_dir: Path) -> Path:
    """Return the path of the bho Hermes management marker."""
    return data_dir / MANAGED_INSTALLATION_MARKER


def read_matching_managed_installation(
    data_dir: Path,
    *,
    executable: Path | None,
    version: str | None,
    install_directory: Path | None,
    hermes_install_method: str | None,
) -> ManagedInstallationRecord | None:
    """Return the marker when it still matches the detected installation."""
    if executable is None:
        return None

    payload = _read_marker_payload(data_dir)
    if payload is None:
        return None

    record = _record_from_payload(payload)
    if record is None:
        return None

    if _normalized(record.executable) != _normalized(executable):
        return None
    if not _optional_values_match(record.version, version):
        return None
    if not _optional_paths_match(record.install_directory, install_directory):
        return None
    if not _optional_values_match(
        record.hermes_install_method,
        hermes_install_method,
    ):
        return None

    return record


def is_managed_installation(
    data_dir: Path,
    executable: Path | None,
    *,
    version: str | None = None,
    install_directory: Path | None = None,
    hermes_install_method: str | None = None,
) -> bool:
    """Return whether the marker belongs to the detected installation."""
    return (
        read_matching_managed_installation(
            data_dir,
            executable=executable,
            version=version,
            install_directory=install_directory,
            hermes_install_method=hermes_install_method,
        )
        is not None
    )


def write_managed_installation(
    data_dir: Path,
    status: HermesStatus,
    *,
    installer_source: str,
) -> None:
    """Record an installation completed by bho."""
    if not status.installed or status.executable is None:
        raise ValueError("Cannot record a missing Hermes installation.")

    marker = managed_marker_path(data_dir)
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _MARKER_SCHEMA_VERSION,
        "executable": str(status.executable),
        "version": status.version,
        "install_directory": (
            str(status.install_directory) if status.install_directory else None
        ),
        "installer_source": installer_source,
        "hermes_install_method": status.hermes_install_method,
        "installed_at": datetime.now(UTC).isoformat(),
    }
    marker.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def remove_managed_installation(data_dir: Path) -> None:
    """Remove the bho Hermes management marker when present."""
    marker = managed_marker_path(data_dir)
    try:
        marker.unlink()
    except FileNotFoundError:
        return

    try:
        marker.parent.rmdir()
    except OSError:
        pass


def _read_marker_payload(data_dir: Path) -> dict[str, Any] | None:
    marker = managed_marker_path(data_dir)
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def _record_from_payload(payload: dict[str, Any]) -> ManagedInstallationRecord | None:
    executable = payload.get("executable")
    installer_source = payload.get("installer_source")
    installed_at = payload.get("installed_at")
    version = payload.get("version")
    install_directory = payload.get("install_directory")
    hermes_install_method = payload.get("hermes_install_method")

    if not isinstance(executable, str):
        return None
    if not isinstance(installer_source, str):
        return None
    if not isinstance(installed_at, str):
        return None
    if version is not None and not isinstance(version, str):
        return None
    if install_directory is not None and not isinstance(install_directory, str):
        return None
    if hermes_install_method is not None and not isinstance(
        hermes_install_method,
        str,
    ):
        return None

    return ManagedInstallationRecord(
        executable=Path(executable).expanduser(),
        version=version,
        install_directory=(
            Path(install_directory).expanduser() if install_directory else None
        ),
        installer_source=installer_source,
        hermes_install_method=hermes_install_method,
        installed_at=installed_at,
    )


def _normalized(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _optional_paths_match(recorded: Path | None, current: Path | None) -> bool:
    if recorded is None:
        return True
    if current is None:
        return False
    return _normalized(recorded) == _normalized(current)


def _optional_values_match(recorded: str | None, current: str | None) -> bool:
    if recorded is None:
        return True
    return recorded == current
