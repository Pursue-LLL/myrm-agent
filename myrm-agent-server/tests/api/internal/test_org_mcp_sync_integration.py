"""Integration: CP org MCP sync → real DB → load → merge → readiness.

Full-chain verification of the org MCP execution path without mocking the
critical merge path:

1. POST /api/admin/org-mcp-sync persists org MCP servers to the UserConfig
   table via the real ConfigService (sensitive config is encrypted at rest).
2. load_user_config_entry() loads the orgMcpServers entry into ``org_mcp_dict``.
3. merge_org_mcp_configs() appends the org servers with ``scope=org``.
4. The readiness MCP check sees a bound org server as configured.
5. The CP token gate rejects requests without the correct token when the
   token is configured.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import httpx
import pytest

from app.core.channel_bridge.config_cache import (
    invalidate_user_configs_cache,
)
from app.database.connection import get_session_factory
from app.database.models import UserConfig
from tests.support.minimal_app import build_minimal_app


def _mount_app() -> httpx.ASGITransport:
    from app.api.internal.org_mcp_sync import router as org_mcp_sync_router

    app = build_minimal_app(register_handlers=False)
    app.include_router(org_mcp_sync_router)
    return httpx.ASGITransport(app=app)


@contextmanager
def _cp_token_env(token: str) -> Iterator[None]:
    os.environ["CONTROL_PLANE_TELEMETRY_TOKEN"] = token
    try:
        yield
    finally:
        os.environ.pop("CONTROL_PLANE_TELEMETRY_TOKEN", None)


@pytest.fixture(autouse=True)
def _cleanup_org_mcp_config() -> None:
    """Remove the orgMcpServers row before and after the test."""
    from sqlalchemy import delete, select

    session_factory = get_session_factory()

    async def _remove() -> None:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(UserConfig).where(UserConfig.config_key == "orgMcpServers")
                )
            ).scalar_one_or_none()
            if row:
                await session.execute(
                    delete(UserConfig).where(UserConfig.config_key == "orgMcpServers")
                )
                await session.commit()
        invalidate_user_configs_cache()

    import asyncio

    asyncio.run(_remove())
    yield
    asyncio.run(_remove())


@pytest.mark.asyncio
async def test_org_mcp_sync_persists_and_merges_full_chain() -> None:
    """CP push → real DB → load_user_configs → merge_org_mcp_configs → readiness."""
    transport = _mount_app()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/org-mcp-sync",
            json={
                "mcp_servers": [
                    {
                        "id": "org-1",
                        "name": "org-crm",
                        "type": "sse",
                        "url": "https://crm.example.com/mcp",
                    }
                ]
            },
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    # Real DB row persisted (encrypted at rest) and decryptable via the
    # real single-config loader.
    from app.core.types import MCPServerConfig

    from app.core.channel_bridge.config_loader import load_user_config_entry
    from app.core.channel_bridge.config_parsers import (
        extract_mcp_configs,
        merge_org_mcp_configs,
    )

    org_mcp_dict = await load_user_config_entry("orgMcpServers")
    assert org_mcp_dict is not None
    assert org_mcp_dict["servers"][0]["name"] == "org-crm"

    merged = merge_org_mcp_configs(
        extract_mcp_configs(None),
        org_mcp_dict,
    )
    org_cfg = next(c for c in merged if c.name == "org-crm")
    assert isinstance(org_cfg, MCPServerConfig)
    assert org_cfg.extra_params == {"scope": "org"}

    # Readiness sees the bound org server as configured (no missing warning).
    from app.services.agent.profile.profile_resolver import ResolvedAgentProfile
    from app.services.agent.readiness.resolver import _check_mcp

    profile = ResolvedAgentProfile(
        agent_id="agent-1",
        skill_ids=(),
        mcp_ids=("org-crm",),
        enabled_builtin_tools=("web_fetch",),
    )
    items = await _check_mcp(profile, None, org_mcp_dict)
    assert not any("not found in config" in item.reason for item in items)


@pytest.mark.asyncio
async def test_org_mcp_sync_rejects_wrong_cp_token() -> None:
    """When CONTROL_PLANE_TELEMETRY_TOKEN is set, a missing/wrong token is 403."""
    transport = _mount_app()
    with _cp_token_env("secret-cp-token"):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/org-mcp-sync",
                json={"mcp_servers": []},
            )
            assert resp.status_code == 403

            resp_ok = await client.post(
                "/api/admin/org-mcp-sync",
                headers={"X-Telemetry-Token": "secret-cp-token"},
                json={"mcp_servers": []},
            )
            assert resp_ok.status_code == 200


@pytest.mark.asyncio
async def test_org_mcp_sync_config_api_can_read_org_mcp() -> None:
    """GET /config/orgMcpServers reads back the synced org MCP (frontend read path)."""
    app = build_minimal_app("config", register_handlers=False)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed org MCP through the real sync endpoint first.
        from app.api.internal.org_mcp_sync import router as org_mcp_sync_router

        sync_app = build_minimal_app(register_handlers=False)
        sync_app.include_router(org_mcp_sync_router)
        sync_transport = httpx.ASGITransport(app=sync_app)
        async with httpx.AsyncClient(
            transport=sync_transport, base_url="http://test"
        ) as sync_client:
            resp = await sync_client.post(
                "/api/admin/org-mcp-sync",
                json={
                    "mcp_servers": [
                        {
                            "id": "org-2",
                            "name": "org-wiki",
                            "type": "sse",
                            "url": "https://wiki.example.com/mcp",
                        }
                    ]
                },
            )
            assert resp.status_code == 200

        resp = await client.get("/api/v1/config/orgMcpServers")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["key"] == "orgMcpServers"
        servers = payload["value"].get("servers", [])
        assert any(s.get("name") == "org-wiki" for s in servers)


@pytest.mark.asyncio
async def test_apply_agent_mcp_selection_respects_org_scope() -> None:
    """Merged org MCP servers participate in per-agent MCP selection.

    The runtime merge appends org servers with ``scope=org``; an agent that
    selects only a user MCP must NOT lose the org server, and an org server
    the agent did not bind must stay filtered out by the same rule as user MCPs.
    """
    from app.core.channel_bridge.config_parsers import (
        extract_mcp_configs,
        merge_org_mcp_configs,
    )
    from app.services.agent.params.mcp_selection import apply_agent_mcp_selection

    user_cfg = extract_mcp_configs(
        {
            "mcpConfigs": [
                {
                    "name": "local-db",
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-sqlite"],
                    "enabled": True,
                }
            ]
        }
    )
    org_mcp_dict = {
        "servers": [
            {
                "id": "org-1",
                "name": "org-crm",
                "type": "sse",
                "url": "https://crm.example.com/mcp",
            }
        ]
    }
    merged = merge_org_mcp_configs(user_cfg, org_mcp_dict)
    assert len(merged) == 2

    # Agent binds only the user MCP -> org server must not appear as a tool
    # source, and the user MCP stays.
    selected = apply_agent_mcp_selection(merged, ("local-db",), None)
    assert [c.name for c in selected] == ["local-db"]

    # Agent binds only the org MCP -> only the org server is selected.
    selected_org = apply_agent_mcp_selection(merged, ("org-crm",), None)
    assert [c.name for c in selected_org] == ["org-crm"]
