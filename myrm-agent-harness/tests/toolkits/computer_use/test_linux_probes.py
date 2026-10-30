"""Screen resolution detection of the Linux backend.

Covers:
- xdpyinfo's `dimensions:` line is read first, then xrandr's current-mode line when xdpyinfo is absent or unparsable
- when neither tool answers the 1920x1080 guess is logged, because a wrong resolution shifts every click
- the functional capture probe picks scrot, then gnome-screenshot, and reports False on every failure
- the active window title and mouse position fall back to "" / (0, 0) field by field
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.backends.linux import probes

_XDPYINFO = "screen #0:\n  dimensions:    1280x800 pixels (338x211 millimeters)\n  resolution:    96x96 dots per inch\n"
_XRANDR = "Screen 0: minimum 320 x 200, current 1366 x 768, maximum 16384 x 16384\n   1366x768     60.00*+\n   1024x768     60.00\n"


def _run(outputs: dict[str, str | Exception]) -> MagicMock:
    """subprocess.run stand-in answering by command name; an Exception value raises (tool missing)."""

    def fake(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        outcome = outputs[argv[0]]
        if isinstance(outcome, Exception):
            raise outcome
        return subprocess.CompletedProcess(argv, 0, stdout=outcome, stderr="")

    return MagicMock(side_effect=fake)


class TestDetectLinuxResolution:
    def test_xdpyinfo_dimensions_are_read(self) -> None:
        with patch("subprocess.run", _run({"xdpyinfo": _XDPYINFO, "xrandr": _XRANDR})):
            assert probes.detect_linux_resolution(None) == (1280, 800)

    @pytest.mark.parametrize(
        "xdpyinfo",
        [FileNotFoundError("xdpyinfo"), "no dimensions line here\n"],
        ids=["xdpyinfo-missing", "xdpyinfo-unparsable"],
    )
    def test_xrandr_current_mode_is_used_when_xdpyinfo_gives_nothing(self, xdpyinfo: str | Exception) -> None:
        with patch("subprocess.run", _run({"xdpyinfo": xdpyinfo, "xrandr": _XRANDR})):
            assert probes.detect_linux_resolution(None) == (1366, 768)

    def test_the_environment_is_passed_to_the_tool(self) -> None:
        env = {"DISPLAY": ":99"}
        run = _run({"xdpyinfo": _XDPYINFO, "xrandr": _XRANDR})
        with patch("subprocess.run", run):
            probes.detect_linux_resolution(env)

        assert run.call_args.kwargs["env"] == env

    def test_the_guess_is_logged_when_no_tool_answers(self, caplog: pytest.LogCaptureFixture) -> None:
        missing = FileNotFoundError("tool")
        with (
            patch("subprocess.run", _run({"xdpyinfo": missing, "xrandr": missing})),
            caplog.at_level(logging.WARNING, logger=probes.logger.name),
        ):
            assert probes.detect_linux_resolution(None) == (1920, 1080)

        assert "assuming 1920x1080" in caplog.text

    def test_a_successful_read_logs_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            patch("subprocess.run", _run({"xdpyinfo": _XDPYINFO, "xrandr": _XRANDR})),
            caplog.at_level(logging.WARNING, logger=probes.logger.name),
        ):
            probes.detect_linux_resolution(None)

        assert caplog.text == ""


class TestProbeLinuxCapturable:
    @staticmethod
    def _which(*available: str) -> MagicMock:
        return MagicMock(side_effect=lambda name: f"/usr/bin/{name}" if name in available else None)

    def test_scrot_is_preferred_and_its_png_is_judged(self) -> None:
        run = MagicMock(return_value=subprocess.CompletedProcess([], 0))
        with (
            patch("shutil.which", self._which("scrot", "gnome-screenshot")),
            patch("subprocess.run", run),
            patch(
                "myrm_agent_harness.toolkits.computer_use.capture_probe.png_bytes_look_capturable", return_value=True
            ),
        ):
            assert probes.probe_linux_capturable() is True

        assert run.call_args.args[0][:2] == ["scrot", "-o"]

    def test_gnome_screenshot_is_the_fallback(self) -> None:
        run = MagicMock(return_value=subprocess.CompletedProcess([], 0))
        with (
            patch("shutil.which", self._which("gnome-screenshot")),
            patch("subprocess.run", run),
            patch(
                "myrm_agent_harness.toolkits.computer_use.capture_probe.png_bytes_look_capturable", return_value=True
            ),
        ):
            assert probes.probe_linux_capturable() is True

        assert run.call_args.args[0][:2] == ["gnome-screenshot", "-f"]

    def test_a_blank_png_is_not_capturable(self) -> None:
        with (
            patch("shutil.which", self._which("scrot")),
            patch("subprocess.run", MagicMock(return_value=subprocess.CompletedProcess([], 0))),
            patch(
                "myrm_agent_harness.toolkits.computer_use.capture_probe.png_bytes_look_capturable", return_value=False
            ),
        ):
            assert probes.probe_linux_capturable() is False

    def test_no_screenshot_tool_is_not_capturable(self) -> None:
        run = MagicMock()
        with patch("shutil.which", self._which()), patch("subprocess.run", run):
            assert probes.probe_linux_capturable() is False

        run.assert_not_called()

    @pytest.mark.parametrize(
        "outcome",
        [subprocess.CompletedProcess([], 1), subprocess.TimeoutExpired("scrot", 1.5), OSError("no display")],
        ids=["tool-failed", "timeout", "os-error"],
    )
    def test_tool_failures_are_not_capturable(self, outcome: subprocess.CompletedProcess[bytes] | Exception) -> None:
        run = MagicMock(side_effect=outcome) if isinstance(outcome, Exception) else MagicMock(return_value=outcome)
        with patch("shutil.which", self._which("scrot")), patch("subprocess.run", run):
            assert probes.probe_linux_capturable() is False

    def test_the_temporary_png_is_removed(self) -> None:
        run = MagicMock(return_value=subprocess.CompletedProcess([], 0))
        with (
            patch("shutil.which", self._which("scrot")),
            patch("subprocess.run", run),
            patch(
                "myrm_agent_harness.toolkits.computer_use.capture_probe.png_bytes_look_capturable", return_value=True
            ),
        ):
            probes.probe_linux_capturable()

        assert not Path(run.call_args.args[0][-1]).exists()


class TestReadScreenContext:
    @staticmethod
    def _run(
        title: subprocess.CompletedProcess[str] | Exception, mouse: subprocess.CompletedProcess[str] | Exception
    ) -> MagicMock:
        def fake(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            outcome = title if argv[1] == "getactivewindow" else mouse
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return MagicMock(side_effect=fake)

    @staticmethod
    def _ok(stdout: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")

    def test_title_and_mouse_position_are_read(self) -> None:
        run = self._run(self._ok("Vault - Unlock\n"), self._ok("x:640 y:360 screen:0 window:123\n"))
        with patch("subprocess.run", run):
            context = probes.read_screen_context({"DISPLAY": ":99"})

        assert (context.active_window, context.mouse_x, context.mouse_y) == ("Vault - Unlock", 640, 360)
        assert run.call_args.kwargs["env"] == {"DISPLAY": ":99"}

    def test_failing_tools_leave_the_fields_empty(self) -> None:
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        with patch("subprocess.run", self._run(failed, failed)):
            context = probes.read_screen_context(None)

        assert (context.active_window, context.mouse_x, context.mouse_y) == ("", 0, 0)

    def test_a_missing_tool_leaves_the_fields_empty(self) -> None:
        missing = FileNotFoundError("xdotool")
        with patch("subprocess.run", self._run(missing, missing)):
            context = probes.read_screen_context(None)

        assert (context.active_window, context.mouse_x, context.mouse_y) == ("", 0, 0)

    def test_an_unparsable_mouse_line_does_not_drop_the_title(self) -> None:
        with patch("subprocess.run", self._run(self._ok("Editor\n"), self._ok("garbage"))):
            context = probes.read_screen_context(None)

        assert (context.active_window, context.mouse_x, context.mouse_y) == ("Editor", 0, 0)
