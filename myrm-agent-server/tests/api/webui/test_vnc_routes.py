"""Unit tests for VNC routes — takeover lifecycle and trace writing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.webui import vnc_routes
from app.api.webui.vnc_routes import (
    _on_takeover_end,
    _on_takeover_start,
)


@pytest.fixture(autouse=True)
def _reset_module_state() -> None:
    """Reset module-level globals between tests."""
    vnc_routes._pre_takeover_snapshot = ""
    vnc_routes._pre_takeover_url = ""
    vnc_routes._takeover_start_time = 0.0
    vnc_routes._takeover_coordinator = None


class TestOnTakeoverStart:
    @pytest.mark.asyncio
    async def test_captures_page_state(self) -> None:
        with patch.object(
            vnc_routes,
            "_capture_page_state",
            new_callable=AsyncMock,
            return_value=("aria: heading 'Login'", "https://example.com/login"),
        ):
            await _on_takeover_start("user stuck")

        assert vnc_routes._pre_takeover_snapshot == "aria: heading 'Login'"
        assert vnc_routes._pre_takeover_url == "https://example.com/login"
        assert vnc_routes._takeover_start_time > 0

    @pytest.mark.asyncio
    async def test_handles_empty_capture(self) -> None:
        with patch.object(
            vnc_routes,
            "_capture_page_state",
            new_callable=AsyncMock,
            return_value=("", ""),
        ):
            await _on_takeover_start("no page")

        assert vnc_routes._pre_takeover_snapshot == ""
        assert vnc_routes._pre_takeover_url == ""


class TestOnTakeoverEnd:
    @pytest.mark.asyncio
    async def test_skips_when_no_pre_snapshot(self) -> None:
        vnc_routes._pre_takeover_snapshot = ""
        await _on_takeover_end("done")

    @pytest.mark.asyncio
    async def test_skips_when_no_page_change(self) -> None:
        vnc_routes._pre_takeover_snapshot = "aria: heading 'Page'"
        vnc_routes._pre_takeover_url = "https://example.com"
        vnc_routes._takeover_start_time = 1000.0

        with patch.object(
            vnc_routes,
            "_capture_page_state",
            new_callable=AsyncMock,
            return_value=("aria: heading 'Page'", "https://example.com"),
        ):
            await _on_takeover_end("no change")

        assert vnc_routes._pre_takeover_snapshot == ""

    @pytest.mark.asyncio
    async def test_writes_event_on_page_change(self) -> None:
        vnc_routes._pre_takeover_snapshot = "aria: heading 'Login'"
        vnc_routes._pre_takeover_url = "https://example.com/login"
        vnc_routes._takeover_start_time = 1000.0

        mock_backend = AsyncMock()
        mock_gateway = MagicMock()
        mock_gateway.get_active_event_log_backend.return_value = ("sess-123", mock_backend)

        with (
            patch.object(
                vnc_routes,
                "_capture_page_state",
                new_callable=AsyncMock,
                return_value=("aria: heading 'Dashboard'", "https://example.com/dashboard"),
            ),
            patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway),
        ):
            await _on_takeover_end("navigated")

        mock_backend.append.assert_called_once()
        events = mock_backend.append.call_args[0][0]
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "takeover_trace"
        assert event.session_id == "sess-123"
        assert event.data.get("reason") == "navigated"
        assert event.data.get("pre_url") == "https://example.com/login"
        assert event.data.get("post_url") == "https://example.com/dashboard"

    @pytest.mark.asyncio
    async def test_clears_globals_after_writing(self) -> None:
        vnc_routes._pre_takeover_snapshot = "aria: something"
        vnc_routes._pre_takeover_url = "https://example.com"
        vnc_routes._takeover_start_time = 1000.0

        mock_backend = AsyncMock()
        mock_gateway = MagicMock()
        mock_gateway.get_active_event_log_backend.return_value = ("sess-1", mock_backend)

        with (
            patch.object(
                vnc_routes,
                "_capture_page_state",
                new_callable=AsyncMock,
                return_value=("aria: different", "https://example.com/other"),
            ),
            patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway),
        ):
            await _on_takeover_end("test")

        assert vnc_routes._pre_takeover_snapshot == ""
        assert vnc_routes._pre_takeover_url == ""
        assert vnc_routes._takeover_start_time == 0.0

    @pytest.mark.asyncio
    async def test_handles_no_active_backend(self) -> None:
        vnc_routes._pre_takeover_snapshot = "aria: heading 'Page'"
        vnc_routes._pre_takeover_url = "https://example.com"
        vnc_routes._takeover_start_time = 1000.0

        mock_gateway = MagicMock()
        mock_gateway.get_active_event_log_backend.return_value = None

        with (
            patch.object(
                vnc_routes,
                "_capture_page_state",
                new_callable=AsyncMock,
                return_value=("aria: heading 'New'", "https://example.com/new"),
            ),
            patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway),
        ):
            await _on_takeover_end("no backend")
