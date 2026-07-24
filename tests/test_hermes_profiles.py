"""Tests for the dedicated Hermes profile used by bho."""

import subprocess
from pathlib import Path

import pytest

from bho.core.hermes.errors import HermesConfigurationError
from bho.core.hermes.profiles import ensure_bho_profile, inspect_profile


def test_existing_profile_is_reused(tmp_path: Path) -> None:
    """An existing bho profile should not be recreated."""
    profile_path = tmp_path / ".hermes" / "profiles" / "bho"
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout=f"Profile: bho\nPath: {profile_path}\n",
            stderr="",
        )

    result = ensure_bho_profile(tmp_path / "hermes", run_fn=fake_run)

    assert result.created is False
    assert result.path == profile_path
    assert calls == [[str(tmp_path / "hermes"), "profile", "show", "bho"]]


def test_missing_profile_is_created_without_alias(tmp_path: Path) -> None:
    """A new profile must be blank and must not create a shell alias."""
    profile_path = tmp_path / ".hermes" / "profiles" / "bho"
    calls: list[list[str]] = []
    show_count = 0

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal show_count
        calls.append(arguments)
        if arguments[1:3] == ["profile", "show"]:
            show_count += 1
            if show_count == 1:
                return subprocess.CompletedProcess(arguments, 1, stdout="", stderr="missing")
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=f"Profile: bho\nPath: {profile_path}\n",
                stderr="",
            )
        return subprocess.CompletedProcess(arguments, 0, stdout="created", stderr="")

    result = ensure_bho_profile(tmp_path / "hermes", run_fn=fake_run)

    assert result.created is True
    assert result.path == profile_path
    assert calls[1] == [
        str(tmp_path / "hermes"),
        "profile",
        "create",
        "bho",
        "--no-alias",
    ]
    assert "--clone" not in calls[1]
    assert "--clone-all" not in calls[1]


def test_profile_creation_failure_is_reported(tmp_path: Path) -> None:
    """A failed Hermes profile command should raise a structured error."""
    call_count = 0

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return subprocess.CompletedProcess(arguments, 1, stdout="", stderr="missing")
        return subprocess.CompletedProcess(arguments, 2, stdout="", stderr="failed")

    with pytest.raises(HermesConfigurationError, match="could not create") as captured:
        ensure_bho_profile(tmp_path / "hermes", run_fn=fake_run)

    assert captured.value.stage == "profile creation"


def test_inspect_profile_returns_none_on_command_error(tmp_path: Path) -> None:
    """Profile inspection should treat command failure as an absent profile."""
    result = inspect_profile(
        tmp_path / "hermes",
        "bho",
        run_fn=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing")),
    )

    assert result is None
