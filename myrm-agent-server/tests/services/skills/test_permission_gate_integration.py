"""Integration tests for the skill permission gate chain.

Verifies that the async permission checker wired into SkillBoundaryProvider +
GuardrailMiddleware allows granted sensitive tools and denies ungranted ones,
mirroring the production wiring in build_general_agent.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from myrm_agent_harness.agent.middlewares.guardrails import (
    GuardrailMiddleware,
    SkillBoundaryProvider,
)
from myrm_agent_harness.agent.skill_agent.context import (
    reset_loaded_skills,
    set_loaded_skills,
)
from myrm_agent_harness.agent.skills import SkillMetadata
from myrm_agent_harness.backends.skills import SkillPermission

from app.services.skills.permission_service import create_async_permission_checker


@pytest.fixture(autouse=True)
def _reset_loaded_skills() -> None:
    reset_loaded_skills()
    yield
    reset_loaded_skills()


@asynccontextmanager
async def _granted_loader(perms: set[SkillPermission]):
    """Stub the per-session cache loader for the duration of the check."""
    with patch(
        "app.services.skills.permission_service.load_granted_permissions_cached",
        new=AsyncMock(return_value=perms),
    ):
        yield


def _request(tool_name: str, args: dict[str, object]) -> ToolCallRequest:
    return ToolCallRequest(
        tool=MagicMock(),
        state={},
        runtime=MagicMock(),
        tool_call={"name": tool_name, "args": args, "id": "call_1"},
    )


async def _handler(req: ToolCallRequest) -> ToolMessage:
    return ToolMessage(content="ok", tool_call_id="call_1")


@pytest.mark.asyncio
async def test_gate_allows_granted_sensitive_tool() -> None:
    """A skill granted CODE_INTERPRETER must let bash_code_execute_tool through."""
    set_loaded_skills([SkillMetadata(name="demo", description="d", version="1.0.0")])
    async with _granted_loader({SkillPermission.CODE_INTERPRETER}):
        checker = await create_async_permission_checker()
        mw = GuardrailMiddleware(
            providers=[SkillBoundaryProvider(permission_checker=checker)]
        )
        result = await mw.awrap_tool_call(
            _request("bash_code_execute_tool", {"command": "echo hi"}), _handler
        )

    assert result.content == "ok"
    assert result.status != "error"


@pytest.mark.asyncio
async def test_gate_denies_ungranted_sensitive_tool() -> None:
    """Without the required grant the sensitive tool call must be blocked."""
    set_loaded_skills([SkillMetadata(name="demo", description="d", version="1.0.0")])
    async with _granted_loader(set()):
        checker = await create_async_permission_checker()
        mw = GuardrailMiddleware(
            providers=[SkillBoundaryProvider(permission_checker=checker)]
        )
        result = await mw.awrap_tool_call(
            _request("bash_code_execute_tool", {"command": "echo hi"}), _handler
        )

    assert result.status == "error"
    assert "skill_boundary" in str(result.content)


@pytest.mark.asyncio
async def test_gate_allows_when_no_skill_loaded() -> None:
    """Without loaded skills the gate must not intercept the tool call."""
    async with _granted_loader(set()):
        checker = await create_async_permission_checker()
        mw = GuardrailMiddleware(
            providers=[SkillBoundaryProvider(permission_checker=checker)]
        )
        result = await mw.awrap_tool_call(
            _request("bash_code_execute_tool", {"command": "echo hi"}), _handler
        )

    assert result.content == "ok"


@pytest.mark.asyncio
async def test_gate_denies_network_tool_without_grant() -> None:
    """A skill without NETWORK_ACCESS must not reach the browser."""
    set_loaded_skills([SkillMetadata(name="demo", description="d", version="1.0.0")])
    async with _granted_loader(set()):
        checker = await create_async_permission_checker()
        mw = GuardrailMiddleware(
            providers=[SkillBoundaryProvider(permission_checker=checker)]
        )
        result = await mw.awrap_tool_call(
            _request("browser_navigate_tool", {"url": "http://example.com"}), _handler
        )

    assert result.status == "error"
    assert "skill_boundary" in str(result.content)


@pytest.mark.asyncio
async def test_gate_allows_network_tool_with_grant() -> None:
    """A NETWORK_ACCESS grant must let the browser tool through."""
    set_loaded_skills([SkillMetadata(name="demo", description="d", version="1.0.0")])
    async with _granted_loader({SkillPermission.NETWORK_ACCESS}):
        checker = await create_async_permission_checker()
        mw = GuardrailMiddleware(
            providers=[SkillBoundaryProvider(permission_checker=checker)]
        )
        result = await mw.awrap_tool_call(
            _request("browser_navigate_tool", {"url": "http://example.com"}), _handler
        )

    assert result.content == "ok"


@pytest.mark.asyncio
async def test_gate_denies_mcp_tool_by_mcp_auth() -> None:
    """MCP tools resolve to mcp_invoke: not a skill domain, gate stays open.

    MCP authorization is enforced by the MCP server layer, not the skill gate.
    """
    set_loaded_skills([SkillMetadata(name="demo", description="d", version="1.0.0")])
    async with _granted_loader(set()):
        checker = await create_async_permission_checker()
        mw = GuardrailMiddleware(
            providers=[SkillBoundaryProvider(permission_checker=checker)]
        )
        result = await mw.awrap_tool_call(
            _request("mcp__github__get_repo", {"repo": "x"}), _handler
        )

    assert result.content == "ok"
