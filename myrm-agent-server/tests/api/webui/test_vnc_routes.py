"""Unit tests for VNC routes — takeover lifecycle and trace writing."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.vnc import TakeoverState
from myrm_agent_harness.utils.runtime.user_control import get_user_control

from app.api.webui import vnc_routes
from app.api.webui.vnc_routes import (
    _on_takeover_end,
    _on_takeover_start,
    _reflect_in_user_control,
)


@pytest.fixture(autouse=True)
def _reset_module_state() -> Iterator[None]:
    """Reset module-level globals between tests and hand the process-wide control back."""

    def _reset() -> None:
        vnc_routes._pre_takeover_snapshot = ""
        vnc_routes._pre_takeover_url = ""
        vnc_routes._takeover_start_time = 0.0
        vnc_routes._takeover_coordinator = None
        get_user_control().release()

    _reset()
    yield
    _reset()


class TestReflectInUserControl:
    def test_takeover_holds_and_agent_active_releases(self) -> None:
        control = get_user_control()
        generation = control.generation

        _reflect_in_user_control(TakeoverState.USER_TAKEOVER)
        assert control.held is True

        _reflect_in_user_control(TakeoverState.AGENT_ACTIVE)
        assert control.held is False
        assert control.generation == generation + 1

    def test_agent_active_while_idle_changes_nothing(self) -> None:
        control = get_user_control()
        generation = control.generation

        _reflect_in_user_control(TakeoverState.AGENT_ACTIVE)

        assert control.held is False
        assert control.generation == generation

    def test_coordinator_is_wired_to_reflect(self) -> None:
        coordinator = vnc_routes._get_takeover()

        assert coordinator is not None
        assert coordinator.on_state_change is _reflect_in_user_control


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


class TestTakeoverTraceCarriesNoCredential:
    """The trace is written beside the events the logger redacts, so it is redacted before it is written."""

    @pytest.mark.asyncio
    async def test_a_credential_in_the_page_state_is_masked_in_the_written_event(self) -> None:
        secret = "hunter2xyz-takeover"
        vnc_routes._pre_takeover_snapshot = "aria: heading 'Login'"
        vnc_routes._pre_takeover_url = f"https://example.com/login?token={secret}"
        vnc_routes._takeover_start_time = 1000.0

        mock_backend = AsyncMock()
        mock_gateway = MagicMock()
        mock_gateway.get_active_event_log_backend.return_value = ("sess-123", mock_backend)
        post_snapshot = f"aria: heading 'Dashboard'\nDB_PASSWORD={secret}"

        with (
            patch.object(
                vnc_routes,
                "_capture_page_state",
                new_callable=AsyncMock,
                return_value=(post_snapshot, f"https://example.com/dashboard?api_key={secret}"),
            ),
            patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway),
        ):
            await _on_takeover_end("navigated")

        event = mock_backend.append.call_args[0][0][0]
        assert secret not in str(event.data)
        assert event.data.get("reason") == "navigated"
        assert "Dashboard" in str(event.data.get("post_aria_tree"))

    @pytest.mark.asyncio
    async def test_a_credential_that_straddles_the_clip_is_masked_whole(self) -> None:
        secret = "ghp_" + "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5"
        # The clip falls in the middle of the token: 12 of its 40 characters lie before it, too few for a scan to know it.
        tree = "x" * (vnc_routes._ARIA_TREE_LIMIT - 13) + f" {secret} " + "y" * 100

        trace = vnc_routes._redacted_trace("https://a.example", "https://b.example", "pre", tree, "done", 1.5)

        post_tree = trace["post_aria_tree"]
        assert isinstance(post_tree, str)
        assert len(post_tree) <= vnc_routes._ARIA_TREE_LIMIT
        assert "ghp_aB3dE5" not in post_tree
        assert "aB3dE5fG7hI9" not in post_tree
        assert trace["duration_s"] == 1.5

    @pytest.mark.asyncio
    async def test_the_server_log_does_not_carry_the_page_url(self, caplog: pytest.LogCaptureFixture) -> None:
        secret = "hunter2xyz-takeover"
        with (
            caplog.at_level("DEBUG", logger=vnc_routes.logger.name),
            patch.object(
                vnc_routes,
                "_capture_page_state",
                new_callable=AsyncMock,
                return_value=("aria: heading 'Login'", f"https://example.com/login?token={secret}"),
            ),
        ):
            await _on_takeover_start("login")

        assert "pre-snapshot captured" in caplog.text
        assert secret not in caplog.text
