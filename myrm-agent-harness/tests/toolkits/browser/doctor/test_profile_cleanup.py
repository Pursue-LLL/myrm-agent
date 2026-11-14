"""Stale browser profile cleanup: only an old, unused, real Playwright profile of this user is ever removed."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest

from myrm_agent_harness.toolkits.browser.doctor import (
    CheckStatus,
    DoctorCheckResult,
    check_orphan_processes,
    cleanup_stale_browser_profiles,
)
from tests.toolkits.browser._stamped_processes import StampedProcesses

_PREFIX = "playwright_chromiumdev_profile-"
_HOUR_S = 3600.0
_PROFILES = "myrm_agent_harness.toolkits.browser.doctor.profiles"
_ORPHAN_CHECK = "myrm_agent_harness.toolkits.browser.doctor.orphan_check"


@pytest.fixture
def temp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The directory ``tempfile.gettempdir()`` returns, so no test reads or removes what is really in the temp directory."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def _profile(temp_dir: Path, suffix: str = "AbC123", *, age_hours: float = 48.0, payload: int = 1000) -> Path:
    """A profile directory holding ``payload`` bytes that last changed ``age_hours`` ago."""
    profile = temp_dir / f"{_PREFIX}{suffix}"
    profile.mkdir()
    (profile / "Local State").write_bytes(b"x" * payload)
    changed = time.time() - age_hours * _HOUR_S
    os.utime(profile, (changed, changed))
    return profile


def _process(command_line: list[str] | Exception) -> MagicMock:
    """A process-table entry whose command line is ``command_line``, or whose read raises it."""
    proc = MagicMock()
    if isinstance(command_line, Exception):
        proc.cmdline.side_effect = command_line
    else:
        proc.cmdline.return_value = command_line
    return proc


def test_dry_run_is_the_default_and_removes_nothing(temp_dir: Path) -> None:
    profile = _profile(temp_dir)

    result = cleanup_stale_browser_profiles()

    assert result == {"pruned": 1, "reclaimed_bytes": 1000, "dry_run": True, "failed": []}
    assert profile.exists()


def test_prune_removes_an_old_unused_profile(temp_dir: Path) -> None:
    profile = _profile(temp_dir, payload=2500)

    result = cleanup_stale_browser_profiles(dry_run=False)

    assert result == {"pruned": 1, "reclaimed_bytes": 2500, "dry_run": False, "failed": []}
    assert not profile.exists()


@pytest.mark.parametrize(("age_hours", "pruned"), [(23.0, 0), (25.0, 1)])
def test_the_default_age_threshold_is_one_day(temp_dir: Path, age_hours: float, pruned: int) -> None:
    profile = _profile(temp_dir, age_hours=age_hours)

    assert cleanup_stale_browser_profiles(dry_run=False)["pruned"] == pruned
    assert profile.exists() is (pruned == 0)


@pytest.mark.parametrize(("max_age_hours", "pruned"), [(1.0, 1), (3.0, 0)])
def test_the_age_threshold_is_the_callers(temp_dir: Path, max_age_hours: float, pruned: int) -> None:
    profile = _profile(temp_dir, age_hours=2.0)

    assert cleanup_stale_browser_profiles(max_age_hours, dry_run=False)["pruned"] == pruned
    assert profile.exists() is (pruned == 0)


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("separate_value", [False, True], ids=["joined", "separate"])
def test_a_profile_a_running_process_uses_is_kept(
    temp_dir: Path, stamped_processes: StampedProcesses, separate_value: bool, dry_run: bool
) -> None:
    live = _profile(temp_dir, "Live01")
    unused = _profile(temp_dir, "Gone01")
    flag = ("--user-data-dir", str(live)) if separate_value else (f"--user-data-dir={live}",)
    stamped_processes.spawn(None, browser=False, extra_args=flag)

    result = cleanup_stale_browser_profiles(dry_run=dry_run)

    assert result["pruned"] == 1
    assert live.exists()
    assert unused.exists() is dry_run


def test_a_running_process_protects_a_profile_whatever_the_spelling_of_its_path(
    temp_dir: Path, tmp_path_factory: pytest.TempPathFactory, stamped_processes: StampedProcesses
) -> None:
    """The temp directory has several spellings (macOS: /var and /private/var); the profile name is what is unique."""
    alias = tmp_path_factory.mktemp("alias") / "temp"
    alias.symlink_to(temp_dir)
    live = _profile(temp_dir, "Live01")
    stamped_processes.spawn(None, browser=False, extra_args=(f"--user-data-dir={alias / live.name}",))

    result = cleanup_stale_browser_profiles(dry_run=False)

    assert result["pruned"] == 0
    assert live.exists()


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("failure", ["os_error", "no_psutil"])
def test_an_unreadable_process_table_protects_every_profile(temp_dir: Path, failure: str, dry_run: bool) -> None:
    """Without the process table "nothing runs" would be a guess, so nothing is reported or removed."""
    profile = _profile(temp_dir)

    if failure == "no_psutil":
        with patch.dict(sys.modules, {"psutil": None}):
            result = cleanup_stale_browser_profiles(dry_run=dry_run)
    else:
        with patch("psutil.process_iter", side_effect=OSError("denied")):
            result = cleanup_stale_browser_profiles(dry_run=dry_run)

    assert result["pruned"] == 0
    assert result["reclaimed_bytes"] == 0
    assert profile.exists()


def test_a_process_that_cannot_be_read_does_not_hide_the_ones_that_can(temp_dir: Path) -> None:
    """Another user's process, one that just exited and psutil's macOS ``SystemError`` are skipped, not fatal."""
    live = _profile(temp_dir, "Live01")
    unused = _profile(temp_dir, "Gone01")
    table = [
        _process(psutil.AccessDenied(pid=1)),
        _process(psutil.NoSuchProcess(pid=2)),
        _process(SystemError("psutil: error reading a process that was just reaped")),
        _process(["/usr/bin/python3"]),
        _process(["chrome", f"--user-data-dir={live}"]),
    ]

    with patch("psutil.process_iter", return_value=table):
        result = cleanup_stale_browser_profiles(dry_run=False)

    assert result["pruned"] == 1
    assert live.exists()
    assert not unused.exists()


def test_the_process_table_is_not_read_while_there_is_nothing_to_prune(temp_dir: Path) -> None:
    _profile(temp_dir, age_hours=1.0)

    with patch("psutil.process_iter") as process_iter:
        result = cleanup_stale_browser_profiles()

    process_iter.assert_not_called()
    assert result["pruned"] == 0


def test_only_playwright_chromium_profiles_directly_in_the_temp_directory_are_touched(temp_dir: Path) -> None:
    nested = temp_dir / "nested"
    nested.mkdir()
    decoys = [
        temp_dir / "playwright_firefoxdev_profile-AbC123",
        temp_dir / "playwright_chromiumdev_profile",
        temp_dir / "chrome-profile-AbC123",
        nested / f"{_PREFIX}AbC123",
    ]
    for decoy in decoys:
        decoy.mkdir()
        os.utime(decoy, (0, 0))
    named_like_a_profile = temp_dir / f"{_PREFIX}file"
    named_like_a_profile.write_text("not a directory")
    os.utime(named_like_a_profile, (0, 0))

    result = cleanup_stale_browser_profiles(dry_run=False)

    assert result["pruned"] == 0
    assert all(path.exists() for path in [*decoys, named_like_a_profile])


def test_a_symlink_named_like_a_profile_is_never_followed(
    temp_dir: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (outside / "keep.txt").write_text("precious")
    link = temp_dir / f"{_PREFIX}Link01"
    link.symlink_to(outside, target_is_directory=True)

    result = cleanup_stale_browser_profiles(max_age_hours=0.0, dry_run=False)

    assert result == {"pruned": 0, "reclaimed_bytes": 0, "dry_run": False, "failed": []}
    assert link.is_symlink()
    assert (outside / "keep.txt").read_text() == "precious"


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="Windows has no user ids")
def test_a_profile_of_another_user_is_left_alone(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _profile(temp_dir)
    other_uid = os.getuid() + 1
    monkeypatch.setattr(os, "getuid", lambda: other_uid)

    result = cleanup_stale_browser_profiles(dry_run=False)

    assert result["pruned"] == 0
    assert profile.exists()


def test_a_removal_that_fails_is_reported_and_not_counted(temp_dir: Path) -> None:
    profile = _profile(temp_dir)

    with patch(f"{_PROFILES}.shutil.rmtree", side_effect=PermissionError("denied")):
        result = cleanup_stale_browser_profiles(dry_run=False)

    assert result["pruned"] == 0
    assert result["reclaimed_bytes"] == 0
    assert result["failed"] == [{"path": str(profile), "reason": "denied"}]
    assert profile.exists()


def test_a_profile_removed_by_someone_else_meanwhile_is_neither_counted_nor_a_failure(temp_dir: Path) -> None:
    _profile(temp_dir)

    with patch(f"{_PROFILES}.shutil.rmtree", side_effect=FileNotFoundError()):
        result = cleanup_stale_browser_profiles(dry_run=False)

    assert result["pruned"] == 0
    assert result["failed"] == []


def test_a_temp_directory_that_cannot_be_read_is_an_empty_result() -> None:
    with patch(f"{_PROFILES}.tempfile.gettempdir", side_effect=FileNotFoundError("no usable temp directory")):
        result = cleanup_stale_browser_profiles(dry_run=False)

    assert result == {"pruned": 0, "reclaimed_bytes": 0, "dry_run": False, "failed": []}


def _check_without_orphans_or_sandboxes() -> DoctorCheckResult:
    """The orphan check with the other two scans pinned to 'nothing found', so only profiles can raise it."""
    with (
        patch(f"{_ORPHAN_CHECK}.find_orphan_automation_processes", return_value=[]),
        patch(f"{_ORPHAN_CHECK}.cleanup_stale_automation_sandboxes", return_value={"pruned": 0, "reclaimed_bytes": 0}),
    ):
        return check_orphan_processes()


def test_the_doctor_check_warns_about_stale_profiles(temp_dir: Path) -> None:
    _profile(temp_dir, "Gone01", payload=3 * 1024 * 1024)
    _profile(temp_dir, "Gone02", payload=1024 * 1024)

    result = _check_without_orphans_or_sandboxes()

    assert result.status is CheckStatus.WARNING
    assert "2 stale browser profile(s) (4.0 MB)" in result.message
    assert result.details is not None
    assert result.details["stale_profiles"] == 2
    assert result.details["stale_profile_bytes"] == 4 * 1024 * 1024


def test_the_doctor_check_is_clean_while_a_browser_uses_the_only_old_profile(
    temp_dir: Path, stamped_processes: StampedProcesses
) -> None:
    live = _profile(temp_dir, "Live01")
    stamped_processes.spawn(None, browser=False, extra_args=(f"--user-data-dir={live}",))

    result = _check_without_orphans_or_sandboxes()

    assert result.status is CheckStatus.OK
    assert result.details is not None
    assert result.details["stale_profiles"] == 0
