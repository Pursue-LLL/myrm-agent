"""The multimodal reply of a desktop vision action: what the model is told about the frame, and when it is not shown.

The checks before an action vouch only for the screen it started from. The frame that comes back is checked once
more against the application in front of it: when that one is sensitive the model gets the text and no pixels.
"""

from __future__ import annotations

import time
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.types import (
    ActionResult,
    ComputerUseConfig,
    ScreenContext,
    ScreenInfo,
)

_VISION = "myrm_agent_harness.toolkits.computer_use.desktop_session.vision"
_STARTED_IN_NOTES = {"app_name": "Notes", "window_title": "", "app_id": ""}
_FRAME = "SECRETFRAMEBASE64"  # what must never reach the model from a sensitive screen


def _shown(reply: str | list[object]) -> list[dict[str, str]]:
    """The reply as content blocks; fails when the frame was withheld."""
    assert isinstance(reply, list), reply
    return cast("list[dict[str, str]]", reply)


def _frame(output: str = "") -> ActionResult:
    return ActionResult(success=True, screenshot_base64=_FRAME, screenshot_size=(960, 540), output=output)


def _session_in_front(active_window: str) -> DesktopSession:
    """A session whose backend reports *active_window* as the foreground when a reply is built."""
    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=2.0)
    backend.screen_context.return_value = ScreenContext(active_window=active_window, mouse_x=500, mouse_y=300)
    session = DesktopSession(backend=backend, config=ComputerUseConfig())
    session._last_snapshot_time = time.time()
    return session


class TestBuildScreenshotResponse:
    """DesktopSession multimodal response formatting."""

    def test_basic_response_structure(self) -> None:
        session = _session_in_front("Chrome")

        blocks = _shown(session._build_multimodal_response(_frame(), "Click done."))

        assert len(blocks) == 2
        text = blocks[0]["text"]
        assert "Click done." in text
        assert "1920x1080" in text
        assert "960x540" in text
        assert "Chrome" in text
        assert "(500, 300)" in text
        assert blocks[1]["base64"] == _FRAME

    def test_response_without_an_active_window(self) -> None:
        session = _session_in_front("")

        blocks = _shown(session._build_multimodal_response(_frame(), "Screenshot captured."))

        assert "Active window" not in blocks[0]["text"]

    def test_response_with_output(self) -> None:
        session = _session_in_front("Notes")

        blocks = _shown(session._build_multimodal_response(_frame("Window text extracted."), "Done."))

        assert "Window text extracted." in blocks[0]["text"]


class TestAFrameInFrontOfASensitiveApplication:
    @pytest.mark.parametrize("front", ["1Password 7", "Terminal", "Signal", "Cursor"])
    def test_the_reply_is_text_only_and_says_why(self, front: str) -> None:
        session = _session_in_front(front)

        reply = session._build_multimodal_response(_frame(), "Vision action 'key' completed.")

        assert isinstance(reply, str)
        assert reply.startswith("Vision action 'key' completed. The screen is not shown. Safety: Blocked:")
        assert front in reply
        assert _FRAME not in reply

    def test_an_unreadable_foreground_keeps_the_frame(self) -> None:
        """Like the checks before an action: an application that cannot be named is not a reason to refuse."""
        session = _session_in_front("")

        assert _shown(session._build_multimodal_response(_frame(), "Done."))[1]["base64"] == _FRAME

    @pytest.mark.asyncio
    async def test_an_action_that_ends_on_it_is_done_and_not_shown(self) -> None:
        session = _session_in_front("1Password")

        with (
            patch(f"{_VISION}.inspect_backend", return_value=_STARTED_IN_NOTES),
            patch.object(session, "key_press", AsyncMock(return_value=_frame())) as key_press,
        ):
            reply = await session.desktop_vision_action(action="key", text="Return")

        key_press.assert_awaited_once_with("Return")
        assert isinstance(reply, str)
        assert reply.startswith("Vision action 'key' completed. The screen is not shown.")
        assert _FRAME not in reply

    @pytest.mark.asyncio
    async def test_a_capture_whose_frame_shows_it_is_not_shown(self) -> None:
        session = _session_in_front("Signal")

        with (
            patch(f"{_VISION}.inspect_backend", return_value=_STARTED_IN_NOTES),
            patch.object(session, "take_screenshot", AsyncMock(return_value=_frame())) as take_screenshot,
        ):
            reply = await session.desktop_vision_capture()

        take_screenshot.assert_awaited_once()
        assert isinstance(reply, str)
        assert reply.startswith("Desktop vision capture. The screen is not shown.")
        assert _FRAME not in reply


class TestAFrameInFrontOfAnOrdinaryApplication:
    @pytest.mark.asyncio
    async def test_an_action_returns_the_frame(self) -> None:
        session = _session_in_front("Notes")

        with (
            patch(f"{_VISION}.inspect_backend", return_value=_STARTED_IN_NOTES),
            patch.object(session, "key_press", AsyncMock(return_value=_frame())),
        ):
            blocks = _shown(await session.desktop_vision_action(action="key", text="Return"))

        assert blocks[1]["base64"] == _FRAME

    @pytest.mark.asyncio
    async def test_a_capture_returns_the_frame(self) -> None:
        session = _session_in_front("Notes")

        with (
            patch(f"{_VISION}.inspect_backend", return_value=_STARTED_IN_NOTES),
            patch.object(session, "take_screenshot", AsyncMock(return_value=_frame())),
        ):
            blocks = _shown(await session.desktop_vision_capture())

        assert blocks[1]["base64"] == _FRAME
