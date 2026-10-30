"""Screen resolution detection of the Linux backend.

Covers:
- xdpyinfo's `dimensions:` line is read first, then xrandr's current-mode line when xdpyinfo is absent or unparsable
- when neither tool answers the 1920x1080 guess is logged, because a wrong resolution shifts every click
"""

from __future__ import annotations

import logging
import subprocess
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
