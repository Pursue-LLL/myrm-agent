"""Mobile hub pairing enforcement tests."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


def _stub_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize hub payload assembly for auth-semantics tests."""
    monkeypatch.setattr(
        "app.remote_access.mobile_hub_payload.resolve_agent_display_names",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "app.remote_access.mobile_hub_payload.build_recent_sessions",
        AsyncMock(return_value=[]),
    )


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
    _stub_payload(monkeypatch)

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
    _stub_payload(monkeypatch)

    result = await mobile_sessions(request, pair=None)
    body = _response_body(result)
    assert body["success"] is True


@pytest.mark.asyncio
async def test_mobile_sessions_assembles_recent_with_agent_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Active cards get agentName injected; finished chats (minus active ones) form recentSessions."""
    request = _mock_request(trust_zone=TrustZone.LOCAL_TRUSTED.value)

    gateway = MagicMock()
    gateway.get_active_sessions.return_value = [
        {"chatId": "c-active", "agentType": "general", "elapsedSeconds": 2.0, "agentId": "a1"},
    ]
    gateway.config.max_per_user = 3
    gateway.get_available_slots.return_value = 2
    monkeypatch.setattr("app.api.remote_access.router.get_agent_gateway", lambda: gateway)

    agent_row = MagicMock()
    agent_row.id = "a1"
    agent_row.display_name = "Research Agent"
    monkeypatch.setattr(
        "app.services.agent.agent_service.AgentService.get_agent_list",
        AsyncMock(return_value=([agent_row], 1)),
    )

    active_chat = MagicMock()
    active_chat.id = "c-active"
    active_chat.title = "Still Running"
    active_chat.agent_id = "a1"
    active_chat.updated_at = datetime(2026, 10, 2, 3, 0, 0)
    finished_chat = MagicMock()
    finished_chat.id = "c-done"
    finished_chat.title = "Finished Report"
    finished_chat.agent_id = "a1"
    finished_chat.updated_at = datetime(2026, 10, 2, 2, 0, 0)
    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.get_chat_list",
        AsyncMock(return_value=([active_chat, finished_chat], 2)),
    )

    result = await mobile_sessions(request, pair=None)
    body = _response_body(result)
    data = body["data"]

    assert data["activeSessions"][0]["agentName"] == "Research Agent"
    # 活跃会话不重复出现在最近完成区
    assert [item["chatId"] for item in data["recentSessions"]] == ["c-done"]
    assert data["recentSessions"][0] == {
        "chatId": "c-done",
        "title": "Finished Report",
        "agentId": "a1",
        "agentName": "Research Agent",
        "updatedAt": "2026-10-02T02:00:00",
    }


def _stub_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = MagicMock()
    gateway.get_active_sessions.return_value = []
    gateway.config.max_per_user = 2
    gateway.get_available_slots.return_value = 2
    monkeypatch.setattr("app.api.remote_access.router.get_agent_gateway", lambda: gateway)
    _stub_payload(monkeypatch)


@pytest.mark.asyncio
async def test_mobile_sessions_reports_curtain_unavailable_without_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非桌面端部署（无状态桥）：curtain.available=False，手机端据此隐藏帷幕胶囊。"""
    monkeypatch.delenv("MYRM_CURTAIN_STATE_FILE", raising=False)
    _stub_gateway(monkeypatch)

    result = await mobile_sessions(_mock_request(trust_zone=TrustZone.LOCAL_TRUSTED.value), pair=None)
    curtain = _response_body(result)["data"]["curtain"]

    assert curtain == {"available": False, "active": False}


@pytest.mark.asyncio
async def test_mobile_sessions_reports_live_curtain_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """桌面端部署：hub payload 透出真实帷幕态（无人值守时手机可见「屏幕已保护」）。"""
    state_file = tmp_path / "curtain_state.json"
    state_file.write_text(
        json.dumps(
            {
                "active": True,
                "autoEngaged": True,
                "lastPhysicalInputMs": 0,
                "pendingAutoUnlock": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MYRM_CURTAIN_STATE_FILE", str(state_file))
    _stub_gateway(monkeypatch)

    result = await mobile_sessions(_mock_request(trust_zone=TrustZone.LOCAL_TRUSTED.value), pair=None)
    curtain = _response_body(result)["data"]["curtain"]

    assert curtain == {
        "available": True,
        "active": True,
        "autoEngaged": True,
        "pendingAutoUnlock": False,
    }
