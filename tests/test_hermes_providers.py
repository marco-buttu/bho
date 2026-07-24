"""Tests for Hermes provider discovery and model configuration."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bho.core.hermes.errors import HermesConfigurationError
from bho.core.hermes.providers import (
    authentication_output_is_configured,
    inspect_subscription_providers,
    run_model_configuration,
)


@pytest.mark.parametrize(
    ("output", "returncode", "expected"),
    [
        ("Logged in and credentials valid", 0, True),
        ("Authentication configured", 0, True),
        ("No credentials stored", 0, False),
        ("Token expired; re-authenticate", 0, False),
        ("Provider unavailable", 3, False),
    ],
)
def test_authentication_output_parsing(
    output: str,
    returncode: int,
    expected: bool,
) -> None:
    """Authentication status parsing must never expose or inspect secrets."""
    assert authentication_output_is_configured(output, returncode) is expected


def test_subscription_providers_prioritize_configured_options(tmp_path: Path) -> None:
    """Existing subscription auth should rank before new OAuth options."""
    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        provider = arguments[-1]
        if provider == "openai-codex":
            return subprocess.CompletedProcess(arguments, 0, stdout="No credentials", stderr="")
        if provider == "copilot":
            return subprocess.CompletedProcess(arguments, 0, stdout="Logged in", stderr="")
        if provider == "nous":
            return subprocess.CompletedProcess(arguments, 0, stdout="Not logged in", stderr="")
        return subprocess.CompletedProcess(
            arguments,
            2,
            stdout="",
            stderr="Unknown provider",
        )

    options = inspect_subscription_providers(
        tmp_path / "hermes",
        "bho",
        run_fn=fake_run,
    )

    assert [option.provider for option in options] == [
        "copilot",
        "openai-codex",
        "nous",
    ]
    assert options[0].authentication_configured is True


def test_openai_codex_is_first_new_subscription_option(tmp_path: Path) -> None:
    """ChatGPT OAuth should be the first recommendation when none is configured."""
    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        provider = arguments[-1]
        if provider in {"openai-codex", "copilot", "nous"}:
            return subprocess.CompletedProcess(arguments, 0, stdout="Not configured", stderr="")
        return subprocess.CompletedProcess(arguments, 2, stdout="", stderr="Unknown provider")

    options = inspect_subscription_providers(
        tmp_path / "hermes",
        "bho",
        run_fn=fake_run,
    )

    assert options[0].provider == "openai-codex"
    assert "ChatGPT" in options[0].label


def test_model_configuration_targets_bho_profile(tmp_path: Path) -> None:
    """The official Hermes model wizard must target the bho profile explicitly."""
    process = SimpleNamespace(pid=123, returncode=0)
    process.wait = lambda timeout=None: 0
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_factory(arguments: list[str], **kwargs: object) -> object:
        calls.append((arguments, kwargs))
        return process

    run_model_configuration(
        tmp_path / "hermes",
        "bho",
        process_factory=fake_factory,
        timeout_seconds=1,
    )

    assert calls[0][0] == [str(tmp_path / "hermes"), "-p", "bho", "model"]
    assert calls[0][1]["start_new_session"] is True


def test_model_configuration_timeout_is_reported(tmp_path: Path) -> None:
    """An interactive Hermes wizard must not remain blocked indefinitely."""
    class FakeProcess:
        pid = 999999
        returncode = None

        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired("hermes", timeout)

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    with pytest.raises(HermesConfigurationError, match="timed out") as captured:
        run_model_configuration(
            tmp_path / "hermes",
            "bho",
            process_factory=lambda *args, **kwargs: FakeProcess(),
            timeout_seconds=0.01,
        )

    assert captured.value.stage == "model configuration"
