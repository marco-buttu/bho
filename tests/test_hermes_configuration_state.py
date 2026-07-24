"""Tests for non-secret bho Hermes profile metadata."""

from pathlib import Path

import pytest

from bho.core.hermes.configuration_state import (
    read_configured_profile,
    remove_configured_profile,
    write_configured_profile,
)
from bho.core.hermes.models import (
    HermesConfigurationVerification,
    HermesDoctorResult,
    HermesProfileConfiguration,
)


def _verification(*, live_check_passed: bool | None = True) -> HermesConfigurationVerification:
    configuration = HermesProfileConfiguration(
        profile_name="bho",
        profile_path=Path("/home/user/.hermes/profiles/bho"),
        provider="openai-codex",
        model="gpt-5.4",
        authentication_configured=True,
        configured_api_providers=(),
        terminal_backend="docker",
        docker_mount_cwd_to_workspace=True,
        docker_run_as_host_user=True,
        docker_forward_env_empty=True,
        fallback_configured=False,
    )
    return HermesConfigurationVerification(
        configuration=configuration,
        doctor=HermesDoctorResult(completed=True, returncode=0, summary=None),
        live_check_passed=live_check_passed,
        live_check_output="OK" if live_check_passed else None,
    )


def test_verified_configuration_is_recorded_without_secrets(tmp_path: Path) -> None:
    """The marker should contain only non-secret profile metadata."""
    record = write_configured_profile(
        tmp_path,
        _verification(),
        hermes_version="0.19.0",
    )

    stored = read_configured_profile(tmp_path)
    marker_text = (tmp_path / "hermes" / "configured.json").read_text(
        encoding="utf-8"
    )

    assert stored == record
    assert record.ready is True
    assert "access_token" not in marker_text
    assert "api_key" not in marker_text
    assert "refresh_token" not in marker_text


def test_skipped_live_check_records_not_ready(tmp_path: Path) -> None:
    """A skipped live check may be recorded but must not claim readiness."""
    record = write_configured_profile(
        tmp_path,
        _verification(live_check_passed=None),
        hermes_version="0.19.0",
    )

    assert record.ready is False
    assert record.live_check_passed is None


def test_unverified_configuration_is_not_recorded(tmp_path: Path) -> None:
    """A false ready marker must not be created after failed checks."""
    invalid = HermesConfigurationVerification(
        configuration=HermesProfileConfiguration(
            profile_name="bho",
            profile_path=None,
            provider=None,
            model=None,
            authentication_configured=False,
            configured_api_providers=(),
            terminal_backend="local",
            docker_mount_cwd_to_workspace=False,
            docker_run_as_host_user=False,
            docker_forward_env_empty=False,
            fallback_configured=False,
        ),
        doctor=HermesDoctorResult(completed=True, returncode=0, summary=None),
        live_check_passed=None,
        live_check_output=None,
    )

    with pytest.raises(ValueError, match="unverified"):
        write_configured_profile(tmp_path, invalid, hermes_version="0.19.0")

    assert read_configured_profile(tmp_path) is None


def test_configured_profile_marker_can_be_removed(tmp_path: Path) -> None:
    """Reconfiguration should invalidate stale bho metadata before changes."""
    write_configured_profile(tmp_path, _verification(), hermes_version="0.19.0")

    remove_configured_profile(tmp_path)

    assert read_configured_profile(tmp_path) is None
