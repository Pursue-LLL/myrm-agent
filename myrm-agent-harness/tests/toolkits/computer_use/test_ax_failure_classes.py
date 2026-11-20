"""Failure classes of a native AX action: what each platform invoker proves about delivery.

Covers:
- macOS: a vanished object or list index is STALE; a refused fill is UNSUPPORTED while a failed click is UNKNOWN (its
  script has a second attempt); a timeout, a killed script and an unexpected answer are UNKNOWN; a missing
  permission or Apple-events authorization and an action the invoker has no verb for are UNSUPPORTED
- Linux: a missing AT-SPI, an action the element lacks and a missing editable text interface are UNSUPPORTED;
  a desktop without applications is STALE
- the contract: a delivered action carries no failure, a failed one always carries its class
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef
from myrm_agent_harness.toolkits.computer_use.perception import linux_ax
from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import invoke_element
from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxFailure, AxInvokeResult
from myrm_agent_harness.toolkits.computer_use.perception.macos_ax.invoke import invoke_ax_element

_GONE = "0:6: execution error: 不能获得“item 5 of {1, 2, 3}”。 (-1728)"


def _script_run(stdout: str = "", returncode: int = 0, stderr: str = ""):
    result = subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)
    return patch("subprocess.run", return_value=result)


class TestMacOsScriptFailures:
    @pytest.mark.parametrize(
        ("action", "stderr", "returncode", "expected"),
        [
            ("click", _GONE, 1, AxFailure.STALE),
            ("fill", _GONE, 1, AxFailure.STALE),
            ("click", "System Events got an error: Invalid index. (-1719)", 1, AxFailure.STALE),
            ("fill", "System Events got an error: Can't set value of text field 1. (-10006)", 1, AxFailure.UNSUPPORTED),
            ("click", "System Events got an error: AppleEvent handler failed. (-10000)", 1, AxFailure.UNKNOWN),
            ("click", "Not authorized to send Apple events to System Events. (-1743)", 1, AxFailure.UNSUPPORTED),
            ("fill", "Not authorized to send Apple events to System Events. (-1743)", 1, AxFailure.UNSUPPORTED),
            ("click", "osascript is not allowed assistive access. (-25211)", 1, AxFailure.UNSUPPORTED),
            ("click", "", -9, AxFailure.UNKNOWN),
            ("fill", "", -9, AxFailure.UNKNOWN),
            ("click", "", 1, AxFailure.UNKNOWN),
            ("fill", "", 1, AxFailure.UNSUPPORTED),
        ],
        ids=[
            "click-object-gone",
            "fill-object-gone",
            "click-invalid-index",
            "fill-value-refused",
            "click-handler-failed",
            "click-apple-events-denied",
            "fill-apple-events-denied",
            "click-assistive-denied",
            "click-killed",
            "fill-killed",
            "click-silent-error",
            "fill-silent-error",
        ],
    )
    def test_a_script_error_is_classified_by_what_it_proves(
        self, action: str, stderr: str, returncode: int, expected: AxFailure
    ) -> None:
        with _script_run(returncode=returncode, stderr=stderr):
            result = invoke_ax_element("1", action, "text")

        assert result.success is False
        assert result.failure is expected

    def test_a_missing_accessibility_permission_names_the_permission(self) -> None:
        with _script_run(returncode=1, stderr='"osascript" is not allowed assistive access.'):
            result = invoke_ax_element("1", "click")

        assert result.error == "Accessibility permission required on macOS"
        assert result.failure is AxFailure.UNSUPPORTED

    def test_a_timeout_may_have_delivered_the_action(self) -> None:
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=10)):
            result = invoke_ax_element("1", "click")

        assert result.error == "AX invoke timed out"
        assert result.failure is AxFailure.UNKNOWN

    def test_an_unexpected_answer_may_have_delivered_the_action(self) -> None:
        with _script_run(stdout="done"):
            result = invoke_ax_element("1", "click")

        assert result.success is False
        assert result.failure is AxFailure.UNKNOWN

    def test_a_verb_without_a_script_is_unsupported_and_runs_nothing(self) -> None:
        with patch("subprocess.run") as run:
            result = invoke_ax_element("1", "scroll")

        run.assert_not_called()
        assert result.failure is AxFailure.UNSUPPORTED

    def test_a_delivered_action_carries_no_failure(self) -> None:
        with _script_run(stdout="OK\n"):
            result = invoke_ax_element("1", "click")

        assert result.success is True
        assert result.failure is None


def _button(name: str) -> MagicMock:
    button = MagicMock()
    button.getRoleName.return_value = "push button"
    button.name = name
    button.getState.return_value = MagicMock()
    button.childCount = 0
    extents = MagicMock(width=100, height=30, x=1, y=2)
    button.queryComponent.return_value.getExtents.return_value = extents
    button.queryAction.return_value.getNActions.return_value = 1
    return button


def _atspi_with(apps: list[MagicMock]) -> MagicMock:
    desktop = MagicMock()
    desktop.childCount = len(apps)
    desktop.getChildAtIndex.side_effect = lambda i: apps[i]
    pyatspi = MagicMock()
    pyatspi.Registry.getDesktop.return_value = desktop
    return pyatspi


def _mail_with(button: MagicMock) -> MagicMock:
    app = MagicMock()
    app.getRoleName.return_value = "application"
    app.name = "Mail"
    app.getState.return_value = MagicMock()
    app.childCount = 1
    app.getChildAtIndex.side_effect = lambda _: button
    app.get_process_id.return_value = 5
    return app


class TestLinuxInvokeFailures:
    def test_a_missing_at_spi_is_unsupported(self) -> None:
        with patch.dict(sys.modules, {"pyatspi": None}):
            result = linux_ax.invoke_ax_element("mail@5:0", "click", role="push button", name="Send")

        assert result.failure is AxFailure.UNSUPPORTED

    def test_a_desktop_without_applications_is_stale(self) -> None:
        with patch.dict(sys.modules, {"pyatspi": _atspi_with([])}):
            result = linux_ax.invoke_ax_element("mail@5:0", "click", role="push button", name="Send")

        assert result.failure is AxFailure.STALE

    def test_an_action_the_invoker_has_no_verb_for_is_unsupported(self) -> None:
        with patch.dict(sys.modules, {"pyatspi": _atspi_with([_mail_with(_button("Send"))])}):
            result = linux_ax.invoke_ax_element("mail@5:0", "scroll", role="push button", name="Send")

        assert result.failure is AxFailure.UNSUPPORTED

    def test_a_fill_without_an_editable_text_interface_is_unsupported_and_types_nothing(self) -> None:
        button = _button("Send")
        button.queryEditableText.side_effect = Exception("not editable")
        with patch.dict(sys.modules, {"pyatspi": _atspi_with([_mail_with(button)])}):
            result = linux_ax.invoke_ax_element("mail@5:0", "fill", "secret", role="push button", name="Send")

        assert result.failure is AxFailure.UNSUPPORTED
        assert "secret" not in result.error


class TestContract:
    def test_a_delivered_action_carries_no_failure(self) -> None:
        result = AxInvokeResult.delivered("done")

        assert (result.success, result.output, result.failure) == (True, "done", None)

    @pytest.mark.parametrize("failure", list(AxFailure))
    def test_a_failed_action_carries_its_class_and_error(self, failure: AxFailure) -> None:
        result = AxInvokeResult.failed(failure, "why")

        assert (result.success, result.error, result.failure) == (False, "why", failure)

    def test_an_unsupported_backend_is_unsupported(self) -> None:
        element = ElementRef(ref_id="d0", role="AXButton", name="Go", bbox=BBox(0, 0, 10, 10), backend_key="1")

        result = invoke_element(MagicMock(), element, "click")

        assert result.failure is AxFailure.UNSUPPORTED
