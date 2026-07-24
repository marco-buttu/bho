"""Orchestrate Hermes profile configuration for bho."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from bho.core.hermes.configuration_state import (
    remove_configured_profile,
    write_configured_profile,
)
from bho.core.hermes.detector import default_bho_data_dir
from bho.core.hermes.docker_backend import (
    check_docker_availability,
    configure_docker_backend,
)
from bho.core.hermes.errors import HermesConfigurationError
from bho.core.hermes.models import (
    DockerAvailability,
    HermesConfigurationVerification,
    HermesProfileConfiguration,
    HermesProfileResult,
    SubscriptionProviderOption,
)
from bho.core.hermes.profiles import BHO_PROFILE_NAME, ensure_bho_profile
from bho.core.hermes.providers import (
    inspect_subscription_providers,
    run_model_configuration,
)
from bho.core.hermes.verification import (
    inspect_profile_configuration,
    verify_hermes_configuration,
)


@dataclass(frozen=True, slots=True)
class HermesConfigurationPreparation:
    """Describe the state available before interactive configuration."""

    profile: HermesProfileResult
    docker: DockerAvailability
    current: HermesProfileConfiguration
    subscription_providers: tuple[SubscriptionProviderOption, ...]


def prepare_hermes_configuration(
    executable: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> HermesConfigurationPreparation:
    """Verify Docker, ensure the bho profile, and inspect current settings."""
    docker = check_docker_availability(environment=environment)
    if docker.executable is None:
        raise HermesConfigurationError(
            "Docker is required for the bho Hermes profile. Install Docker, "
            "then run `bho hermes configure` again.",
            stage="Docker precondition",
        )
    if not docker.daemon_available:
        detail = f" Detail: {docker.detail}" if docker.detail else ""
        raise HermesConfigurationError(
            "Docker is required for the bho Hermes profile. Start Docker and "
            "ensure the current user can access the daemon, then run "
            f"`bho hermes configure` again.{detail}",
            stage="Docker precondition",
        )

    profile = ensure_bho_profile(executable, environment=environment)
    current = inspect_profile_configuration(
        executable,
        BHO_PROFILE_NAME,
        environment=environment,
    )
    providers = inspect_subscription_providers(
        executable,
        BHO_PROFILE_NAME,
        environment=environment,
    )
    return HermesConfigurationPreparation(
        profile=profile,
        docker=docker,
        current=current,
        subscription_providers=providers,
    )


def apply_and_verify_hermes_configuration(
    executable: Path,
    *,
    reconfigure_model: bool,
    skip_live_check: bool,
    hermes_version: str | None,
    home_dir: Path | None = None,
    data_dir: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> HermesConfigurationVerification:
    """Run selected Hermes setup stages and persist verified non-secret state."""
    env = dict(os.environ if environment is None else environment)
    home = (home_dir or Path.home()).expanduser()
    env.setdefault("HOME", str(home))
    bho_data_dir = data_dir or default_bho_data_dir(home, env)
    remove_configured_profile(bho_data_dir)

    if reconfigure_model:
        run_model_configuration(
            executable,
            BHO_PROFILE_NAME,
            environment=env,
        )

    configure_docker_backend(
        executable,
        BHO_PROFILE_NAME,
        environment=env,
    )
    verification = verify_hermes_configuration(
        executable,
        BHO_PROFILE_NAME,
        skip_live_check=skip_live_check,
        environment=env,
    )
    write_configured_profile(
        bho_data_dir,
        verification,
        hermes_version=hermes_version,
    )
    return verification
