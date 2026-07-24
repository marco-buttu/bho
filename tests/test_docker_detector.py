"""Tests for Docker host-state detection."""

from __future__ import annotations

import grp
import pwd
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bho.core.docker.detector import (
    detect_docker_status,
    detect_linux_distribution,
)
from bho.core.docker.models import DockerState


def _completed(
    stderr: str = "",
    returncode: int = 1,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout="", stderr=stderr)


def test_missing_docker_executable() -> None:
    status = detect_docker_status(
        which_fn=lambda name: None,
        current_user="marco",
        active_group_ids=(),
    )

    assert status.state is DockerState.NOT_INSTALLED
    assert status.executable is None


def test_permission_denied_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        grp,
        "getgrnam",
        lambda name: SimpleNamespace(gr_gid=999, gr_mem=[]),
    )
    monkeypatch.setattr(
        pwd,
        "getpwnam",
        lambda name: SimpleNamespace(pw_gid=1000),
    )

    status = detect_docker_status(
        which_fn=lambda name: str(tmp_path / "docker"),
        run_fn=lambda *args, **kwargs: _completed("permission denied"),
        current_user="marco",
        active_group_ids=(1000,),
    )

    assert status.state is DockerState.PERMISSION_DENIED
    assert status.user_configured_for_group is False


def test_configured_group_requires_new_login(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        grp,
        "getgrnam",
        lambda name: SimpleNamespace(gr_gid=999, gr_mem=["marco"]),
    )
    monkeypatch.setattr(
        pwd,
        "getpwnam",
        lambda name: SimpleNamespace(pw_gid=1000),
    )

    status = detect_docker_status(
        which_fn=lambda name: str(tmp_path / "docker"),
        run_fn=lambda *args, **kwargs: _completed("permission denied"),
        current_user="marco",
        active_group_ids=(1000,),
    )

    assert status.state is DockerState.SESSION_REFRESH_REQUIRED
    assert status.user_configured_for_group is True
    assert status.group_active_in_session is False


def test_stopped_daemon_is_distinguished(tmp_path: Path) -> None:
    status = detect_docker_status(
        which_fn=lambda name: str(tmp_path / "docker"),
        run_fn=lambda *args, **kwargs: _completed(
            "Cannot connect to the Docker daemon. Is the docker daemon running?"
        ),
        current_user="marco",
        active_group_ids=(),
    )

    assert status.state is DockerState.DAEMON_STOPPED


def test_ready_docker(tmp_path: Path) -> None:
    status = detect_docker_status(
        which_fn=lambda name: str(tmp_path / "docker"),
        run_fn=lambda *args, **kwargs: _completed(returncode=0),
        current_user="marco",
        active_group_ids=(),
    )

    assert status.state is DockerState.READY
    assert status.ready is True


def test_linux_mint_is_supported_through_apt(tmp_path: Path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text(
        'NAME="Linux Mint"\nID=linuxmint\nID_LIKE="ubuntu debian"\n',
        encoding="utf-8",
    )

    distribution = detect_linux_distribution(
        os_release_path=os_release,
        which_fn=lambda name: "/usr/bin/apt-get" if name == "apt-get" else None,
    )

    assert distribution.name == "Linux Mint"
    assert distribution.apt_supported is True
