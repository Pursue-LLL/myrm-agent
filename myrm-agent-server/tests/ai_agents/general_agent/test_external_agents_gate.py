"""Unit tests for external_agents pure gate helpers (pool/delegate entitlement)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_agents.general_agent.external_agents import (
    BUILTIN_CLI_VISUAL_AGENT_ID,
    ExternalAgentsMixin,
    _auth_mode,
    _cfg_int,
    _config_fingerprint,
    _default_cli_args,
    _register_backends_on_pool,
    _resolve_external_agent_cfgs,
    _runtime_pool_scope_id,
    needs_runtime_pool,
    should_mount_delegate_tool,
)


def test_default_cli_args_known_and_unknown() -> None:
    assert _default_cli_args("claude")
    assert _default_cli_args("unknown-agent") == []


def test_auth_mode_resolves_api_key_and_subscription() -> None:
    assert _auth_mode({"authMode": "api_key"}) == "api_key"
    assert _auth_mode({}) == "subscription"


def test_cfg_int_parses_and_falls_back() -> None:
    assert _cfg_int({"maxTurns": 10}, "maxTurns", 25) == 10
    assert _cfg_int({"maxTurns": "12"}, "maxTurns", 25) == 12
    assert _cfg_int({"maxTurns": "bad"}, "maxTurns", 25) == 25
    assert _cfg_int({"maxTurns": True}, "maxTurns", 25) == 25


def test_runtime_pool_scope_id_prefers_scope_then_chat_id() -> None:
    agent = SimpleNamespace(_runtime_pool_scope_id=" scope-1 ", chat_id="chat-2")
    assert _runtime_pool_scope_id(agent) == "scope-1"
    agent2 = SimpleNamespace(_runtime_pool_scope_id=None, chat_id=" chat-2 ")
    assert _runtime_pool_scope_id(agent2) == "chat-2"
    assert _runtime_pool_scope_id(SimpleNamespace()) is None


def test_config_fingerprint_stable_and_skips_disabled() -> None:
    cfgs: list[dict[str, object]] = [
        {"name": "b", "command": "echo", "args": ["-a"], "enabled": True},
        {"name": "a", "command": "claude", "args": [], "enabled": False},
        {"name": "a", "command": "claude", "args": [], "enabled": True},
        {"name": "", "command": "skip", "enabled": True},
        {"enabled": True},
    ]
    fp1 = _config_fingerprint(cfgs)
    fp2 = _config_fingerprint(list(reversed(cfgs)))
    assert fp1 == fp2
    assert len(fp1) == 16


@pytest.mark.asyncio
async def test_resolve_external_agent_cfgs_returns_explicit_config() -> None:
    explicit = [{"name": "cli", "command": "echo", "args": []}]
    assert await _resolve_external_agent_cfgs(explicit) == explicit


@pytest.mark.asyncio
async def test_resolve_external_agent_cfgs_non_local_returns_none() -> None:
    with patch("app.config.deploy_mode.is_local_mode", return_value=False):
        assert await _resolve_external_agent_cfgs(None) is None


@pytest.mark.asyncio
async def test_resolve_external_agent_cfgs_auto_detect_local() -> None:
    detected = SimpleNamespace(name="claude", path="/usr/bin/claude")

    class _FakeDetector:
        async def detect(self) -> list[object]:
            return [detected]

    with (
        patch("app.config.deploy_mode.is_local_mode", return_value=True),
        patch(
            "myrm_agent_harness.toolkits.acp.backend_detector.BackendDetector",
            _FakeDetector,
        ),
    ):
        cfgs = await _resolve_external_agent_cfgs(None)

    assert cfgs is not None
    assert cfgs[0]["name"] == "claude"
    assert cfgs[0]["command"] == "/usr/bin/claude"


def test_register_backends_on_pool_skips_invalid_and_registers_valid() -> None:
    pool = MagicMock()
    cfgs: list[dict[str, object]] = [
        {"enabled": False, "name": "off", "command": "echo"},
        {"enabled": True, "name": "", "command": "echo"},
        {"enabled": True, "name": "bad", "command": "echo", "type": "invalid"},
        {
            "enabled": True,
            "name": "ok-cli",
            "command": "echo",
            "type": "cli",
            "args": ["-n"],
            "authMode": "api_key",
            "maxTurns": "10",
        },
    ]
    _register_backends_on_pool(pool, cfgs)
    pool.register.assert_called_once()
    assert pool.register.call_args[0][0] == "ok-cli"


@pytest.mark.asyncio
async def test_resolve_external_agent_cfgs_auto_detect_failure_returns_none() -> None:
    with (
        patch("app.config.deploy_mode.is_local_mode", return_value=True),
        patch(
            "myrm_agent_harness.toolkits.acp.backend_detector.BackendDetector",
            side_effect=RuntimeError("detect failed"),
        ),
    ):
        assert await _resolve_external_agent_cfgs(None) is None


@pytest.mark.asyncio
async def test_setup_external_agents_swallows_errors() -> None:
    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin.external_agents_config = [{"name": "x", "command": "echo"}]

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("setup failed")

    mixin._do_setup_external_agents = _boom  # type: ignore[method-assign]
    await mixin._setup_external_agents([], [])


@pytest.mark.asyncio
async def test_ensure_runtime_pool_initializes_when_missing() -> None:
    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin._runtime_pool = None
    mixin._do_setup_external_agents = AsyncMock()  # type: ignore[method-assign]

    await mixin._ensure_runtime_pool()
    mixin._do_setup_external_agents.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_runtime_pool_noop_when_pool_exists() -> None:
    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin._runtime_pool = object()
    mixin._do_setup_external_agents = AsyncMock()  # type: ignore[method-assign]
    await mixin._ensure_runtime_pool()
    mixin._do_setup_external_agents.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_external_agent_cfgs_auto_detect_empty_returns_none() -> None:
    class _EmptyDetector:
        async def detect(self) -> list[object]:
            return []

    with (
        patch("app.config.deploy_mode.is_local_mode", return_value=True),
        patch(
            "myrm_agent_harness.toolkits.acp.backend_detector.BackendDetector",
            _EmptyDetector,
        ),
    ):
        assert await _resolve_external_agent_cfgs(None) is None


@pytest.mark.asyncio
async def test_do_setup_returns_early_without_configs() -> None:
    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin.external_agents_config = None
    with patch(
        "app.ai_agents.general_agent.external_agents._resolve_external_agent_cfgs",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await mixin._do_setup_external_agents([], [], mount_delegate_tool=True)
    assert getattr(mixin, "_runtime_pool", None) is None


def test_should_mount_delegate_tool_matrix() -> None:
    assert should_mount_delegate_tool(agent_id="general", force_delegate_agent=None) is True
    assert should_mount_delegate_tool(agent_id=BUILTIN_CLI_VISUAL_AGENT_ID, force_delegate_agent=None) is False
    assert should_mount_delegate_tool(agent_id="general", force_delegate_agent="claude") is False


def test_needs_runtime_pool_matrix() -> None:
    assert (
        needs_runtime_pool(
            enable_external_cli=False,
            agent_id="builtin-writer",
            force_delegate_agent=None,
        )
        is False
    )
    assert (
        needs_runtime_pool(
            enable_external_cli=True,
            agent_id="builtin-developer",
            force_delegate_agent=None,
        )
        is True
    )
    assert (
        needs_runtime_pool(
            enable_external_cli=False,
            agent_id=BUILTIN_CLI_VISUAL_AGENT_ID,
            force_delegate_agent=None,
        )
        is True
    )
    assert (
        needs_runtime_pool(
            enable_external_cli=False,
            agent_id="builtin-writer",
            force_delegate_agent="claude",
        )
        is True
    )
