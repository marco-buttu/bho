"""Tests for Hermes Agent CLI commands."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bho.cli import app
from bho.core.docker.models import (
    DockerHostStatus,
    DockerState,
    LinuxDistribution,
)
from bho.core.hermes.errors import (
    HermesOperationError,
    HermesPartialInstallationError,
)
from bho.core.hermes.models import (
    HermesInstallResult,
    HermesStatus,
    HermesUninstallResult,
)

runner = CliRunner()


def _docker_status(
    state: DockerState = DockerState.READY,
    *,
    configured: bool = False,
) -> DockerHostStatus:
    return DockerHostStatus(
        state=state,
        executable=(
            None if state is DockerState.NOT_INSTALLED else Path("/usr/bin/docker")
        ),
        detail=(
            "permission denied while trying to connect to the docker API"
            if state in {
                DockerState.PERMISSION_DENIED,
                DockerState.SESSION_REFRESH_REQUIRED,
            }
            else None
        ),
        current_user="marco",
        docker_group_exists=configured,
        user_configured_for_group=configured,
        group_active_in_session=state is DockerState.READY,
    )


@pytest.fixture
def docker_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "bho.commands.hermes.detect_docker_status",
        lambda: _docker_status(),
    )


def _status(
    *,
    installed: bool = True,
    managed: bool = False,
    configuration_present: bool = True,
) -> HermesStatus:
    return HermesStatus(
        installed=installed,
        executable=Path("/home/user/.local/bin/hermes") if installed else None,
        version="0.19.0" if installed else None,
        configuration_present=configuration_present,
        managed_by_bho=managed,
        installer_source="official-user-installer" if managed else None,
        hermes_install_method="git" if installed else None,
        install_directory=(
            Path("/home/user/.hermes/hermes-agent") if installed else None
        ),
    )


def test_hermes_status_when_not_installed_with_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI should report preserved configuration when Hermes is absent."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False, configuration_present=True),
    )

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert result.stdout.strip().splitlines() == [
        "Hermes Agent: not installed",
        "Configuration: found",
    ]


def test_hermes_status_when_not_installed_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI should distinguish a completely absent Hermes state."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False, configuration_present=False),
    )

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert "Configuration: not found" in result.stdout


def test_hermes_status_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should render separate installer and Hermes metadata."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(managed=True),
    )

    result = runner.invoke(app, ["hermes", "status"])

    assert result.exit_code == 0
    assert "Version: 0.19.0" in result.stdout
    assert "Managed by bho: yes" in result.stdout
    assert "Installer source: official-user-installer" in result.stdout
    assert "Hermes install method: git" in result.stdout
    assert "Configuration: found" in result.stdout


def test_install_when_already_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should not reinstall an existing Hermes installation."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.install_hermes",
        lambda: (_ for _ in ()).throw(AssertionError("Install should not run.")),
    )

    result = runner.invoke(app, ["hermes", "install"])

    assert result.exit_code == 0
    assert "Hermes Agent is already installed." in result.stdout


def test_successful_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should report a verified managed installation."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.install_hermes",
        lambda: HermesInstallResult(_status(managed=True), installed_now=True),
    )

    result = runner.invoke(app, ["hermes", "install"])

    assert result.exit_code == 0
    assert "Installing Hermes Agent non-interactively..." in result.stdout
    assert "Optional setup and gateway stages will be skipped." in result.stdout
    assert "Hermes Agent installed successfully." in result.stdout
    assert "Managed by bho: yes" in result.stdout


def test_partial_install_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """An interrupted installation should report the reconciled state."""
    partial = _status(managed=False)
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.install_hermes",
        lambda: (_ for _ in ()).throw(
            HermesPartialInstallationError("install interrupted", partial)
        ),
    )

    result = runner.invoke(app, ["hermes", "install"])

    assert result.exit_code == 1
    assert "Error: install interrupted" in result.output
    assert "Executable: /home/user/.local/bin/hermes" in result.output
    assert "Managed by bho: no" in result.output
    assert "Run `bho hermes status`" in result.output


def test_install_failure_returns_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Installation errors should be visible and return a failing exit code."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.install_hermes",
        lambda: (_ for _ in ()).throw(HermesOperationError("install failed")),
    )

    result = runner.invoke(app, ["hermes", "install"])

    assert result.exit_code == 1
    assert "Error: install failed" in result.output


def test_uninstall_can_be_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Declining confirmation should leave Hermes untouched."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.uninstall_hermes",
        lambda: (_ for _ in ()).throw(AssertionError("Uninstall should not run.")),
    )

    result = runner.invoke(app, ["hermes", "uninstall"], input="n\n")

    assert result.exit_code == 0
    assert "Uninstall cancelled." in result.stdout


def test_uninstall_yes_skips_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The --yes option should support non-interactive uninstall."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.uninstall_hermes",
        lambda: HermesUninstallResult(True, False, True),
    )

    result = runner.invoke(app, ["hermes", "uninstall", "--yes"])

    assert result.exit_code == 0
    assert "not managed by bho" in result.stdout
    assert "Hermes Agent uninstalled successfully." in result.stdout
    assert "Configuration and user data were preserved." in result.stdout
    assert "hash -r" in result.stdout
    assert "Uninstall Hermes Agent?" not in result.stdout


def test_uninstall_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """An absent installation should be treated as a successful valid state."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False),
    )

    result = runner.invoke(app, ["hermes", "uninstall"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "Hermes Agent is not installed."


def test_uninstall_failure_returns_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uninstall errors should be visible and return a failing exit code."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.uninstall_hermes",
        lambda: (_ for _ in ()).throw(HermesOperationError("uninstall failed")),
    )

    result = runner.invoke(app, ["hermes", "uninstall", "--yes"])

    assert result.exit_code == 1
    assert "Error: uninstall failed" in result.output


def _profile_configuration(
    *,
    configured: bool = True,
) -> "HermesProfileConfiguration":
    from bho.core.hermes.models import HermesProfileConfiguration

    return HermesProfileConfiguration(
        profile_name="bho",
        profile_path=Path("/home/user/.hermes/profiles/bho"),
        provider="openai-codex" if configured else None,
        model="gpt-5.4" if configured else None,
        authentication_configured=configured,
        configured_api_providers=(),
        terminal_backend="docker" if configured else None,
        docker_mount_cwd_to_workspace=True if configured else None,
        docker_run_as_host_user=True if configured else None,
        docker_forward_env_empty=True if configured else None,
        fallback_configured=False,
    )


def _preparation(*, configured: bool = False) -> object:
    from bho.core.hermes.configuration import HermesConfigurationPreparation
    from bho.core.hermes.models import (
        DockerAvailability,
        HermesProfileResult,
        SubscriptionProviderOption,
    )

    return HermesConfigurationPreparation(
        profile=HermesProfileResult(
            name="bho",
            path=Path("/home/user/.hermes/profiles/bho"),
            created=not configured,
        ),
        docker=DockerAvailability(
            executable=Path("/usr/bin/docker"),
            daemon_available=True,
        ),
        current=_profile_configuration(configured=configured),
        subscription_providers=(
            SubscriptionProviderOption(
                provider="openai-codex",
                label="OpenAI Codex via ChatGPT subscription",
                description="Uses ChatGPT OAuth without OpenAI API billing.",
                supported=True,
                authentication_configured=configured,
            ),
        ),
    )


def _verification(*, live: bool | None = True) -> object:
    from bho.core.hermes.models import (
        HermesConfigurationVerification,
        HermesDoctorResult,
    )

    return HermesConfigurationVerification(
        configuration=_profile_configuration(configured=True),
        doctor=HermesDoctorResult(
            completed=True,
            returncode=0,
            summary=None,
        ),
        live_check_passed=live,
        live_check_output="OK" if live else None,
    )


def test_configure_requires_hermes_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configuration must fail clearly when Hermes is absent."""
    monkeypatch.setattr(
        "bho.commands.hermes.detect_hermes_status",
        lambda: _status(installed=False),
    )

    result = runner.invoke(app, ["hermes", "configure"])

    assert result.exit_code == 1
    assert "Hermes Agent is not installed." in result.output
    assert "bho hermes install" in result.output


def test_configure_new_profile_and_skip_live_check(
    monkeypatch: pytest.MonkeyPatch,
    docker_ready: None,
) -> None:
    """The CLI should run the model wizard and report skipped live verification."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.prepare_hermes_configuration",
        lambda executable: _preparation(configured=False),
    )

    def fake_apply(executable: Path, **kwargs: object) -> object:
        calls.append(kwargs)
        return _verification(live=None)

    monkeypatch.setattr(
        "bho.commands.hermes.apply_and_verify_hermes_configuration",
        fake_apply,
    )

    result = runner.invoke(
        app,
        ["hermes", "configure", "--skip-live-check"],
    )

    assert result.exit_code == 0
    assert "Profile status: created" in result.stdout
    assert "OpenAI Codex via ChatGPT subscription" in result.stdout
    assert "Live model check: skipped" in result.stdout
    assert calls[0]["reconfigure_model"] is True
    assert calls[0]["skip_live_check"] is True


def test_configure_existing_profile_can_skip_model_reconfiguration(
    monkeypatch: pytest.MonkeyPatch,
    docker_ready: None,
) -> None:
    """Declining reconfiguration should preserve existing model credentials."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.prepare_hermes_configuration",
        lambda executable: _preparation(configured=True),
    )

    def fake_apply(executable: Path, **kwargs: object) -> object:
        calls.append(kwargs)
        return _verification(live=True)

    monkeypatch.setattr(
        "bho.commands.hermes.apply_and_verify_hermes_configuration",
        fake_apply,
    )

    result = runner.invoke(app, ["hermes", "configure"], input="n\n")

    assert result.exit_code == 0
    assert "Current provider: openai-codex" in result.stdout
    assert "Live model check: passed" in result.stdout
    assert "Hermes Agent is ready for bho." in result.stdout
    assert calls[0]["reconfigure_model"] is False


def test_configure_failure_renders_completed_and_failed_stages(
    monkeypatch: pytest.MonkeyPatch,
    docker_ready: None,
) -> None:
    """Configuration failures should be actionable and return a non-zero code."""
    from bho.core.hermes.errors import HermesConfigurationError

    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.prepare_hermes_configuration",
        lambda executable: _preparation(configured=False),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.apply_and_verify_hermes_configuration",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            HermesConfigurationError(
                "Docker verification failed.",
                stage="Docker backend verification",
                completed_stages=("profile created", "model configured"),
            )
        ),
    )

    result = runner.invoke(app, ["hermes", "configure"])

    assert result.exit_code == 1
    assert "Completed stages:" in result.output
    assert "- profile created" in result.output
    assert "Failed stage:" in result.output
    assert "- Docker backend verification" in result.output


def test_configure_offers_supported_docker_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing Docker should trigger an explicit supported installation offer."""
    statuses = iter((_docker_status(DockerState.NOT_INSTALLED), _docker_status()))
    install_calls: list[LinuxDistribution] = []
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.detect_docker_status",
        lambda: next(statuses),
    )
    distribution = LinuxDistribution(
        distribution_id="linuxmint",
        name="Linux Mint",
        id_like=("ubuntu", "debian"),
        package_manager="apt-get",
    )
    monkeypatch.setattr(
        "bho.commands.hermes.detect_linux_distribution",
        lambda: distribution,
    )
    monkeypatch.setattr(
        "bho.commands.hermes.docker_install_commands",
        lambda current: (
            ("sudo", "apt-get", "update"),
            ("sudo", "apt-get", "install", "-y", "docker.io"),
            ("sudo", "systemctl", "enable", "--now", "docker"),
        ),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.install_docker",
        lambda current: install_calls.append(current),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.prepare_hermes_configuration",
        lambda executable: _preparation(configured=False),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.apply_and_verify_hermes_configuration",
        lambda *args, **kwargs: _verification(live=None),
    )

    result = runner.invoke(
        app,
        ["hermes", "configure", "--skip-live-check"],
        input="y\n",
    )

    assert result.exit_code == 0
    assert "Docker is not installed." in result.stdout
    assert "Detected system: Linux Mint" in result.stdout
    assert "sudo apt-get install -y docker.io" in result.stdout
    assert install_calls == [distribution]


def test_configure_does_not_install_docker_without_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Privileged Docker installation must never run after a declined prompt."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.detect_docker_status",
        lambda: _docker_status(DockerState.NOT_INSTALLED),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.detect_linux_distribution",
        lambda: LinuxDistribution(
            "linuxmint", "Linux Mint", ("ubuntu", "debian"), "apt-get"
        ),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.install_docker",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("Docker installation should not run.")
        ),
    )

    result = runner.invoke(app, ["hermes", "configure"], input="n\n")

    assert result.exit_code == 1
    assert "Docker installation cancelled." in result.stdout


def test_configure_offers_to_start_stopped_docker_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed but stopped daemon should be repairable explicitly."""
    statuses = iter(
        (
            _docker_status(DockerState.DAEMON_STOPPED),
            _docker_status(),
        )
    )
    service_calls: list[str] = []
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.detect_docker_status",
        lambda: next(statuses),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.start_docker_service",
        lambda: service_calls.append("start"),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.prepare_hermes_configuration",
        lambda executable: _preparation(configured=False),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.apply_and_verify_hermes_configuration",
        lambda *args, **kwargs: _verification(live=None),
    )

    result = runner.invoke(
        app,
        ["hermes", "configure", "--skip-live-check"],
        input="y\n",
    )

    assert result.exit_code == 0
    assert "daemon is not running" in result.stdout
    assert service_calls == ["start"]


def test_configure_offers_docker_group_setup_and_requires_new_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Permission repair should be separate and stop until a new login session."""
    group_calls: list[str] = []
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.detect_docker_status",
        lambda: _docker_status(DockerState.PERMISSION_DENIED),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.add_user_to_docker_group",
        lambda user: group_calls.append(user),
    )

    result = runner.invoke(app, ["hermes", "configure"], input="y\n")

    assert result.exit_code == 1
    assert "root-level privileges" in result.stdout
    assert 'Add user "marco" to the docker group?' in result.stdout
    assert "Log out completely and log back in" in result.stdout
    assert group_calls == ["marco"]


def test_configure_reports_inactive_existing_group_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An already configured user should only be asked to refresh the session."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.detect_docker_status",
        lambda: _docker_status(
            DockerState.SESSION_REFRESH_REQUIRED,
            configured=True,
        ),
    )

    result = runner.invoke(app, ["hermes", "configure"])

    assert result.exit_code == 1
    assert "already configured in the docker group" in result.stdout
    assert "Log out completely and log back in" in result.stdout
    assert "Add user" not in result.stdout


def test_configure_rejects_unsupported_automatic_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported hosts should receive a safe manual-installation message."""
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.detect_docker_status",
        lambda: _docker_status(DockerState.NOT_INSTALLED),
    )
    monkeypatch.setattr(
        "bho.commands.hermes.detect_linux_distribution",
        lambda: LinuxDistribution("arch", "Arch Linux", (), None),
    )

    result = runner.invoke(app, ["hermes", "configure"])

    assert result.exit_code == 1
    assert "currently supported only" in result.output
    assert "Install Docker manually" in result.output



def test_configure_does_not_repeat_group_setup_when_membership_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active group membership with denied access needs manual socket diagnosis."""
    status = DockerHostStatus(
        state=DockerState.PERMISSION_DENIED,
        executable=Path("/usr/bin/docker"),
        detail="permission denied",
        current_user="marco",
        docker_group_exists=True,
        user_configured_for_group=True,
        group_active_in_session=True,
    )
    monkeypatch.setattr("bho.commands.hermes.detect_hermes_status", _status)
    monkeypatch.setattr(
        "bho.commands.hermes.detect_docker_status",
        lambda: status,
    )
    monkeypatch.setattr(
        "bho.commands.hermes.add_user_to_docker_group",
        lambda user: (_ for _ in ()).throw(
            AssertionError("Group setup should not be repeated.")
        ),
    )

    result = runner.invoke(app, ["hermes", "configure"])

    assert result.exit_code == 1
    assert "docker group is active" in result.output
    assert "/var/run/docker.sock" in result.output
