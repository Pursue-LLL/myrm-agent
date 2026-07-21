"""Tests for server-side takeover live assist URL enrichment."""

from __future__ import annotations

import pytest

from app.services.agent import streaming


@pytest.mark.asyncio
async def test_injects_live_assist_url_into_browser_takeover_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_create_live_assist_url(
        *,
        chat_id: str | None,
        message_id: str,
        reason: object,
        page_url: object,
        is_managed: bool,
    ) -> str | None:
        assert chat_id == "chat-1"
        assert message_id == "msg-1"
        assert reason == "Complete MFA"
        assert page_url == "https://example.com/login"
        assert is_managed is False
        return "https://assist.example/mobile/takeover/chat-1?pair=pair-token"

    monkeypatch.setattr(streaming, "_create_takeover_live_assist_url", _fake_create_live_assist_url)

    event = {
        "type": "browser_takeover_requested",
        "data": {
            "reason": "Complete MFA",
            "url": "https://example.com/login",
            "is_managed": False,
        },
    }
    updated, cache = await streaming._inject_takeover_live_assist_url(
        event,
        chat_id="chat-1",
        message_id="msg-1",
        cached=None,
    )

    assert isinstance(updated, dict)
    assert updated["data"]["live_assist_url"] == "https://assist.example/mobile/takeover/chat-1?pair=pair-token"
    assert cache is not None
    assert cache[1] == "https://assist.example/mobile/takeover/chat-1?pair=pair-token"


@pytest.mark.asyncio
async def test_reuses_cached_live_assist_url_for_matching_approval_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _should_not_be_called(**_: object) -> str | None:
        raise AssertionError("Unexpected live assist URL re-issue")

    monkeypatch.setattr(streaming, "_create_takeover_live_assist_url", _should_not_be_called)

    cached: streaming.TakeoverLiveAssistCache = (
        "extension|Complete MFA|https://example.com/login",
        "https://assist.example/mobile/takeover/chat-1?pair=pair-token",
    )
    event = {
        "type": "approval_required",
        "data": {
            "action_type": "browser_takeover",
            "payload": {
                "reason": "Complete MFA",
                "url": "https://example.com/login",
                "is_managed": False,
            },
        },
    }
    updated, next_cache = await streaming._inject_takeover_live_assist_url(
        event,
        chat_id="chat-1",
        message_id="msg-1",
        cached=cached,
    )

    assert isinstance(updated, dict)
    assert updated["data"]["payload"]["live_assist_url"] == cached[1]
    assert updated["data"]["live_assist_url"] == cached[1]
    assert next_cache == cached


@pytest.mark.asyncio
async def test_managed_takeover_does_not_inject_live_assist_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_create_live_assist_url(**_: object) -> str | None:
        raise AssertionError("Managed takeover should not issue live assist URL")

    monkeypatch.setattr(streaming, "_create_takeover_live_assist_url", _fake_create_live_assist_url)

    event = {
        "type": "browser_takeover_requested",
        "data": {
            "reason": "Please verify",
            "url": "https://example.com/verify",
            "is_managed": True,
        },
    }
    updated, cache = await streaming._inject_takeover_live_assist_url(
        event,
        chat_id="chat-1",
        message_id="msg-1",
        cached=None,
    )

    assert isinstance(updated, dict)
    assert "live_assist_url" not in updated["data"]
    assert cache is None
