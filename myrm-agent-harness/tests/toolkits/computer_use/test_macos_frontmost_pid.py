"""Tests for the macOS frontmost-process read that guard_foreground compares before and after a background action.

The window server's stacking order answers first: NSWorkspace only follows focus changes while the process runs an
AppKit run loop, so on its own it can keep naming an application the user already left. NSWorkspace and a System
Events query answer only when the window list cannot. All macOS-only APIs are stubbed: this suite runs on Linux CI.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.backends.macos import background as macos_background
from myrm_agent_harness.toolkits.computer_use.dref.errors import FocusChangedError

_ON_SCREEN_ONLY = 1
_EXCLUDE_DESKTOP = 16
_NULL_WINDOW = 0


def _window(pid: object, layer: int = 0) -> dict[str, object]:
    return {"kCGWindowOwnerPID": pid, "kCGWindowLayer": layer}


@pytest.fixture()
def quartz_stub(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    stub = MagicMock(name="Quartz")
    stub.kCGWindowListOptionOnScreenOnly = _ON_SCREEN_ONLY
    stub.kCGWindowListExcludeDesktopElements = _EXCLUDE_DESKTOP
    stub.kCGNullWindowID = _NULL_WINDOW
    monkeypatch.setitem(sys.modules, "Quartz", stub)
    return stub


def _workspace_naming(pid: int) -> MagicMock:
    """An AppKit stub whose NSWorkspace always answers with `pid`, as a process without a run loop sees it."""
    app = MagicMock()
    app.processIdentifier.return_value = pid
    workspace = MagicMock()
    workspace.frontmostApplication.return_value = app
    ns_workspace = MagicMock()
    ns_workspace.sharedWorkspace.return_value = workspace
    return MagicMock(NSWorkspace=ns_workspace)


class TestWindowListRead:
    def test_owner_of_the_front_most_normal_window(self, quartz_stub: MagicMock) -> None:
        quartz_stub.CGWindowListCopyWindowInfo.return_value = [
            _window(11, layer=25),  # menu-bar item
            _window(22, layer=3),  # floating panel
            _window(300),
            _window(400),
        ]

        assert macos_background._frontmost_pid_window_list() == 300
        quartz_stub.CGWindowListCopyWindowInfo.assert_called_once_with(_ON_SCREEN_ONLY | _EXCLUDE_DESKTOP, _NULL_WINDOW)

    @pytest.mark.parametrize(
        "windows",
        [[], None, [_window(11, layer=25), _window(22, layer=3)]],
        ids=["no window", "no list", "only windows above the applications"],
    )
    def test_without_a_normal_window_the_pid_is_unknown(self, quartz_stub: MagicMock, windows: object) -> None:
        quartz_stub.CGWindowListCopyWindowInfo.return_value = windows

        assert macos_background._frontmost_pid_window_list() is None

    @pytest.mark.parametrize("pid", [0, -1, "nan", None])
    def test_an_unreadable_owner_is_unknown(self, quartz_stub: MagicMock, pid: object) -> None:
        quartz_stub.CGWindowListCopyWindowInfo.return_value = [_window(pid)]

        assert macos_background._frontmost_pid_window_list() is None

    def test_a_window_server_error_is_unknown(self, quartz_stub: MagicMock) -> None:
        quartz_stub.CGWindowListCopyWindowInfo.side_effect = RuntimeError("denied")

        assert macos_background._frontmost_pid_window_list() is None

    def test_a_missing_quartz_is_unknown(self) -> None:
        with patch.dict("sys.modules", {"Quartz": None}):
            assert macos_background._frontmost_pid_window_list() is None


class TestWorkspaceRead:
    def test_no_frontmost_application_or_a_bad_pid_is_unknown(self) -> None:
        workspace = MagicMock()
        workspace.frontmostApplication.return_value = None
        ns = MagicMock()
        ns.sharedWorkspace.return_value = workspace
        with patch.dict("sys.modules", {"AppKit": MagicMock(NSWorkspace=ns)}):
            assert macos_background._frontmost_pid_nsworkspace() is None
        app = MagicMock()
        app.processIdentifier.return_value = 0
        workspace.frontmostApplication.return_value = app
        with patch.dict("sys.modules", {"AppKit": MagicMock(NSWorkspace=ns)}):
            assert macos_background._frontmost_pid_nsworkspace() is None


class TestFrontmostPidFallbackOrder:
    def test_the_window_list_outranks_a_stale_workspace(self) -> None:
        with (
            patch.object(macos_background, "_frontmost_pid_window_list", return_value=300),
            patch.object(macos_background, "_frontmost_pid_nsworkspace", return_value=100) as workspace,
            patch("subprocess.run") as system_events,
        ):
            assert macos_background._frontmost_pid() == 300

        workspace.assert_not_called()
        system_events.assert_not_called()

    def test_the_workspace_answers_when_the_window_list_cannot(self) -> None:
        with (
            patch.object(macos_background, "_frontmost_pid_window_list", return_value=None),
            patch.object(macos_background, "_frontmost_pid_nsworkspace", return_value=777),
            patch("subprocess.run") as system_events,
        ):
            assert macos_background._frontmost_pid() == 777

        system_events.assert_not_called()

    def test_system_events_answers_last(self) -> None:
        with (
            patch.object(macos_background, "_frontmost_pid_window_list", return_value=None),
            patch.object(macos_background, "_frontmost_pid_nsworkspace", return_value=None),
            patch("subprocess.run") as system_events,
        ):
            system_events.return_value = MagicMock(returncode=0, stdout="  888\n")
            assert macos_background._frontmost_pid() == 888

        system_events.assert_called_once()

    def test_every_source_failing_is_unknown(self) -> None:
        with (
            patch.object(macos_background, "_frontmost_pid_window_list", return_value=None),
            patch.object(macos_background, "_frontmost_pid_nsworkspace", return_value=None),
            patch("subprocess.run") as system_events,
        ):
            system_events.side_effect = OSError("no osascript")
            assert macos_background._frontmost_pid() is None
            system_events.side_effect = None
            system_events.return_value = MagicMock(returncode=1, stdout="")
            assert macos_background._frontmost_pid() is None
            system_events.return_value = MagicMock(returncode=0, stdout="abc")
            assert macos_background._frontmost_pid() is None


class TestGuardSeesTheRealForeground:
    def test_a_leak_is_caught_although_the_workspace_never_updates(self, quartz_stub: MagicMock) -> None:
        quartz_stub.CGWindowListCopyWindowInfo.side_effect = [[_window(100)], [_window(200)]]

        with (
            patch.dict("sys.modules", {"AppKit": _workspace_naming(100)}),
            pytest.raises(FocusChangedError, match="Foreground app changed"),
            macos_background.guard_foreground(),
        ):
            pass

    def test_a_stable_foreground_passes(self, quartz_stub: MagicMock) -> None:
        quartz_stub.CGWindowListCopyWindowInfo.side_effect = [[_window(100)], [_window(100)]]

        with patch.dict("sys.modules", {"AppKit": _workspace_naming(999)}), macos_background.guard_foreground():
            pass
