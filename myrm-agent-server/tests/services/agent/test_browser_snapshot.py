"""Browser snapshot payload collection tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.browser_snapshot import (
    BrowserSnapshotUnavailableError,
    collect_browser_snapshot_payload,
)


class _FakeBrowserSession:
    pass


@pytest.mark.asyncio
async def test_collect_browser_snapshot_requires_chat_id() -> None:
    with pytest.raises(BrowserSnapshotUnavailableError) as exc_info:
        await collect_browser_snapshot_payload()
    assert exc_info.value.status_code == 400
    assert exc_info.value.error == "missing_chat_id"


@pytest.mark.asyncio
async def test_collect_browser_snapshot_no_active_session() -> None:
    gateway = MagicMock()
    gateway.get_active_browser_session.return_value = None

    with patch("app.services.agent.gateway.get_agent_gateway", return_value=gateway):
        with pytest.raises(BrowserSnapshotUnavailableError) as exc_info:
            await collect_browser_snapshot_payload(chat_id="chat-1")

    gateway.get_active_browser_session.assert_called_once_with(session_id="chat-1")
    assert exc_info.value.status_code == 404
    assert exc_info.value.error == "no_active_browser"


@pytest.mark.asyncio
async def test_collect_browser_snapshot_delegates_to_harness_capture() -> None:
    gateway = MagicMock()
    session = _FakeBrowserSession()
    gateway.get_active_browser_session.return_value = session
    payload = {
        "screenshot_base64": "abc",
        "mime_type": "image/jpeg",
        "refs": {},
        "page_url": "https://example.com",
        "page_title": "Example",
        "viewport_width": 1280,
        "viewport_height": 720,
    }

    with patch("app.services.agent.gateway.get_agent_gateway", return_value=gateway):
        with patch(
            "myrm_agent_harness.toolkits.browser.session.BrowserSession",
            _FakeBrowserSession,
        ):
            with patch(
                "myrm_agent_harness.toolkits.browser.session.view_update_payload.capture_browser_view_update_data",
                new=AsyncMock(return_value=payload),
            ) as capture_mock:
                result = await collect_browser_snapshot_payload(chat_id="chat-1")

    capture_mock.assert_awaited_once_with(session)
    assert result == payload
