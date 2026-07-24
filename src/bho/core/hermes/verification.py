"""Inspect and verify the Hermes profile configured for bho."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from bho.core.hermes.errors import HermesConfigurationError
from bho.core.hermes.models import (
    HermesConfigurationVerification,
    HermesDoctorResult,
    HermesProfileConfiguration,
)
from bho.core.hermes.profiles import inspect_profile
from bho.core.hermes.providers import inspect_provider_authentication

RunFunction = Callable[..., subprocess.CompletedProcess[str]]

DEFAULT_DOCTOR_TIMEOUT_SECONDS = 90
DEFAULT_LIVE_CHECK_TIMEOUT_SECONDS = 180
_LIVE_CHECK_PROMPT = "Reply with exactly: OK"


def inspect_profile_configuration(
    executable: Path,
    profile_name: str,
    *,
    environment: Mapping[str, str] | None = None,
    run_fn: RunFunction = subprocess.run,
) -> HermesProfileConfiguration:
    """Inspect non-secret provider, model, and terminal settings."""
    env = dict(environment) if environment is not None else None
    profile_path = inspect_profile(
        executable,
        profile_name,
        environment=environment,
        run_fn=run_fn,
    )

    dump_output = _run_optional_command(
        [str(executable), "-p", profile_name, "dump"],
        environment=env,
        run_fn=run_fn,
    )
    config_output = _read_profile_config(
        executable,
        profile_name,
        environment=env,
        run_fn=run_fn,
    )
    if not config_output:
        config_output = _run_optional_command(
            [str(executable), "-p", profile_name, "config", "show"],
            environment=env,
            run_fn=run_fn,
        )

    dump_values = _parse_colon_values(dump_output)
    config_values = _parse_yaml_like_values(config_output)

    provider = _clean_value(
        dump_values.get("provider") or config_values.get("model.provider")
    )
    model = _clean_value(
        dump_values.get("model")
        or config_values.get("model.default")
        or config_values.get("model.model")
    )
    terminal_backend = _clean_value(
        dump_values.get("terminal") or config_values.get("terminal.backend")
    )

    authentication_configured = False
    if provider and provider not in {"auto", "none", "unknown"}:
        _supported, authentication_configured = inspect_provider_authentication(
            executable,
            profile_name,
            provider,
            environment=environment,
            run_fn=run_fn,
        )

    return HermesProfileConfiguration(
        profile_name=profile_name,
        profile_path=profile_path,
        provider=provider,
        model=model,
        authentication_configured=authentication_configured,
        configured_api_providers=_parse_configured_api_providers(dump_output),
        terminal_backend=terminal_backend,
        docker_mount_cwd_to_workspace=_parse_bool(
            config_values.get("terminal.docker_mount_cwd_to_workspace")
        ),
        docker_run_as_host_user=_parse_bool(
            config_values.get("terminal.docker_run_as_host_user")
        ),
        docker_forward_env_empty=_parse_empty_collection(
            config_values.get("terminal.docker_forward_env")
        ),
        fallback_configured=_fallback_is_configured(config_output),
    )


def verify_hermes_configuration(
    executable: Path,
    profile_name: str,
    *,
    skip_live_check: bool,
    environment: Mapping[str, str] | None = None,
    run_fn: RunFunction = subprocess.run,
    doctor_timeout_seconds: float = DEFAULT_DOCTOR_TIMEOUT_SECONDS,
    live_check_timeout_seconds: float = DEFAULT_LIVE_CHECK_TIMEOUT_SECONDS,
) -> HermesConfigurationVerification:
    """Verify the Hermes profile, diagnostics, and optional live inference."""
    configuration = inspect_profile_configuration(
        executable,
        profile_name,
        environment=environment,
        run_fn=run_fn,
    )
    _validate_required_configuration(configuration)

    doctor = run_hermes_doctor(
        executable,
        profile_name,
        environment=environment,
        run_fn=run_fn,
        timeout_seconds=doctor_timeout_seconds,
    )

    if skip_live_check:
        return HermesConfigurationVerification(
            configuration=configuration,
            doctor=doctor,
            live_check_passed=None,
            live_check_output=None,
        )

    if configuration.fallback_configured:
        raise HermesConfigurationError(
            "The bho profile has fallback providers configured. The live check "
            "was not run because a failed primary provider could trigger a "
            "separately billed fallback. Remove the fallback chain or rerun with "
            "--skip-live-check.",
            stage="live model verification",
            completed_stages=(
                "profile available",
                "model configured",
                "Docker backend configured",
                "diagnostics completed",
            ),
        )

    output = run_live_model_check(
        executable,
        profile_name,
        provider=configuration.provider,
        model=configuration.model,
        environment=environment,
        run_fn=run_fn,
        timeout_seconds=live_check_timeout_seconds,
    )
    return HermesConfigurationVerification(
        configuration=configuration,
        doctor=doctor,
        live_check_passed=True,
        live_check_output=output,
    )


def run_hermes_doctor(
    executable: Path,
    profile_name: str,
    *,
    environment: Mapping[str, str] | None = None,
    run_fn: RunFunction = subprocess.run,
    timeout_seconds: float = DEFAULT_DOCTOR_TIMEOUT_SECONDS,
) -> HermesDoctorResult:
    """Run Hermes diagnostics and retain only a redacted summary."""
    arguments = [str(executable), "-p", profile_name, "doctor"]
    try:
        result = run_fn(
            arguments,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=dict(environment) if environment is not None else None,
        )
    except subprocess.TimeoutExpired as error:
        raise HermesConfigurationError(
            "Hermes diagnostics timed out.",
            stage="diagnostics",
            completed_stages=(
                "profile available",
                "model configured",
                "Docker backend configured",
            ),
        ) from error
    except (OSError, subprocess.SubprocessError) as error:
        raise HermesConfigurationError(
            f"Hermes diagnostics could not be executed: {error}",
            stage="diagnostics",
            completed_stages=(
                "profile available",
                "model configured",
                "Docker backend configured",
            ),
        ) from error

    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return HermesDoctorResult(
        completed=True,
        returncode=result.returncode,
        summary=_safe_output_summary(output),
    )


def run_live_model_check(
    executable: Path,
    profile_name: str,
    *,
    provider: str | None,
    model: str | None,
    environment: Mapping[str, str] | None = None,
    run_fn: RunFunction = subprocess.run,
    timeout_seconds: float = DEFAULT_LIVE_CHECK_TIMEOUT_SECONDS,
) -> str:
    """Run one minimal inference using only the selected provider and model."""
    if not provider or not model:
        raise HermesConfigurationError(
            "A provider and model are required for the live check.",
            stage="live model verification",
        )

    arguments = [
        str(executable),
        "-p",
        profile_name,
        "-z",
        _LIVE_CHECK_PROMPT,
        "--provider",
        provider,
        "--model",
        model,
    ]
    try:
        result = run_fn(
            arguments,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=dict(environment) if environment is not None else None,
        )
    except subprocess.TimeoutExpired as error:
        raise HermesConfigurationError(
            "The Hermes live model check timed out.",
            stage="live model verification",
            completed_stages=(
                "profile available",
                "model configured",
                "Docker backend configured",
                "diagnostics completed",
            ),
        ) from error
    except (OSError, subprocess.SubprocessError) as error:
        raise HermesConfigurationError(
            f"The Hermes live model check could not be executed: {error}",
            stage="live model verification",
            completed_stages=(
                "profile available",
                "model configured",
                "Docker backend configured",
                "diagnostics completed",
            ),
        ) from error

    output = (result.stdout or "").strip()
    if result.returncode != 0:
        detail = _safe_output_summary(
            "\n".join(part for part in (result.stdout, result.stderr) if part)
        )
        message = (
            "The selected Hermes provider did not pass the live model check."
        )
        if detail:
            message = f"{message} {detail}"
        raise HermesConfigurationError(
            message,
            stage="live model verification",
            completed_stages=(
                "profile available",
                "model configured",
                "Docker backend configured",
                "diagnostics completed",
            ),
        )

    if output.upper() != "OK":
        raise HermesConfigurationError(
            "The selected provider returned an unexpected response during the "
            "live model check.",
            stage="live model verification",
            completed_stages=(
                "profile available",
                "model configured",
                "Docker backend configured",
                "diagnostics completed",
            ),
        )
    return output


def _validate_required_configuration(
    configuration: HermesProfileConfiguration,
) -> None:
    missing: list[str] = []
    if not configuration.model_configured:
        missing.append("provider and model")
    if not configuration.authentication_configured:
        missing.append("provider authentication")
    if configuration.terminal_backend != "docker":
        missing.append("Docker terminal backend")
    if configuration.docker_mount_cwd_to_workspace is not True:
        missing.append("workspace mount")
    if configuration.docker_run_as_host_user is not True:
        missing.append("host-user file ownership")
    if configuration.docker_forward_env_empty is not True:
        missing.append("empty Docker credential forwarding list")

    if missing:
        raise HermesConfigurationError(
            "Hermes configuration verification failed. Missing or invalid: "
            + ", ".join(missing)
            + ".",
            stage="configuration verification",
            completed_stages=("profile available",),
        )


def _read_profile_config(
    executable: Path,
    profile_name: str,
    *,
    environment: Mapping[str, str] | None,
    run_fn: RunFunction,
) -> str:
    """Read only the non-secret Hermes config.yaml selected by the profile."""
    output = _run_optional_command(
        [str(executable), "-p", profile_name, "config", "path"],
        environment=environment,
        run_fn=run_fn,
    )
    candidates = [line.strip() for line in output.splitlines() if line.strip()]
    if not candidates:
        return ""

    config_path = Path(candidates[-1]).expanduser()
    try:
        return config_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _run_optional_command(
    arguments: list[str],
    *,
    environment: Mapping[str, str] | None,
    run_fn: RunFunction,
) -> str:
    try:
        result = run_fn(
            arguments,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=dict(environment) if environment is not None else None,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return "\n".join(part for part in (result.stdout, result.stderr) if part)


def _parse_configured_api_providers(output: str) -> tuple[str, ...]:
    """Return provider names marked as set in the redacted Hermes dump."""
    providers: list[str] = []
    in_api_keys = False
    section_indent = 0

    for raw_line in output.splitlines():
        if not raw_line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if stripped == "api_keys:":
            in_api_keys = True
            section_indent = indent
            continue
        if in_api_keys and indent <= section_indent:
            break
        if not in_api_keys:
            continue

        parts = stripped.split()
        if (
            len(parts) >= 2
            and parts[-1].lower() == "set"
            and (len(parts) < 3 or parts[-2].lower() != "not")
        ):
            provider = parts[0].strip()
            if provider and provider not in providers:
                providers.append(provider)

    return tuple(providers)


def _parse_colon_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() and value.strip():
            values[key.strip().lower()] = value.strip()
    return values


def _parse_yaml_like_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    sections: list[tuple[int, str]] = []

    for raw_line in output.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        key, separator, value = stripped.partition(":")
        if not separator or not key.strip() or key.lstrip().startswith("-"):
            continue

        while sections and sections[-1][0] >= indent:
            sections.pop()

        key = key.strip()
        value = value.strip()
        path_parts = [section for _level, section in sections] + [key]
        path = ".".join(path_parts)
        if value:
            values[path] = _strip_quotes(value)
        else:
            sections.append((indent, key))

    return values


def _fallback_is_configured(output: str) -> bool:
    lines = output.splitlines()
    for index, raw_line in enumerate(lines):
        if not raw_line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        key, separator, value = stripped.partition(":")
        if not separator or key not in {"fallback_providers", "fallback_model"}:
            continue

        scalar = value.strip().lower()
        if scalar in {"[]", "{}", "null", "none", ""}:
            if scalar:
                return False
            for following in lines[index + 1 :]:
                if not following.strip():
                    continue
                following_indent = len(following) - len(following.lstrip(" "))
                if following_indent <= indent:
                    return False
                content = following.strip().lower()
                if content not in {"[]", "{}", "null", "none"}:
                    return True
            return False
        return True
    return False


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _strip_quotes(value.strip())
    if not cleaned or cleaned.lower() in {
        "none",
        "null",
        "unknown",
        "not configured",
        "<not configured>",
    }:
        return None
    return cleaned


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "1", "on"}:
        return True
    if normalized in {"false", "no", "0", "off"}:
        return False
    return None


def _parse_empty_collection(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace(" ", "")
    if normalized in {"[]", "{}", "null", "none"}:
        return True
    return False


def _safe_output_summary(output: str) -> str | None:
    sensitive_terms = (
        "api_key",
        "access_token",
        "refresh_token",
        "authorization",
        "password",
        "secret",
    )
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    safe_lines = [
        line
        for line in lines
        if not any(term in line.lower() for term in sensitive_terms)
    ]
    if not safe_lines:
        return None
    return " | ".join(safe_lines[-4:])[:600]
