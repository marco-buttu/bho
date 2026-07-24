"""Inspect and configure Hermes inference providers without handling secrets."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from bho.core.hermes.errors import HermesConfigurationError
from bho.core.hermes.models import SubscriptionProviderOption

DEFAULT_MODEL_SETUP_TIMEOUT_SECONDS = 30 * 60
_PROCESS_TERMINATION_TIMEOUT_SECONDS = 5


class InteractiveProcess(Protocol):
    """Describe the subprocess operations used by interactive Hermes commands."""

    pid: int
    returncode: int | None

    def wait(self, timeout: float | None = None) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


ProcessFactory = Callable[..., InteractiveProcess]
RunFunction = Callable[..., subprocess.CompletedProcess[str]]


_SUBSCRIPTION_PROVIDERS = (
    (
        "openai-codex",
        "OpenAI Codex via ChatGPT subscription",
        "Uses ChatGPT OAuth and Codex models. It does not use OpenAI API "
        "billing and remains subject to the ChatGPT plan limits.",
    ),
    (
        "copilot",
        "GitHub Copilot subscription",
        "Uses GitHub Copilot authentication when available.",
    ),
    (
        "nous",
        "Nous Portal subscription",
        "Uses a Nous Portal subscription through Hermes OAuth.",
    ),
    (
        "xai-oauth",
        "xAI Grok subscription OAuth",
        "Uses a supported SuperGrok or X subscription through OAuth.",
    ),
    (
        "qwen-oauth",
        "Qwen Portal OAuth",
        "Uses the consumer Qwen Portal through OAuth.",
    ),
    (
        "minimax-oauth",
        "MiniMax subscription OAuth",
        "Uses MiniMax browser OAuth without an API key.",
    ),
)


def inspect_subscription_providers(
    executable: Path,
    profile_name: str,
    *,
    environment: Mapping[str, str] | None = None,
    run_fn: RunFunction = subprocess.run,
) -> tuple[SubscriptionProviderOption, ...]:
    """Probe subscription-backed providers supported by the installed Hermes."""
    options: list[SubscriptionProviderOption] = []
    for provider, label, description in _SUBSCRIPTION_PROVIDERS:
        supported, configured = inspect_provider_authentication(
            executable,
            profile_name,
            provider,
            environment=environment,
            run_fn=run_fn,
        )
        if supported:
            options.append(
                SubscriptionProviderOption(
                    provider=provider,
                    label=label,
                    description=description,
                    supported=True,
                    authentication_configured=configured,
                )
            )

    return tuple(
        sorted(
            options,
            key=lambda option: (
                not option.authentication_configured,
                _provider_order(option.provider),
            ),
        )
    )


def inspect_provider_authentication(
    executable: Path,
    profile_name: str,
    provider: str,
    *,
    environment: Mapping[str, str] | None = None,
    run_fn: RunFunction = subprocess.run,
) -> tuple[bool, bool]:
    """Return whether a provider is supported and currently authenticated."""
    arguments = [
        str(executable),
        "-p",
        profile_name,
        "auth",
        "status",
        provider,
    ]
    try:
        result = run_fn(
            arguments,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=dict(environment) if environment is not None else None,
        )
    except (OSError, subprocess.SubprocessError):
        return False, False

    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    normalized = output.lower()
    unsupported_markers = (
        "unknown provider",
        "unsupported provider",
        "invalid provider",
        "no such provider",
        "provider not found",
        "unrecognized provider",
        "invalid choice",
    )
    if any(marker in normalized for marker in unsupported_markers):
        return False, False

    return True, authentication_output_is_configured(output, result.returncode)


def authentication_output_is_configured(output: str, returncode: int) -> bool:
    """Interpret redacted Hermes authentication status output."""
    normalized = output.lower()
    negative_markers = (
        "not configured",
        "not authenticated",
        "not logged in",
        "no credentials",
        "credentials missing",
        "missing credentials",
        "expired",
        "invalid token",
        "re-authenticate",
        "relogin required",
        "logged out",
    )
    if any(marker in normalized for marker in negative_markers):
        return False
    if returncode != 0:
        return False

    positive_markers = (
        "configured",
        "authenticated",
        "logged in",
        "credential",
        "valid",
        "active",
        "ready",
        "available",
    )
    if any(marker in normalized for marker in positive_markers):
        return True

    return returncode == 0 and bool(normalized.strip())


def run_model_configuration(
    executable: Path,
    profile_name: str,
    *,
    environment: Mapping[str, str] | None = None,
    process_factory: ProcessFactory = subprocess.Popen,
    timeout_seconds: float = DEFAULT_MODEL_SETUP_TIMEOUT_SECONDS,
) -> None:
    """Run the official interactive Hermes model and authentication wizard."""
    arguments = [str(executable), "-p", profile_name, "model"]
    try:
        process = process_factory(
            arguments,
            env=dict(environment) if environment is not None else None,
            start_new_session=True,
        )
    except OSError as error:
        raise HermesConfigurationError(
            f"Could not start the Hermes model configuration wizard: {error}",
            stage="model configuration",
        ) from error

    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        _terminate_process(process)
        raise HermesConfigurationError(
            "The Hermes model configuration wizard timed out.",
            stage="model configuration",
        ) from error
    except KeyboardInterrupt as error:
        _terminate_process(process)
        raise HermesConfigurationError(
            "Hermes model configuration was cancelled.",
            stage="model configuration",
        ) from error

    if returncode != 0:
        raise HermesConfigurationError(
            "The Hermes model configuration wizard did not complete successfully.",
            stage="model configuration",
        )


def _provider_order(provider: str) -> int:
    for index, (candidate, _label, _description) in enumerate(
        _SUBSCRIPTION_PROVIDERS
    ):
        if provider == candidate:
            return index
    return len(_SUBSCRIPTION_PROVIDERS)


def _terminate_process(process: InteractiveProcess) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError, PermissionError):
            try:
                process.terminate()
            except OSError:
                pass
    else:
        try:
            process.terminate()
        except OSError:
            pass

    try:
        process.wait(timeout=_PROCESS_TERMINATION_TIMEOUT_SECONDS)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError, PermissionError):
            try:
                process.kill()
            except OSError:
                pass
    else:
        try:
            process.kill()
        except OSError:
            pass
