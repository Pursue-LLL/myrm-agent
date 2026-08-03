"""Tests for MCP runtime config preparation (secrets + OAuth injection)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.mcp.config import MCPConfig


@pytest.mark.asyncio
async def test_prepare_returns_copy_when_agent_or_configs_missing() -> None:
    from app.services.agent.mcp_runtime_prepare import prepare_mcp_configs_for_runtime

    cfg = MCPConfig(name="demo", type="stdio", command="echo")
    assert await prepare_mcp_configs_for_runtime(None, [cfg]) == [cfg]
    assert await prepare_mcp_configs_for_runtime("agent-1", []) == []


@pytest.mark.asyncio
async def test_prepare_injects_stdio_required_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.agent.mcp_runtime_prepare import prepare_mcp_configs_for_runtime

    cfg = MCPConfig(
        name="stdio-mcp",
        type="stdio",
        command="echo",
        required_secrets=["API_KEY"],
        extra_params={"env": {"BASE": "1"}},
    )

    secret_store = AsyncMock()
    secret_store.get_all_secrets = AsyncMock(return_value={"API_KEY": "secret-value"})

    monkeypatch.setattr(
        "app.core.security.MasterKeyProvider.get_master_key",
        lambda: b"master-key",
    )
    monkeypatch.setattr(
        "app.services.agent.backends.DatabaseSecretBackend",
        lambda master_key: secret_store,
    )

    prepared = await prepare_mcp_configs_for_runtime("agent-stdio", [cfg])
    assert len(prepared) == 1
    extra = prepared[0].extra_params or {}
    env = extra.get("env")
    assert isinstance(env, dict)
    assert env["API_KEY"] == "secret-value"
    assert env["BASE"] == "1"


@pytest.mark.asyncio
async def test_prepare_warns_when_required_secret_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.agent.mcp_runtime_prepare import prepare_mcp_configs_for_runtime

    cfg = MCPConfig(
        name="stdio-mcp",
        type="stdio",
        command="echo",
        required_secrets=["MISSING_KEY"],
    )

    secret_store = AsyncMock()
    secret_store.get_all_secrets = AsyncMock(return_value={})

    monkeypatch.setattr(
        "app.core.security.MasterKeyProvider.get_master_key",
        lambda: b"master-key",
    )
    monkeypatch.setattr(
        "app.services.agent.backends.DatabaseSecretBackend",
        lambda master_key: secret_store,
    )

    prepared = await prepare_mcp_configs_for_runtime("agent-missing", [cfg])
    extra = prepared[0].extra_params or {}
    env = extra.get("env")
    assert isinstance(env, dict)
    assert "MISSING_KEY" not in env


@pytest.mark.asyncio
async def test_prepare_uses_secret_auth_provider_for_header_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.agent.mcp_runtime_prepare import prepare_mcp_configs_for_runtime

    cfg = MCPConfig(
        name="remote-mcp",
        type="sse",
        url="https://mcp.example.com/sse",
        headers={"Authorization": "Bearer {{secret:TOKEN}}"},
    )

    secret_store = AsyncMock()
    secret_store.get_all_secrets = AsyncMock(return_value={"TOKEN": "tok"})

    monkeypatch.setattr(
        "app.core.security.MasterKeyProvider.get_master_key",
        lambda: b"master-key",
    )
    monkeypatch.setattr(
        "app.services.agent.backends.DatabaseSecretBackend",
        lambda master_key: secret_store,
    )

    prepared = await prepare_mcp_configs_for_runtime("agent-remote", [cfg])
    assert prepared[0].auth_provider is not None


@pytest.mark.asyncio
async def test_prepare_falls_back_to_oauth_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.agent.mcp_runtime_prepare import prepare_mcp_configs_for_runtime

    cfg = MCPConfig(
        name="oauth-mcp",
        type="sse",
        url="https://mcp.example.com/sse",
        headers={"X-Plain": "static"},
    )
    oauth_cfg = cfg.model_copy(update={"headers": {"Authorization": "Bearer oauth-token"}})

    monkeypatch.setattr(
        "app.core.security.MasterKeyProvider.get_master_key",
        lambda: b"master-key",
    )
    monkeypatch.setattr(
        "app.services.agent.backends.DatabaseSecretBackend",
        lambda master_key: AsyncMock(get_all_secrets=AsyncMock(return_value={})),
    )
    monkeypatch.setattr(
        "app.ai_agents.general_agent.factory._try_inject_mcp_oauth",
        AsyncMock(return_value=oauth_cfg),
    )

    prepared = await prepare_mcp_configs_for_runtime("agent-oauth", [cfg])
    assert prepared[0].headers == {"Authorization": "Bearer oauth-token"}


@pytest.mark.asyncio
async def test_prepare_returns_original_configs_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.agent.mcp_runtime_prepare import prepare_mcp_configs_for_runtime

    cfg = MCPConfig(name="broken", type="stdio", command="echo")

    def _raise_master_key() -> bytes:
        raise RuntimeError("no master key")

    monkeypatch.setattr(
        "app.core.security.MasterKeyProvider.get_master_key",
        _raise_master_key,
    )

    prepared = await prepare_mcp_configs_for_runtime("agent-broken", [cfg])
    assert prepared == [cfg]
