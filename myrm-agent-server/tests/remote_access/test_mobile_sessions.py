"""Mobile hub pairing enforcement tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.remote_access.router import mobile_sessions
from app.remote_access.pairing import create_pairing_token
from app.remote_access.trust_zone import TrustZone


@pytest.mark.asyncio
async def test_mobile_sessions_requires_pair_on_remote_exposed() -> None:
    request = MagicMock()
    request.state.trust_zone = TrustZone.REMOTE_EXPOSED.value

    with pytest.raises(HTTPException) as exc_info:
        await mobile_sessions(request, pair=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_mobile_sessions_accepts_valid_pair_on_remote_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    request = MagicMock()
    request.state.trust_zone = TrustZone.REMOTE_EXPOSED.value
    token = create_pairing_token()

    gateway = MagicMock()
    gateway.get_active_sessions.return_value = []
    gateway.config.max_per_user = 2
    gateway.get_available_slots.return_value = 2
    monkeypatch.setattr("app.api.remote_access.router.get_agent_gateway", lambda: gateway)

    result = await mobile_sessions(request, pair=token)
    assert result["success"] is True
    assert result["data"]["availableSlots"] == 2


@pytest.mark.asyncio
async def test_mobile_sessions_allows_local_trusted_without_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    request = MagicMock()
    request.state.trust_zone = TrustZone.LOCAL_TRUSTED.value

    gateway = MagicMock()
    gateway.get_active_sessions.return_value = []
    gateway.config.max_per_user = 2
    gateway.get_available_slots.return_value = 2
    monkeypatch.setattr("app.api.remote_access.router.get_agent_gateway", lambda: gateway)

    result = await mobile_sessions(request, pair=None)
    assert result["success"] is True
