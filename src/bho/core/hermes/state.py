"""Persist local state for the Hermes installation managed by bho."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from bho.core.hermes.models import HermesStatus

MANAGED_INSTALLATION_MARKER = Path("hermes") / "managed.json"


def managed_marker_path(data_dir: Path) -> Path:
    """Return the path of the bho Hermes management marker."""
    return data_dir / MANAGED_INSTALLATION_MARKER


def is_managed_installation(data_dir: Path, executable: Path | None) -> bool:
    """Return whether the marker belongs to the detected executable."""
    if executable is None:
        return False

    marker = managed_marker_path(data_dir)
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return False

    recorded_executable = payload.get("executable")
    if not isinstance(recorded_executable, str):
        return False

    return Path(recorded_executable).expanduser().resolve(strict=False) == executable.resolve(
        strict=False
    )


def write_managed_installation(data_dir: Path, status: HermesStatus) -> None:
    """Record an installation completed by bho."""
    if not status.installed or status.executable is None:
        raise ValueError("Cannot record a missing Hermes installation.")

    marker = managed_marker_path(data_dir)
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "executable": str(status.executable),
        "version": status.version,
        "installation_method": status.installation_method,
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
