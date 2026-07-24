"""Tests for Hermes configuration orchestration."""

from pathlib import Path

import pytest

from bho.core.hermes.configuration import (
    apply_and_verify_hermes_configuration,
    prepare_hermes_configuration,
)
from bho.core.hermes.errors import HermesConfigurationError
from bho.core.hermes.models import (
    DockerAvailability,
    HermesConfigurationVerification,
    HermesDoctorResult,
    HermesProfileConfiguration,
    HermesProfileResult,
)


def _configuration() -> HermesProfileConfiguration:
    return HermesProfileConfiguration(
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


def _verification() -> HermesConfigurationVerification:
    return HermesConfigurationVerification(
        configuration=_configuration(),
        doctor=HermesDoctorResult(completed=True, returncode=0, summary=None),
        live_check_passed=True,
        live_check_output="OK",
    )


def test_prepare_requires_docker_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Profile creation must not start when Docker is unavailable."""
    monkeypatch.setattr(
        "bho.core.hermes.configuration.check_docker_availability",
        lambda **kwargs: DockerAvailability(None, False, "missing"),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.ensure_bho_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Profile creation should not run.")
        ),
    )

    with pytest.raises(HermesConfigurationError, match="Install Docker"):
        prepare_hermes_configuration(tmp_path / "hermes")


def test_prepare_reuses_profile_and_collects_recommendations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Preparation should inspect state without changing the active profile."""
    profile = HermesProfileResult("bho", tmp_path / "profile", False)
    monkeypatch.setattr(
        "bho.core.hermes.configuration.check_docker_availability",
        lambda **kwargs: DockerAvailability(tmp_path / "docker", True),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.ensure_bho_profile",
        lambda *args, **kwargs: profile,
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.inspect_profile_configuration",
        lambda *args, **kwargs: _configuration(),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.inspect_subscription_providers",
        lambda *args, **kwargs: (),
    )

    preparation = prepare_hermes_configuration(tmp_path / "hermes")

    assert preparation.profile == profile
    assert preparation.current.provider == "openai-codex"


def test_apply_runs_model_docker_verification_and_writes_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A successful flow should persist only after all checks complete."""
    calls: list[str] = []
    verification = _verification()

    monkeypatch.setattr(
        "bho.core.hermes.configuration.remove_configured_profile",
        lambda data_dir: calls.append("remove"),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.run_model_configuration",
        lambda *args, **kwargs: calls.append("model"),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.configure_docker_backend",
        lambda *args, **kwargs: calls.append("docker"),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.verify_hermes_configuration",
        lambda *args, **kwargs: calls.append("verify") or verification,
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.write_configured_profile",
        lambda *args, **kwargs: calls.append("write"),
    )

    result = apply_and_verify_hermes_configuration(
        tmp_path / "hermes",
        reconfigure_model=True,
        skip_live_check=False,
        hermes_version="0.19.0",
        home_dir=tmp_path,
        data_dir=tmp_path / "data",
        environment={},
    )

    assert result == verification
    assert calls == ["remove", "model", "docker", "verify", "write"]


def test_apply_skips_model_wizard_when_user_keeps_existing_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Repeated configuration should preserve provider credentials on request."""
    calls: list[str] = []
    monkeypatch.setattr(
        "bho.core.hermes.configuration.remove_configured_profile",
        lambda data_dir: calls.append("remove"),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.run_model_configuration",
        lambda *args, **kwargs: calls.append("model"),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.configure_docker_backend",
        lambda *args, **kwargs: calls.append("docker"),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.verify_hermes_configuration",
        lambda *args, **kwargs: calls.append("verify") or _verification(),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.write_configured_profile",
        lambda *args, **kwargs: calls.append("write"),
    )

    apply_and_verify_hermes_configuration(
        tmp_path / "hermes",
        reconfigure_model=False,
        skip_live_check=False,
        hermes_version="0.19.0",
        home_dir=tmp_path,
        data_dir=tmp_path / "data",
        environment={},
    )

    assert calls == ["remove", "docker", "verify", "write"]


def test_failed_verification_does_not_write_ready_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Failure after partial setup must not create a false configured state."""
    calls: list[str] = []
    monkeypatch.setattr(
        "bho.core.hermes.configuration.remove_configured_profile",
        lambda data_dir: calls.append("remove"),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.configure_docker_backend",
        lambda *args, **kwargs: calls.append("docker"),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.verify_hermes_configuration",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            HermesConfigurationError(
                "verification failed",
                stage="configuration verification",
            )
        ),
    )
    monkeypatch.setattr(
        "bho.core.hermes.configuration.write_configured_profile",
        lambda *args, **kwargs: calls.append("write"),
    )

    with pytest.raises(HermesConfigurationError):
        apply_and_verify_hermes_configuration(
            tmp_path / "hermes",
            reconfigure_model=False,
            skip_live_check=False,
            hermes_version="0.19.0",
            home_dir=tmp_path,
            data_dir=tmp_path / "data",
            environment={},
        )

    assert calls == ["remove", "docker"]
