"""Tests for external_cli persist gate."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.external_cli_gate import (
    ExternalCliBackendUnavailableError,
    assert_external_cli_tools_allowed,
    external_cli_backend_available,
)


@pytest.mark.asyncio
async def test_assert_external_cli_skips_when_tool_disabled() -> None:
    await assert_external_cli_tools_allowed(["web_search", "memory"])


@pytest.mark.asyncio
async def test_assert_external_cli_rejects_sandbox_deploy() -> None:
    with (
        patch(
            "app.config.external_cli_deploy.is_external_cli_deploy_supported",
            return_value=False,
        ),
        pytest.raises(ExternalCliBackendUnavailableError, match="not supported"),
    ):
        await assert_external_cli_tools_allowed(["external_cli"])


@pytest.mark.asyncio
async def test_assert_external_cli_rejects_when_no_backend() -> None:
    with (
        patch(
            "app.config.external_cli_deploy.is_external_cli_deploy_supported",
            return_value=True,
        ),
        patch(
            "app.services.agent.external_cli_gate.external_cli_backend_available",
            new=AsyncMock(return_value=False),
        ),
        pytest.raises(ExternalCliBackendUnavailableError, match="requires an enabled CLI backend"),
    ):
        await assert_external_cli_tools_allowed(["external_cli", "web_search"])


@pytest.mark.asyncio
async def test_assert_external_cli_allows_when_backend_available() -> None:
    with (
        patch(
            "app.config.external_cli_deploy.is_external_cli_deploy_supported",
            return_value=True,
        ),
        patch(
            "app.services.agent.external_cli_gate.external_cli_backend_available",
            new=AsyncMock(return_value=True),
        ),
    ):
        await assert_external_cli_tools_allowed(["external_cli"])


@pytest.mark.asyncio
async def test_external_cli_backend_available_when_backends_resolve() -> None:
    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    external_agents_dict={"agents": [{"name": "claude-code", "enabled": True}]},
                ),
            ),
        ),
        patch(
            "app.ai_agents.general_agent.external_agents.resolve_external_agent_backends",
            new=AsyncMock(return_value=[{"name": "claude-code"}]),
        ),
    ):
        assert await external_cli_backend_available() is True


@pytest.mark.asyncio
async def test_external_cli_backend_available_false_when_no_backends() -> None:
    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.ai_agents.general_agent.external_agents.resolve_external_agent_backends",
            new=AsyncMock(return_value=[]),
        ),
    ):
        assert await external_cli_backend_available() is False


@pytest.mark.asyncio
async def test_load_external_agents_config_ignores_invalid_agent_entries() -> None:
    resolve_mock = AsyncMock(return_value=[{"name": "codex"}])
    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    external_agents_dict={"agents": ["not-a-dict", {"name": "codex"}]},
                ),
            ),
        ),
        patch(
            "app.ai_agents.general_agent.external_agents.resolve_external_agent_backends",
            new=resolve_mock,
        ),
    ):
        assert await external_cli_backend_available() is True
        resolve_mock.assert_awaited_once_with([{"name": "codex"}])


@pytest.mark.asyncio
async def test_load_external_agents_config_returns_none_for_missing_dict() -> None:
    resolve_mock = AsyncMock(return_value=[])
    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=SimpleNamespace(external_agents_dict=None)),
        ),
        patch(
            "app.ai_agents.general_agent.external_agents.resolve_external_agent_backends",
            new=resolve_mock,
        ),
    ):
        assert await external_cli_backend_available() is False
        resolve_mock.assert_awaited_once_with(None)


@pytest.mark.asyncio
async def test_load_external_agents_config_returns_none_for_non_list_agents() -> None:
    resolve_mock = AsyncMock(return_value=[])
    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(
                return_value=SimpleNamespace(external_agents_dict={"agents": "invalid"}),
            ),
        ),
        patch(
            "app.ai_agents.general_agent.external_agents.resolve_external_agent_backends",
            new=resolve_mock,
        ),
    ):
        assert await external_cli_backend_available() is False
        resolve_mock.assert_awaited_once_with(None)


@pytest.mark.asyncio
async def test_load_external_agents_config_returns_none_for_empty_agent_list() -> None:
    resolve_mock = AsyncMock(return_value=[])
    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(
                return_value=SimpleNamespace(external_agents_dict={"agents": []}),
            ),
        ),
        patch(
            "app.ai_agents.general_agent.external_agents.resolve_external_agent_backends",
            new=resolve_mock,
        ),
    ):
        assert await external_cli_backend_available() is False
        resolve_mock.assert_awaited_once_with(None)
