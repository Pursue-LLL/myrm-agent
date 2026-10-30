"""Element identity and application scope of the Linux AT-SPI snapshot.

Covers:
- backend_key = "<application>@<pid>:<ordinal>": a snapshot and a later invoke count the same elements, with or
  without a query/role filter, across applications and across instances of one application, and whatever name the
  snapshot reports for the window
- invoke refuses an element whose role or name differs from the snapshot's instead of acting on a moved element
- the foreground snapshot lists the active window's application (matched by process id) and falls back to every
  application when the process cannot be matched
- the name X11 gives the foreground window also resolves a target snapshot of that window's application
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from importlib import reload
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.dref.errors import AXTreeEmptyError
from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef
from myrm_agent_harness.toolkits.computer_use.perception import linux_x11
from myrm_agent_harness.toolkits.computer_use.types import ActionResult


def _button(name: str) -> MagicMock:
    button = MagicMock()
    button.getRoleName.return_value = "push button"
    button.name = name
    button.getState.return_value = MagicMock()
    button.childCount = 0
    extents = MagicMock()
    extents.width = 100
    extents.height = 30
    extents.x = 1
    extents.y = 2
    button.queryComponent.return_value.getExtents.return_value = extents
    button.queryAction.return_value.getNActions.return_value = 1
    return button


def _app(name: str, buttons: list[MagicMock], pid: int | Exception | None = None) -> MagicMock:
    app = MagicMock()
    app.getRoleName.return_value = "application"
    app.name = name
    app.getState.return_value = MagicMock()
    app.childCount = len(buttons)
    app.getChildAtIndex.side_effect = lambda i: buttons[i]
    if isinstance(pid, Exception):
        app.get_process_id.side_effect = pid
    else:
        app.get_process_id.return_value = pid
    return app


def _desktop(apps: list[MagicMock]) -> MagicMock:
    pyatspi = MagicMock()
    desktop = MagicMock()
    desktop.childCount = len(apps)
    desktop.getChildAtIndex.side_effect = lambda i: apps[i]
    pyatspi.Registry.getDesktop.return_value = desktop
    return pyatspi


Loader = Callable[[list[MagicMock]], ModuleType]


@pytest.fixture
def load() -> Iterator[Loader]:
    """Reload linux_ax against a fake AT-SPI desktop; no X11 tool is available unless a test patches the seam."""

    def _load(apps: list[MagicMock]) -> ModuleType:
        from myrm_agent_harness.toolkits.computer_use.perception import linux_ax

        sys.modules["pyatspi"] = _desktop(apps)
        reload(linux_ax)
        return linux_ax

    with patch("subprocess.run", side_effect=OSError("no X11 tools")):
        yield _load
    sys.modules.pop("pyatspi", None)


def _clicked(button: MagicMock) -> bool:
    return bool(button.queryAction.return_value.doAction.called)


def _invoke(linux_ax: ModuleType, ref: ElementRef, action: str = "click") -> ActionResult:
    result: ActionResult = linux_ax.invoke_ax_element(ref.backend_key, action, role=ref.role, name=ref.name)
    return result


class TestOrdinalIsAssignedBeforeFilters:
    def test_a_filtered_ref_invokes_the_element_the_model_saw(self, load: Loader) -> None:
        cancel, send, archive = _button("Cancel"), _button("Send"), _button("Archive")
        linux_ax = load([_app("Mail", [cancel, send, archive])])

        snapshot = linux_ax.capture_ax_snapshot("foreground", query="send")

        (ref,) = snapshot.refs.values()
        assert ref.name == "Send"
        result = _invoke(linux_ax, ref)
        assert result.success is True
        assert _clicked(send)
        assert not _clicked(cancel)
        assert not _clicked(archive)

    def test_each_application_counts_its_own_elements(self, load: Loader) -> None:
        first, second = _button("Open"), _button("Close")
        linux_ax = load([_app("Alpha", [first]), _app("Beta", [second])])

        snapshot = linux_ax.capture_ax_snapshot("foreground")

        assert {ref.backend_key for ref in snapshot.refs.values()} == {"alpha@:0", "beta@:0"}
        assert linux_ax.invoke_ax_element("beta@:0", "click", role="push button", name="Close").success is True
        assert _clicked(second)
        assert not _clicked(first)

    def test_an_application_name_containing_the_separator_round_trips(self, load: Loader) -> None:
        button = _button("Go")
        linux_ax = load([_app("Foo: Bar", [button])])

        (ref,) = linux_ax.capture_ax_snapshot("foreground").refs.values()

        assert ref.backend_key == "foo: bar@:0"
        assert _invoke(linux_ax, ref).success is True
        assert _clicked(button)

    def test_matches_past_the_output_cap_are_still_reachable(self, load: Loader) -> None:
        """The scan bound is separate from the number of refs a snapshot returns."""
        others = [_button("Other") for _ in range(4)]
        send = _button("Send")
        linux_ax = load([_app("Mail", [*others, send])])

        with patch.object(linux_ax, "_MAX_ELEMENTS", 2):
            (ref,) = linux_ax.capture_ax_snapshot("foreground", query="send").refs.values()

        assert ref.backend_key == "mail@:4"
        assert _invoke(linux_ax, ref).success is True
        assert _clicked(send)

    def test_the_scan_bound_limits_the_ordinal_of_an_application(self, load: Loader) -> None:
        buttons = [_button(f"B{i}") for i in range(5)]
        linux_ax = load([_app("Mail", buttons)])

        with patch.object(linux_ax, "_MAX_ORDINAL", 3):
            keys = [ref.backend_key for ref in linux_ax.capture_ax_snapshot("foreground").refs.values()]
            result = linux_ax.invoke_ax_element("mail@:3", "click", role="push button", name="B3")

        assert keys == ["mail@:0", "mail@:1", "mail@:2"]
        assert "out of range" in (result.error or "")

    @pytest.mark.parametrize("key", ["mail", "mail:0", "mail@:x", "mail@:", "mail@x:0", "mail@1.5:0", ""])
    def test_a_malformed_key_is_rejected(self, load: Loader, key: str) -> None:
        linux_ax = load([_app("Mail", [_button("Send")])])

        result = linux_ax.invoke_ax_element(key, "click", role="push button", name="Send")

        assert result.success is False
        assert "Invalid backend_key" in (result.error or "")


class TestIdentityNameDoesNotAddressAtSpi:
    def test_invoke_works_when_x11_names_the_window_differently(self, load: Loader) -> None:
        """The foreground snapshot reports the X11 class; AT-SPI knows the application under another name."""
        button = _button("Open")
        linux_ax = load([_app("nautilus", [button])])

        with patch.object(linux_ax, "read_foreground_meta", return_value=("Org.gnome.Nautilus", "Files")):
            snapshot = linux_ax.capture_ax_snapshot("foreground")

        assert snapshot.meta.app_name == "Org.gnome.Nautilus"
        (ref,) = snapshot.refs.values()
        assert _invoke(linux_ax, ref).success is True
        assert _clicked(button)

    def test_a_target_snapshot_by_the_x11_name_reaches_the_foreground_application(self, load: Loader) -> None:
        linux_ax = load([_app("Slack", [_button("Send")], pid=100), _app("nautilus", [_button("Open")], pid=200)])

        with (
            patch.object(linux_ax, "read_foreground_meta", return_value=("Org.gnome.Nautilus", "Files")),
            patch.object(linux_ax, "foreground_pid", return_value=200),
        ):
            snapshot = linux_ax.capture_ax_snapshot("target", "Org.gnome.Nautilus")

        assert snapshot.meta.scope == "target"
        assert [ref.name for ref in snapshot.refs.values()] == ["Open"]

    def test_a_target_snapshot_by_the_at_spi_name_never_asks_x11(self, load: Loader) -> None:
        linux_ax = load([_app("Slack", [_button("Send")])])

        with patch.object(linux_ax, "read_foreground_meta", side_effect=AssertionError("X11 queried")):
            snapshot = linux_ax.capture_ax_snapshot("target", "slack")

        assert [ref.name for ref in snapshot.refs.values()] == ["Send"]

    def test_the_x11_name_of_another_window_does_not_resolve_a_target(self, load: Loader) -> None:
        linux_ax = load([_app("Slack", [_button("Send")], pid=100)])

        with (
            patch.object(linux_ax, "read_foreground_meta", return_value=("Firefox", "Docs")),
            patch.object(linux_ax, "foreground_pid", return_value=100),
            pytest.raises(AXTreeEmptyError, match="target window not found"),
        ):
            linux_ax.capture_ax_snapshot("target", "Org.gnome.Nautilus")


class TestForegroundListsTheActiveApplication:
    def test_only_the_application_of_the_active_window_is_listed(self, load: Loader) -> None:
        linux_ax = load([_app("Bank", [_button("Hidden")], pid=100), _app("Editor", [_button("Visible")], pid=200)])

        with patch.object(linux_ax, "foreground_pid", return_value=200):
            snapshot = linux_ax.capture_ax_snapshot("foreground")

        assert [ref.name for ref in snapshot.refs.values()] == ["Visible"]
        assert snapshot.meta.app_name == "Editor"

    def test_a_filter_matching_only_another_application_finds_nothing(self, load: Loader) -> None:
        linux_ax = load([_app("Bank", [_button("Transfer")], pid=100), _app("Editor", [_button("Save")], pid=200)])

        with patch.object(linux_ax, "foreground_pid", return_value=200):
            assert linux_ax._try_pyatspi_snapshot(query="transfer") is None

    @pytest.mark.parametrize(
        "active_pid",
        [None, 999],
        ids=["x11-process-unreadable", "no-application-has-that-process"],
    )
    def test_every_application_is_listed_when_the_process_cannot_be_matched(
        self, load: Loader, active_pid: int | None
    ) -> None:
        linux_ax = load([_app("Bank", [_button("Transfer")], pid=100), _app("Editor", [_button("Save")], pid=200)])

        with patch.object(linux_ax, "foreground_pid", return_value=active_pid):
            snapshot = linux_ax.capture_ax_snapshot("foreground")

        assert [ref.name for ref in snapshot.refs.values()] == ["Transfer", "Save"]

    @pytest.mark.parametrize(
        "unreadable",
        [AttributeError("no get_process_id"), 0xFFFFFFFF],
        ids=["no-method", "defunct-application"],
    )
    def test_an_unreadable_application_process_is_never_matched(
        self, load: Loader, unreadable: int | Exception
    ) -> None:
        linux_ax = load(
            [_app("Bank", [_button("Transfer")], pid=unreadable), _app("Editor", [_button("Save")], pid=200)]
        )

        with patch.object(linux_ax, "foreground_pid", return_value=200):
            snapshot = linux_ax.capture_ax_snapshot("foreground")

        assert [ref.name for ref in snapshot.refs.values()] == ["Save"]


class TestForegroundPid:
    @pytest.mark.parametrize(
        ("stdout", "returncode", "expected"),
        [("4242", 0, 4242), ("", 1, None), ("0", 0, None), ("not-a-pid", 0, None), ("-1", 0, None)],
    )
    def test_reads_the_process_of_the_active_window(self, stdout: str, returncode: int, expected: int | None) -> None:
        completed = MagicMock(stdout=stdout + "\n", returncode=returncode)
        with patch("subprocess.run", return_value=completed) as run:
            assert linux_x11.foreground_pid() == expected

        assert run.call_args.args[0] == ["xdotool", "getactivewindow", "getwindowpid"]


class TestInstancesOfOneApplication:
    """Two processes can run the same program: their elements must never be confused."""

    def test_the_foreground_instance_is_the_one_invoked(self, load: Loader) -> None:
        background, foreground = _button("Run"), _button("Run")
        linux_ax = load([_app("Term", [background], pid=100), _app("Term", [foreground], pid=200)])

        with patch.object(linux_ax, "foreground_pid", return_value=200):
            (ref,) = linux_ax.capture_ax_snapshot("foreground").refs.values()
        result = _invoke(linux_ax, ref)

        assert ref.backend_key == "term@200:0"
        assert result.success is True
        assert _clicked(foreground)
        assert not _clicked(background)

    def test_each_instance_counts_its_own_elements(self, load: Loader) -> None:
        first, second = _button("Run"), _button("Run")
        linux_ax = load([_app("Term", [first], pid=100), _app("Term", [second], pid=200)])

        with patch.object(linux_ax, "foreground_pid", return_value=None):
            refs = list(linux_ax.capture_ax_snapshot("foreground").refs.values())

        assert [ref.backend_key for ref in refs] == ["term@100:0", "term@200:0"]
        assert _invoke(linux_ax, refs[1]).success is True
        assert _clicked(second)
        assert not _clicked(first)

    def test_a_restarted_application_does_not_inherit_the_old_elements(self, load: Loader) -> None:
        button = _button("Run")
        linux_ax = load([_app("Term", [button], pid=300)])

        result = linux_ax.invoke_ax_element("term@200:0", "click", role="push button", name="Run")

        assert "Stale element" in (result.error or "")
        assert not _clicked(button)

    def test_an_application_name_containing_both_separators_round_trips(self, load: Loader) -> None:
        button = _button("Go")
        linux_ax = load([_app("a@b: c@", [button], pid=7)])

        (ref,) = linux_ax.capture_ax_snapshot("foreground").refs.values()

        assert ref.backend_key == "a@b: c@@7:0"
        assert _invoke(linux_ax, ref).success is True
        assert _clicked(button)


class TestInvokeRefusesAMovedElement:
    def test_an_element_that_shifted_position_is_not_acted_on(self, load: Loader) -> None:
        send, cancel = _button("Send"), _button("Cancel")
        buttons = [send, cancel]
        linux_ax = load([_app("Mail", buttons, pid=5)])
        (ref, _) = linux_ax.capture_ax_snapshot("foreground").refs.values()

        buttons.reverse()
        result = _invoke(linux_ax, ref)

        assert "Stale element" in (result.error or "")
        assert not _clicked(send)
        assert not _clicked(cancel)

    def test_an_element_that_changed_role_is_not_acted_on(self, load: Loader) -> None:
        button = _button("Send")
        linux_ax = load([_app("Mail", [button], pid=5)])
        (ref,) = linux_ax.capture_ax_snapshot("foreground").refs.values()

        button.getRoleName.return_value = "link"
        result = _invoke(linux_ax, ref)

        assert "Stale element" in (result.error or "")
        assert not _clicked(button)

    def test_an_element_that_kept_role_and_name_is_acted_on(self, load: Loader) -> None:
        button = _button("Send")
        linux_ax = load([_app("Mail", [button], pid=5)])
        (ref,) = linux_ax.capture_ax_snapshot("foreground").refs.values()

        assert _invoke(linux_ax, ref).success is True
        assert _clicked(button)


class TestScopeFallbackIsObservable:
    def test_an_unmatched_foreground_process_is_logged(self, load: Loader, caplog: pytest.LogCaptureFixture) -> None:
        linux_ax = load([_app("Bank", [_button("Transfer")], pid=100)])

        with (
            patch.object(linux_ax, "foreground_pid", return_value=999),
            caplog.at_level(logging.DEBUG, logger=linux_ax.logger.name),
        ):
            linux_ax.capture_ax_snapshot("foreground")

        assert "process 999" in caplog.text

    def test_an_unknown_foreground_process_is_logged(self, load: Loader, caplog: pytest.LogCaptureFixture) -> None:
        linux_ax = load([_app("Bank", [_button("Transfer")], pid=100)])

        with (
            patch.object(linux_ax, "foreground_pid", return_value=None),
            caplog.at_level(logging.DEBUG, logger=linux_ax.logger.name),
        ):
            linux_ax.capture_ax_snapshot("foreground")

        assert "process is unknown" in caplog.text

    def test_an_unresolved_target_is_logged(self, load: Loader, caplog: pytest.LogCaptureFixture) -> None:
        linux_ax = load([_app("Bank", [_button("Transfer")], pid=100)])

        with (
            patch.object(linux_ax, "read_foreground_meta", return_value=("Firefox", "Docs")),
            caplog.at_level(logging.DEBUG, logger=linux_ax.logger.name),
            pytest.raises(AXTreeEmptyError),
        ):
            linux_ax.capture_ax_snapshot("target", "Nautilus")

        assert "'nautilus'" in caplog.text
