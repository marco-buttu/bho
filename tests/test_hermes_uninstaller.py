"""Tests for Hermes Agent uninstallation."""

import subprocess
from pathlib import Path

import pytest

from bho.core.hermes.errors import HermesOperationError
from bho.core.hermes.models import HermesStatus
from bho.core.hermes.state import write_managed_installation
from bho.core.hermes.uninstaller import uninstall_hermes


def _status(
    executable: Path | None,
    *,
    installed: bool,
    managed: bool = False,
    configuration_present: bool = True,
    method: str | None = "git",
) -> HermesStatus:
    return HermesStatus(
        installed=installed,
        executable=executable if installed else None,
        version="0.19.0" if installed else None,
        configuration_present=configuration_present,
        managed_by_bho=managed,
        installer_source="official-user-installer" if managed else None,
        hermes_install_method=method if installed else None,
        install_directory=(
            executable.parent.parent.parent / ".hermes" / "hermes-agent"
            if installed and executable is not None
            else None
        ),
    )


def test_uninstalls_managed_hermes_and_removes_marker(tmp_path: Path) -> None:
    """A managed installation should use Hermes own data-preserving uninstaller."""
    data_dir = tmp_path / "bho-data"
    executable = tmp_path / ".local" / "bin" / "hermes"
    executable.parent.mkdir(parents=True)
    executable.touch()
    installed = True

    initial = _status(executable, installed=True)
    write_managed_installation(
        data_dir,
        initial,
        installer_source="official-user-installer",
    )

    def fake_detect(**kwargs: object) -> HermesStatus:
        return _status(
            executable,
            installed=installed,
            managed=installed,
            configuration_present=True,
        )

    def fake_run(
        arguments: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal installed
        assert arguments == [str(executable), "uninstall", "--yes"]
        assert "--full" not in arguments
        installed = False
        executable.unlink()
        return subprocess.CompletedProcess(arguments, 0)

    result = uninstall_hermes(
        home_dir=tmp_path,
        data_dir=data_dir,
        environment={},
        detect_fn=fake_detect,
        run_fn=fake_run,
    )

    assert result.uninstalled_now is True
    assert result.data_preserved is True
    assert not (data_dir / "hermes" / "managed.json").exists()


def test_uninstalls_recognized_unmanaged_installation(tmp_path: Path) -> None:
    """A recognized unmanaged installation may be removed after CLI confirmation."""
    executable = tmp_path / ".local" / "bin" / "hermes"
    installed = True

    def fake_detect(**kwargs: object) -> HermesStatus:
        return _status(executable, installed=installed, method="git")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal installed
        installed = False
        return subprocess.CompletedProcess(args=args, returncode=0)

    result = uninstall_hermes(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        detect_fn=fake_detect,
        run_fn=fake_run,
    )

    assert result.uninstalled_now is True
    assert result.data_preserved is True


def test_missing_hermes_is_a_valid_state(tmp_path: Path) -> None:
    """Uninstalling an absent installation should succeed without running commands."""
    missing = _status(None, installed=False, configuration_present=True)

    result = uninstall_hermes(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        detect_fn=lambda **kwargs: missing,
        run_fn=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Uninstaller should not run.")
        ),
    )

    assert result.already_absent is True
    assert result.data_preserved is True


def test_unknown_unmanaged_installation_is_refused(tmp_path: Path) -> None:
    """An unrecognized unmanaged executable should not be removed automatically."""
    unknown = _status(
        tmp_path / "custom" / "hermes",
        installed=True,
        method="custom",
    )

    with pytest.raises(HermesOperationError, match="could not be identified safely"):
        uninstall_hermes(
            home_dir=tmp_path,
            data_dir=tmp_path / "bho-data",
            environment={},
            detect_fn=lambda **kwargs: unknown,
        )


def test_uninstaller_failure_is_reported(tmp_path: Path) -> None:
    """A non-zero Hermes uninstaller result should fail the operation."""
    installed = _status(tmp_path / "hermes", installed=True, method="git")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=4)

    with pytest.raises(HermesOperationError, match="exit code 4"):
        uninstall_hermes(
            home_dir=tmp_path,
            data_dir=tmp_path / "bho-data",
            environment={},
            detect_fn=lambda **kwargs: installed,
            run_fn=fake_run,
        )


def test_uninstall_verification_failure_is_reported(tmp_path: Path) -> None:
    """A remaining executable after uninstall should fail verification."""
    installed = _status(tmp_path / "hermes", installed=True, method="git")

    with pytest.raises(HermesOperationError, match="still detected"):
        uninstall_hermes(
            home_dir=tmp_path,
            data_dir=tmp_path / "bho-data",
            environment={},
            detect_fn=lambda **kwargs: installed,
            run_fn=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args,
                returncode=0,
            ),
        )


def test_configuration_is_preserved_after_uninstall(tmp_path: Path) -> None:
    """The post-uninstall status may remain configured while the CLI is absent."""
    executable = tmp_path / ".local" / "bin" / "hermes"
    states = [
        _status(executable, installed=True, method="git"),
        _status(None, installed=False, configuration_present=True),
    ]

    result = uninstall_hermes(
        home_dir=tmp_path,
        data_dir=tmp_path / "bho-data",
        environment={},
        detect_fn=lambda **kwargs: states.pop(0),
        run_fn=lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
        ),
    )

    assert result.data_preserved is True
