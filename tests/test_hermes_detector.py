"""Tests for Hermes Agent detection."""

import subprocess
from pathlib import Path

from bho.core.hermes.detector import detect_hermes_status


def test_detects_missing_hermes(tmp_path: Path) -> None:
    """Hermes should be reported as absent when it is not in PATH."""
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


def test_detects_installed_configured_and_managed_hermes(tmp_path: Path) -> None:
    """Hermes details should be reported when all local indicators exist."""
    executable = tmp_path / "bin" / "hermes"
    executable.parent.mkdir()
    executable.touch()
    (tmp_path / ".hermes").mkdir()

    data_dir = tmp_path / "bho-data"
    marker = data_dir / "hermes" / "managed.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[str(executable), "--version"],
            returncode=0,
            stdout="Hermes Agent 1.2.3\n",
            stderr="",
        )

    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=data_dir,
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=fake_run,
    )

    assert result.installed is True
    assert result.executable == executable.resolve()
    assert result.version == "1.2.3"
    assert result.configuration_present is True
    assert result.managed_by_bho is True


def test_unknown_version_does_not_fail(tmp_path: Path) -> None:
    """A failed version command should produce an unknown version."""
    executable = tmp_path / "hermes"
    executable.touch()

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[str(executable), "--version"],
            returncode=1,
            stdout="",
            stderr="unsupported option",
        )

    result = detect_hermes_status(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        which_fn=lambda _: str(executable),
        run_fn=fake_run,
    )

    assert result.installed is True
    assert result.version is None
