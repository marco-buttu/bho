"""Persist non-secret state for the Hermes profile used by bho."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bho.core.hermes.models import (
    ConfiguredProfileRecord,
    HermesConfigurationVerification,
)

CONFIGURED_PROFILE_MARKER = Path("hermes") / "configured.json"
_MARKER_SCHEMA_VERSION = 1


def configured_profile_marker_path(data_dir: Path) -> Path:
    """Return the path of the bho Hermes profile configuration marker."""
    return data_dir / CONFIGURED_PROFILE_MARKER


def write_configured_profile(
    data_dir: Path,
    verification: HermesConfigurationVerification,
    *,
    hermes_version: str | None,
) -> ConfiguredProfileRecord:
    """Record verified non-secret metadata for the bho Hermes profile."""
    configuration = verification.configuration
    if not verification.required_checks_passed:
        raise ValueError("Cannot record an unverified Hermes profile configuration.")
    if configuration.provider is None or configuration.model is None:
        raise ValueError("Cannot record a profile without provider and model.")
    if configuration.terminal_backend is None:
        raise ValueError("Cannot record a profile without a terminal backend.")

    record = ConfiguredProfileRecord(
        profile_name=configuration.profile_name,
        profile_path=configuration.profile_path,
        provider=configuration.provider,
        model=configuration.model,
        terminal_backend=configuration.terminal_backend,
        verified_at=datetime.now(UTC).isoformat(),
        live_check_passed=verification.live_check_passed,
        hermes_version=hermes_version,
        ready=verification.ready,
    )
    marker = configured_profile_marker_path(data_dir)
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _MARKER_SCHEMA_VERSION,
        "profile_name": record.profile_name,
        "profile_path": str(record.profile_path) if record.profile_path else None,
        "provider": record.provider,
        "model": record.model,
        "terminal_backend": record.terminal_backend,
        "verified_at": record.verified_at,
        "live_check_passed": record.live_check_passed,
        "hermes_version": record.hermes_version,
        "ready": record.ready,
    }
    marker.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return record


def read_configured_profile(data_dir: Path) -> ConfiguredProfileRecord | None:
    """Read the recorded non-secret Hermes profile configuration."""
    marker = configured_profile_marker_path(data_dir)
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    return _record_from_payload(payload)


def remove_configured_profile(data_dir: Path) -> None:
    """Remove the bho Hermes profile configuration marker when present."""
    marker = configured_profile_marker_path(data_dir)
    try:
        marker.unlink()
    except FileNotFoundError:
        return

    try:
        marker.parent.rmdir()
    except OSError:
        pass


def _record_from_payload(payload: dict[str, Any]) -> ConfiguredProfileRecord | None:
    if payload.get("schema_version") != _MARKER_SCHEMA_VERSION:
        return None

    profile_name = payload.get("profile_name")
    profile_path = payload.get("profile_path")
    provider = payload.get("provider")
    model = payload.get("model")
    terminal_backend = payload.get("terminal_backend")
    verified_at = payload.get("verified_at")
    live_check_passed = payload.get("live_check_passed")
    hermes_version = payload.get("hermes_version")
    ready = payload.get("ready")

    required_strings = (
        profile_name,
        provider,
        model,
        terminal_backend,
        verified_at,
    )
    if not all(isinstance(value, str) for value in required_strings):
        return None
    if profile_path is not None and not isinstance(profile_path, str):
        return None
    if live_check_passed is not None and not isinstance(live_check_passed, bool):
        return None
    if hermes_version is not None and not isinstance(hermes_version, str):
        return None
    if not isinstance(ready, bool):
        return None

    return ConfiguredProfileRecord(
        profile_name=profile_name,
        profile_path=Path(profile_path).expanduser() if profile_path else None,
        provider=provider,
        model=model,
        terminal_backend=terminal_backend,
        verified_at=verified_at,
        live_check_passed=live_check_passed,
        hermes_version=hermes_version,
        ready=ready,
    )
