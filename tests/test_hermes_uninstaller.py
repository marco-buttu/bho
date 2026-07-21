"""Tests for Hermes Agent uninstallation."""

import subprocess
from pathlib import Path

import pytest

from bho.core.hermes.errors import HermesOperationError
from bho.core.hermes.models import HermesStatus
from bho.core.hermes.state import write_managed_installation
from bho.core.hermes.uninstaller import uninstall_hermes


def test_uninstalls_managed_hermes_and_removes_marker(tmp_path: Path) -> None:
    """A managed installation should use Hermes own data-preserving uninstaller."""
    data_dir = tmp_path / "bho-data"
    executable = tmp_path / ".local" / "bin" / "hermes"
    executable.parent.mkdir(parents=True)
    executable.touch()
    installed = True

    initial = HermesStatus(
        True,
        executable,
        "0.18.2",
        True,
        False,
        "official-user-installer",
    )
    write_managed_installation(data_dir, initial)

    def fake_detect(**kwargs: object) -> HermesStatus:
        return HermesStatus(
            installed,
            executable if installed else None,
            "0.18.2" if installed else None,
            True,
            installed,
            "official-user-installer" if installed else None,
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
    """A recognized existing installation may be removed after CLI confirmation."""
    executable = tmp_path / ".local" / "bin" / "hermes"
    installed = True

    def fake_detect(**kwargs: object) -> HermesStatus:
        return HermesStatus(
            installed,
            executable if installed else None,
            "0.18.2" if installed else None,
            True,
            False,
            "official-user-installer" if installed else None,
        )

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
    missing = HermesStatus(False, None, None, True, False, None)

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
    unknown = HermesStatus(
        True,
        tmp_path / "custom" / "hermes",
        "0.18.2",
        True,
        False,
        "unknown",
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
    installed = HermesStatus(
        True,
        tmp_path / "hermes",
        "0.18.2",
        True,
        False,
        "official-user-installer",
    )

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
    installed = HermesStatus(
        True,
        tmp_path / "hermes",
        "0.18.2",
        True,
        False,
        "official-user-installer",
    )

    with pytest.raises(HermesOperationError, match="still detected"):
        uninstall_hermes(
            home_dir=tmp_path,
            data_dir=tmp_path / "bho-data",
            environment={},
            detect_fn=lambda **kwargs: installed,
            run_fn=lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=0),
        )
