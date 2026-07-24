"""Tests for Hermes Agent detection."""

import subprocess
from pathlib import Path

from bho.core.hermes.detector import detect_hermes_status
from bho.core.hermes.state import write_managed_installation


def test_detects_missing_hermes_without_configuration(tmp_path: Path) -> None:
    """Hermes should be reported as absent when no executable or data exists."""
    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        which_fn=lambda _: None,
    )

    assert result.installed is False
    assert result.executable is None
    assert result.version is None
    assert result.configuration_present is False
    assert result.managed_by_bho is False
    assert result.installer_source is None
    assert result.hermes_install_method is None
    assert result.install_directory is None


def test_detects_configuration_when_executable_is_absent(tmp_path: Path) -> None:
    """Configuration detection must not depend on executable detection."""
    (tmp_path / ".hermes").mkdir()

    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        which_fn=lambda _: None,
    )

    assert result.installed is False
    assert result.configuration_present is True


def test_detects_custom_hermes_home_when_executable_is_absent(tmp_path: Path) -> None:
    """HERMES_HOME should be considered even when Hermes is not installed."""
    custom_home = tmp_path / "custom-hermes"
    custom_home.mkdir()

    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={"HERMES_HOME": str(custom_home)},
        which_fn=lambda _: None,
    )

    assert result.configuration_present is True


def test_detects_complete_metadata_from_version_output(tmp_path: Path) -> None:
    """Version, install directory, and Hermes install method should be parsed."""
    executable = tmp_path / ".local" / "bin" / "hermes"
    executable.parent.mkdir(parents=True)
    executable.touch()
    install_directory = tmp_path / ".hermes" / "hermes-agent"
    install_directory.mkdir(parents=True)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=(
                "Hermes Agent v0.19.0 (2026.7.20)\n"
                f"Install directory: {install_directory}\n"
                "Install method: git\n"
            ),
            stderr="",
        )

    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=fake_run,
    )

    assert result.installed is True
    assert result.executable == executable.absolute()
    assert result.version == "0.19.0"
    assert result.configuration_present is True
    assert result.managed_by_bho is False
    assert result.installer_source is None
    assert result.hermes_install_method == "git"
    assert result.install_directory == install_directory


def test_detects_managed_installation(tmp_path: Path) -> None:
    """A marker matching all known metadata should mark Hermes as managed."""
    executable = tmp_path / ".local" / "bin" / "hermes"
    executable.parent.mkdir(parents=True)
    executable.touch()
    install_directory = tmp_path / ".hermes" / "hermes-agent"
    install_directory.mkdir(parents=True)
    data_dir = tmp_path / "bho-data"

    unmanaged = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=data_dir,
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=_metadata_run(install_directory),
    )
    write_managed_installation(
        data_dir,
        unmanaged,
        installer_source="official-user-installer",
    )

    managed = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=data_dir,
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=_metadata_run(install_directory),
    )

    assert managed.managed_by_bho is True
    assert managed.installer_source == "official-user-installer"


def test_stale_marker_is_not_treated_as_managed(tmp_path: Path) -> None:
    """A changed Hermes version should invalidate the old management marker."""
    executable = tmp_path / ".local" / "bin" / "hermes"
    executable.parent.mkdir(parents=True)
    executable.touch()
    install_directory = tmp_path / ".hermes" / "hermes-agent"
    install_directory.mkdir(parents=True)
    data_dir = tmp_path / "bho-data"

    old_status = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=data_dir,
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=_metadata_run(install_directory, version="0.18.2"),
    )
    write_managed_installation(
        data_dir,
        old_status,
        installer_source="official-user-installer",
    )

    changed = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=data_dir,
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=_metadata_run(install_directory, version="0.19.0"),
    )

    assert changed.managed_by_bho is False
    assert changed.installer_source is None


def test_ignores_stale_shell_cache_path(tmp_path: Path) -> None:
    """A non-existent path returned by which should not count as installed."""
    stale = tmp_path / ".local" / "bin" / "hermes"

    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        which_fn=lambda _: str(stale),
    )

    assert result.installed is False


def test_falls_back_to_standard_user_executable(tmp_path: Path) -> None:
    """A standard executable should be detected when PATH is stale or missing."""
    executable = tmp_path / ".local" / "bin" / "hermes"
    executable.parent.mkdir(parents=True)
    executable.touch()

    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        which_fn=lambda _: None,
        run_fn=_metadata_run(tmp_path / ".hermes" / "hermes-agent"),
    )

    assert result.installed is True
    assert result.executable == executable.absolute()


def test_version_command_falls_back_to_dash_dash_version(tmp_path: Path) -> None:
    """Older Hermes installations using --version should remain supported."""
    executable = tmp_path / "hermes"
    executable.touch()
    calls: list[list[str]] = []

    def fake_run(
        arguments: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if arguments[-1] == "version":
            return subprocess.CompletedProcess(arguments, 1, "", "unsupported")
        return subprocess.CompletedProcess(arguments, 0, "Hermes Agent v0.18.2", "")

    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=fake_run,
    )

    assert result.version == "0.18.2"
    assert [call[-1] for call in calls] == ["version", "--version"]


def test_unknown_metadata_does_not_fail(tmp_path: Path) -> None:
    """Failed version commands should produce unknown metadata."""
    executable = tmp_path / "hermes"
    executable.touch()

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="error")

    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=fake_run,
    )

    assert result.installed is True
    assert result.version is None
    assert result.hermes_install_method is None
    assert result.install_directory is None


def _metadata_run(
    install_directory: Path,
    *,
    version: str = "0.19.0",
):
    def fake_run(
        *args: object,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=(
                f"Hermes Agent v{version}\n"
                f"Install directory: {install_directory}\n"
                "Install method: git\n"
            ),
            stderr="",
        )

    return fake_run
