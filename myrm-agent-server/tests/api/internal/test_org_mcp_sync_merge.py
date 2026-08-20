"""Org MCP sync → load_user_configs → converter merge chain.

Verifies the Control Plane push path (``POST /api/admin/org-mcp-sync``) reaches
the live agent params: config write → config cache load → org server merge →
``params.mcp_cfg`` on the General Agent request.
"""

from __future__ import annotations

import os
import sys
from typing import Iterator

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.database.connection import get_session_factory
from app.database.models import UserConfig
from tests.support.minimal_app import build_minimal_app


def _mount_app() -> httpx.ASGITransport:
    from app.api.internal.org_policy_sync.org_mcp_sync import router as org_mcp_sync_router

    app = build_minimal_app(register_handlers=False)
    app.include_router(org_mcp_sync_router)
    return httpx.ASGITransport(app=app)


@pytest.fixture
async def _cleanup() -> Iterator[None]:
    session_factory = get_session_factory()

    async def _remove() -> None:
        async with session_factory() as session:
            for key in ("orgMcpServers", "providers"):
                row = (await session.execute(select(UserConfig).where(UserConfig.config_key == key))).scalar_one_or_none()
                if row:
                    await session.execute(delete(UserConfig).where(UserConfig.config_key == key))
            await session.commit()
        invalidate_user_configs_cache()

    await _remove()
    yield
    await _remove()


async def _seed_providers() -> None:
    """Write an enabled provider so model resolution can proceed in the converter."""
    basic_model = os.environ.get("BASIC_MODEL", "agnes-2.5-flash")
    basic_key = os.environ.get("BASIC_API_KEY", "test-key")
    basic_url = os.environ.get("BASIC_BASE_URL", "https://apihub.agnes-ai.com/v1")
    providers_dict = {
        "defaultModelConfig": {"baseModel": {"primary": {"providerId": "test-provider", "model": basic_model}}},
        "providers": [
            {
                "id": "test-provider",
                "providerType": "openai",
                "isEnabled": True,
                "apiUrl": basic_url,
                "apiKeys": [{"key": basic_key, "isActive": True}],
                "enabledModels": [basic_model],
            }
        ],
    }
    from app.database.models.config import UserConfig as _UC

    async with get_session_factory()() as session:
        session.add(
            _UC(
                id="test-providers",
                config_key="providers",
                config_value=providers_dict,
                version="1_0",
                last_device_id="org-sync-test",
            )
        )
        await session.commit()
    invalidate_user_configs_cache()


@pytest.mark.asyncio
async def test_org_mcp_reaches_agent_params(_cleanup: None) -> None:
    await _seed_providers()

    transport = _mount_app()
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/org-mcp-sync",
            json={
                "mcp_servers": [
                    {
                        "id": "org-1",
                        "name": "org-probe",
                        "type": "stdio",
                        "command": sys.executable,
                        "args": ["tests/support/e2e_minimal_stdio_mcp_server.py"],
                        "description": "org probe",
                    }
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["count"] == 1

    from app.core.channel_bridge.config_loader import load_user_configs

    configs = await load_user_configs()
    assert configs is not None
    org_servers = (configs.org_mcp_dict or {}).get("servers") or []
    assert any(s.get("name") == "org-probe" for s in org_servers)

    from app.core.channel_bridge.config_parsers import merge_org_mcp_configs

    merged = merge_org_mcp_configs([], configs.org_mcp_dict)
    assert [c.name for c in merged] == ["org-probe"]

    from app.services.agent.params.converter import convert_to_general_agent_params
    from app.services.agent.params.models import AgentRequest

    request = AgentRequest(
        message_id="msg-org-probe",
        chat_id="chat-org-probe",
        content="请调用 org-probe MCP 的 ping 工具",
        action_mode="agent",
        model_selection={"providerId": "test-provider", "model": "agnes-2.5-flash"},
    )
    params, routing, warnings, archive = await convert_to_general_agent_params(request, [["user", "hello"]])
    mcp_names = [(c.name, c.type) for c in (params.mcp_cfg or [])]
    assert ("org-probe", "stdio") in mcp_names
