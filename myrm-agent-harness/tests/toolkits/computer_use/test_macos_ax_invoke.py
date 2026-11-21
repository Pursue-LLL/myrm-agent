"""Tests for invoke_ax_element in the macos_ax package and its dispatcher route.

Covers:
- invoke_ax_element: targeted invoke, unsupported actions, timeout, permission, the delivered action of every verb
  (type and scroll are refused as unsupported)
- ax_dispatch.invoke_element: the macOS route passes the app name to the script
"""

from __future__ import annotations

import subprocess
from typing import get_args
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxFailure
from myrm_agent_harness.toolkits.computer_use.perception.macos_ax.invoke import invoke_ax_element
from myrm_agent_harness.toolkits.computer_use.types import DESKTOP_TEXT_ACTIONS, DesktopInteractAction

# fill_credential never reaches the invoker (desktop_interact turns it into fill first); the other two are refused.
_NOT_PERFORMED = {"fill_credential", "type", "scroll"}


class TestInvokeAxElement:
    def test_unsupported_action(self) -> None:
        result = invoke_ax_element("1", "delete")
        assert not result.success
        assert "Unsupported" in result.error

    def test_pattern_actions_supported(self) -> None:
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        with patch(
            "subprocess.run",
            return_value=mock_result,
        ):
            for action_name in ["toggle", "expand", "collapse", "invoke", "check", "uncheck"]:
                result = invoke_ax_element("1", action_name)
                assert result.success

    def test_click_success(self) -> None:
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        with patch(
            "subprocess.run",
            return_value=mock_result,
        ):
            result = invoke_ax_element("1", "click")
            assert result.success

    def test_fill_success(self) -> None:
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        with patch(
            "subprocess.run",
            return_value=mock_result,
        ):
            result = invoke_ax_element("1", "fill", text="hello")
            assert result.success

    def test_targeted_invoke_with_app_name(self) -> None:
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        with patch(
            "subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            result = invoke_ax_element("1", "click", app_name="TextEdit")
            assert result.success
            script_arg = mock_run.call_args[0][0][2]
            assert "TextEdit" in script_arg
            assert "frontmost" not in script_arg

    def test_invoke_without_app_name_uses_frontmost(self) -> None:
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        with patch(
            "subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            result = invoke_ax_element("1", "click")
            assert result.success
            script_arg = mock_run.call_args[0][0][2]
            assert "frontmost" in script_arg

    def test_timeout(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=10),
        ):
            result = invoke_ax_element("1", "click")
            assert not result.success
            assert "timed out" in result.error

    def test_permission_error(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="not allowed assistive access"
        )
        with patch(
            "subprocess.run",
            return_value=mock_result,
        ):
            result = invoke_ax_element("1", "click")
            assert not result.success
            assert "permission" in result.error.lower()

    def test_double_click_normalized(self) -> None:
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        with patch(
            "subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            result = invoke_ax_element("1", "double_click")
            assert result.success
            call_args = mock_run.call_args[0][0]
            assert call_args[3] == "click"

    def test_invoke_failed_returns_error(self) -> None:
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="UNSUPPORTED", stderr="")
        with patch(
            "subprocess.run",
            return_value=mock_result,
        ):
            result = invoke_ax_element("1", "focus")
            assert not result.success

    @pytest.mark.parametrize("action", [a for a in get_args(DesktopInteractAction) if a not in _NOT_PERFORMED])
    def test_every_verb_of_the_tool_vocabulary_is_delivered_as_its_class(self, action: str) -> None:
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = invoke_ax_element("1", action, text="hello")
        assert result.success
        assert mock_run.call_args[0][0][3] == ("fill" if action in DESKTOP_TEXT_ACTIONS else "click")

    @pytest.mark.parametrize("action", ["type", "scroll"])
    def test_a_verb_the_script_cannot_perform_is_refused_as_unsupported(self, action: str) -> None:
        # type is then typed by the caller's coordinate fallback; scroll has no native route on any platform.
        with patch("subprocess.run") as mock_run:
            result = invoke_ax_element("1", action, text="hello")
        assert result.failure is AxFailure.UNSUPPORTED
        mock_run.assert_not_called()


class TestAxDispatchInvokeElement:
    def test_macos_passes_app_name(self) -> None:
        from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import (
            invoke_element,
        )

        mock_backend = MagicMock()
        type(mock_backend).__name__ = "MacOSBackend"
        mock_element = MagicMock()
        mock_element.backend_key = "1"

        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        with patch(
            "subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            result = invoke_element(mock_backend, mock_element, "click", app_name="TextEdit")
            assert result.success
            script_arg = mock_run.call_args[0][0][2]
            assert "TextEdit" in script_arg

    def test_macos_no_app_name(self) -> None:
        from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import (
            invoke_element,
        )

        mock_backend = MagicMock()
        type(mock_backend).__name__ = "MacOSBackend"
        mock_element = MagicMock()
        mock_element.backend_key = "1"

        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        with patch(
            "subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            result = invoke_element(mock_backend, mock_element, "click")
            assert result.success
            script_arg = mock_run.call_args[0][0][2]
            assert "frontmost" in script_arg
