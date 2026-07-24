"""Tests for Hermes profile inspection and verification."""

import subprocess
from pathlib import Path

import pytest

from bho.core.hermes.errors import HermesConfigurationError
from bho.core.hermes.verification import (
    inspect_profile_configuration,
    run_hermes_doctor,
    run_live_model_check,
    verify_hermes_configuration,
)


def _configured_run(
    tmp_path: Path,
    *,
    fallback: bool = False,
    live_output: str = "OK",
    live_returncode: int = 0,
    doctor_returncode: int = 0,
):
    profile_path = tmp_path / ".hermes" / "profiles" / "bho"
    fallback_yaml = (
        "fallback_providers:\n  - provider: openrouter\n    model: paid/model\n"
        if fallback
        else "fallback_providers: []\n"
    )
    config_path = profile_path / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "model:\n"
        "  provider: openai-codex\n"
        "  default: gpt-5.4\n"
        "terminal:\n"
        "  backend: docker\n"
        "  docker_mount_cwd_to_workspace: true\n"
        "  docker_run_as_host_user: true\n"
        "  docker_forward_env: []\n"
        f"{fallback_yaml}",
        encoding="utf-8",
    )

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if arguments[1:4] == ["profile", "show", "bho"]:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=f"Profile: bho\nPath: {profile_path}\n",
                stderr="",
            )
        if arguments[-1] == "dump":
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=(
                    "--- hermes dump ---\n"
                    "profile: bho\n"
                    "model: gpt-5.4\n"
                    "provider: openai-codex\n"
                    "terminal: docker\n"
                    "api_keys:\n"
                    "  openrouter           set\n"
                    "  anthropic            not set\n"
                ),
                stderr="",
            )
        if arguments[-2:] == ["config", "path"]:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=f"{config_path}\n",
                stderr="",
            )
        if arguments[-2:] == ["config", "show"]:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=config_path.read_text(encoding="utf-8"),
                stderr="",
            )
        if "auth" in arguments and "status" in arguments:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout="Logged in; credentials valid",
                stderr="",
            )
        if arguments[-1] == "doctor":
            return subprocess.CompletedProcess(
                arguments,
                doctor_returncode,
                stdout="Diagnostics completed\nOptional tool missing",
                stderr="",
            )
        if "-z" in arguments:
            return subprocess.CompletedProcess(
                arguments,
                live_returncode,
                stdout=live_output,
                stderr="provider failure" if live_returncode else "",
            )
        raise AssertionError(f"Unexpected command: {arguments}")

    return fake_run


def test_profile_configuration_is_parsed_without_reading_secrets(tmp_path: Path) -> None:
    """Provider, model, auth, and Docker settings should come from Hermes commands."""
    configuration = inspect_profile_configuration(
        tmp_path / "hermes",
        "bho",
        run_fn=_configured_run(tmp_path),
    )

    assert configuration.profile_path == tmp_path / ".hermes" / "profiles" / "bho"
    assert configuration.provider == "openai-codex"
    assert configuration.model == "gpt-5.4"
    assert configuration.authentication_configured is True
    assert configuration.configured_api_providers == ("openrouter",)
    assert configuration.docker_configured is True
    assert configuration.fallback_configured is False


def test_doctor_warnings_are_non_fatal(tmp_path: Path) -> None:
    """Optional Hermes doctor warnings should not invalidate core configuration."""
    result = run_hermes_doctor(
        tmp_path / "hermes",
        "bho",
        run_fn=_configured_run(tmp_path, doctor_returncode=1),
    )

    assert result.completed is True
    assert result.returncode == 1
    assert "Optional tool missing" in (result.summary or "")


def test_live_check_forces_selected_provider_and_model(tmp_path: Path) -> None:
    """The check should use the selected provider rather than an automatic choice."""
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout="OK\n", stderr="")

    output = run_live_model_check(
        tmp_path / "hermes",
        "bho",
        provider="openai-codex",
        model="gpt-5.4",
        run_fn=fake_run,
    )

    assert output == "OK"
    assert calls == [[
        str(tmp_path / "hermes"),
        "-p",
        "bho",
        "-z",
        "Reply with exactly: OK",
        "--provider",
        "openai-codex",
        "--model",
        "gpt-5.4",
    ]]


def test_live_check_failure_does_not_fall_back_silently(tmp_path: Path) -> None:
    """A provider error should fail instead of being hidden."""
    with pytest.raises(HermesConfigurationError, match="did not pass") as captured:
        run_live_model_check(
            tmp_path / "hermes",
            "bho",
            provider="openai-codex",
            model="gpt-5.4",
            run_fn=lambda arguments, **kwargs: subprocess.CompletedProcess(
                arguments,
                4,
                stdout="",
                stderr="provider unavailable",
            ),
        )

    assert captured.value.stage == "live model verification"


def test_live_check_timeout_is_reported(tmp_path: Path) -> None:
    """A model request must not block bho indefinitely."""
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("hermes", 1)

    with pytest.raises(HermesConfigurationError, match="timed out"):
        run_live_model_check(
            tmp_path / "hermes",
            "bho",
            provider="openai-codex",
            model="gpt-5.4",
            run_fn=fake_run,
            timeout_seconds=1,
        )


def test_verification_can_skip_live_inference(tmp_path: Path) -> None:
    """The explicit option should validate all other required settings."""
    verification = verify_hermes_configuration(
        tmp_path / "hermes",
        "bho",
        skip_live_check=True,
        run_fn=_configured_run(tmp_path),
    )

    assert verification.required_checks_passed is True
    assert verification.live_check_passed is None
    assert verification.ready is False


def test_verification_rejects_fallback_chain_for_live_check(tmp_path: Path) -> None:
    """The live check must not trigger a separately billed fallback provider."""
    with pytest.raises(HermesConfigurationError, match="fallback providers"):
        verify_hermes_configuration(
            tmp_path / "hermes",
            "bho",
            skip_live_check=False,
            run_fn=_configured_run(tmp_path, fallback=True),
        )


def test_complete_verification_is_ready(tmp_path: Path) -> None:
    """A successful live check should mark the profile ready."""
    verification = verify_hermes_configuration(
        tmp_path / "hermes",
        "bho",
        skip_live_check=False,
        run_fn=_configured_run(tmp_path),
    )

    assert verification.ready is True
    assert verification.live_check_output == "OK"


def test_missing_authentication_fails_verification(tmp_path: Path) -> None:
    """A selected model without credentials is incomplete."""
    base_run = _configured_run(tmp_path)

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "auth" in arguments and "status" in arguments:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout="No credentials stored",
                stderr="",
            )
        return base_run(arguments, **kwargs)

    with pytest.raises(HermesConfigurationError, match="provider authentication"):
        verify_hermes_configuration(
            tmp_path / "hermes",
            "bho",
            skip_live_check=True,
            run_fn=fake_run,
        )
