"""Mobile hub pairing enforcement tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.remote_access.router import mobile_sessions
from app.remote_access.pairing import MOBILE_HUB_LIST_PURPOSE, create_pairing_token
from app.remote_access.trust_zone import TrustZone

_MOBILE_SESSIONS_PATH = "/api/v1/remote-access/mobile/sessions"


def _mock_request(*, trust_zone: str) -> MagicMock:
    request = MagicMock()
    request.state.trust_zone = trust_zone
    request.state.session_username = None
    request.url.path = _MOBILE_SESSIONS_PATH
    return request


def _response_body(result: object) -> dict[str, object]:
    if hasattr(result, "body"):
        return json.loads(result.body)
    if isinstance(result, dict):
        return result
    raise TypeError(f"Unexpected mobile_sessions result type: {type(result)!r}")


@pytest.mark.asyncio
async def test_mobile_sessions_requires_pair_on_remote_exposed() -> None:
    request = _mock_request(trust_zone=TrustZone.REMOTE_EXPOSED.value)

    with pytest.raises(HTTPException) as exc_info:
        await mobile_sessions(request, pair=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_mobile_sessions_accepts_valid_pair_on_remote_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _mock_request(trust_zone=TrustZone.REMOTE_EXPOSED.value)
    token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)

    gateway = MagicMock()
    gateway.get_active_sessions.return_value = []
    gateway.config.max_per_user = 2
    gateway.get_available_slots.return_value = 2
    monkeypatch.setattr("app.api.remote_access.router.get_agent_gateway", lambda: gateway)

    result = await mobile_sessions(request, pair=token)
    body = _response_body(result)
    assert body["success"] is True
    assert body["data"]["availableSlots"] == 2


@pytest.mark.asyncio
async def test_mobile_sessions_allows_local_trusted_without_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _mock_request(trust_zone=TrustZone.LOCAL_TRUSTED.value)

    gateway = MagicMock()
    gateway.get_active_sessions.return_value = []
    gateway.config.max_per_user = 2
    gateway.get_available_slots.return_value = 2
    monkeypatch.setattr("app.api.remote_access.router.get_agent_gateway", lambda: gateway)

    result = await mobile_sessions(request, pair=None)
    body = _response_body(result)
    assert body["success"] is True
