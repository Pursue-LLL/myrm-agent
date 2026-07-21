"""Mobile takeover snapshot endpoint authorization and payload tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.remote_access.router import mobile_takeover_snapshot
from app.remote_access.pairing import BROWSER_TAKEOVER_PURPOSE, create_pairing_token
from app.remote_access.trust_zone import TrustZone


def _mock_request(
    *,
    path: str,
    trust_zone: str,
    auth_source: str | None,
    pair_bound_chat_id: str | None,
    session_username: str | None = None,
) -> object:
    state = SimpleNamespace(
        trust_zone=trust_zone,
        auth_source=auth_source,
        pair_bound_chat_id=pair_bound_chat_id,
        session_username=session_username,
    )
    url = SimpleNamespace(path=path, query="")
    return SimpleNamespace(state=state, url=url, headers={})


def _response_body(result: object) -> dict[str, object]:
    if hasattr(result, "body"):
        return json.loads(result.body)
    if isinstance(result, dict):
        return result
    raise TypeError(f"Unexpected mobile_takeover_snapshot result type: {type(result)!r}")


@pytest.mark.asyncio
async def test_mobile_takeover_snapshot_success(monkeypatch: pytest.MonkeyPatch) -> None:
    path = "/api/v1/remote-access/mobile/takeover/chat-a/snapshot"
    request = _mock_request(
        path=path,
        trust_zone=TrustZone.REMOTE_EXPOSED.value,
        auth_source="pair_token",
        pair_bound_chat_id="chat-a",
    )
    token = create_pairing_token(chat_id="chat-a", purpose=BROWSER_TAKEOVER_PURPOSE)

    async def _mock_snapshot(*, session_id: str | None = None) -> dict[str, object]:
        assert session_id == "chat-a"
        return {
            "screenshot_base64": "abc",
            "mime_type": "image/jpeg",
            "refs": {},
            "page_url": "https://example.com",
            "page_title": "Example",
            "viewport_width": 1280,
            "viewport_height": 720,
        }

    monkeypatch.setattr(
        "app.services.agent.browser_snapshot.collect_browser_snapshot_payload",
        _mock_snapshot,
    )

    result = await mobile_takeover_snapshot("chat-a", request, pair=token)
    body = _response_body(result)
    assert body["success"] is True
    assert body["data"]["page_url"] == "https://example.com"


@pytest.mark.asyncio
async def test_mobile_takeover_snapshot_requires_pair_or_session() -> None:
    path = "/api/v1/remote-access/mobile/takeover/chat-a/snapshot"
    request = _mock_request(
        path=path,
        trust_zone=TrustZone.REMOTE_EXPOSED.value,
        auth_source=None,
        pair_bound_chat_id=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await mobile_takeover_snapshot("chat-a", request, pair=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_mobile_takeover_snapshot_rejects_pair_chat_mismatch() -> None:
    path = "/api/v1/remote-access/mobile/takeover/chat-a/snapshot"
    request = _mock_request(
        path=path,
        trust_zone=TrustZone.REMOTE_EXPOSED.value,
        auth_source="pair_token",
        pair_bound_chat_id="chat-b",
    )
    token = create_pairing_token(chat_id="chat-a", purpose=BROWSER_TAKEOVER_PURPOSE)

    with pytest.raises(HTTPException) as exc_info:
        await mobile_takeover_snapshot("chat-a", request, pair=token)

    assert exc_info.value.status_code == 401
