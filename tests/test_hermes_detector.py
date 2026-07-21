"""Tests for Hermes Agent detection."""

import subprocess
from pathlib import Path

from bho.core.hermes.detector import detect_hermes_status
from bho.core.hermes.state import write_managed_installation


def test_detects_missing_hermes(tmp_path: Path) -> None:
    """Hermes should be reported as absent when it is not installed."""
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
    assert result.installation_method is None


def test_detects_official_user_installation_and_version(tmp_path: Path) -> None:
    """The official per-user layout and complete version should be detected."""
    executable = tmp_path / ".local" / "bin" / "hermes"
    executable.parent.mkdir(parents=True)
    executable.touch()
    (tmp_path / ".hermes" / "hermes-agent").mkdir(parents=True)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="Hermes Agent v0.18.2\n",
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
    assert result.executable == executable.resolve()
    assert result.version == "0.18.2"
    assert result.configuration_present is True
    assert result.managed_by_bho is False
    assert result.installation_method == "official-user-installer"


def test_detects_managed_installation(tmp_path: Path) -> None:
    """A marker matching the executable should mark the installation as managed."""
    executable = tmp_path / ".local" / "bin" / "hermes"
    executable.parent.mkdir(parents=True)
    executable.touch()
    (tmp_path / ".hermes" / "hermes-agent").mkdir(parents=True)
    data_dir = tmp_path / "bho-data"

    unmanaged = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=data_dir,
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=_successful_version_run,
    )
    write_managed_installation(data_dir, unmanaged)

    managed = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=data_dir,
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=_successful_version_run,
    )

    assert managed.managed_by_bho is True


def test_falls_back_to_standard_user_executable(tmp_path: Path) -> None:
    """A standard Hermes executable should be detected even when PATH is stale."""
    executable = tmp_path / ".local" / "bin" / "hermes"
    executable.parent.mkdir(parents=True)
    executable.touch()
    (tmp_path / ".hermes" / "hermes-agent").mkdir(parents=True)

    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        which_fn=lambda _: None,
        run_fn=_successful_version_run,
    )

    assert result.installed is True
    assert result.executable == executable.resolve()


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


def test_unknown_version_does_not_fail(tmp_path: Path) -> None:
    """Failed version commands should produce an unknown version."""
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


def _successful_version_run(
    *args: object,
    **kwargs: object,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=args,
        returncode=0,
        stdout="Hermes Agent v0.18.2\n",
        stderr="",
    )
